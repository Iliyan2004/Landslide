"""CUDA twin of flow.FlowState (identical scheme, whole-domain tensor ops). GPU first, numba CPU as the fallback.
State lives on the GPU; only frame snapshots and final rasters cross to host RAM."""
from __future__ import annotations
import numpy as np
import torch

G = 9.81
H_WET = 0.02
V_MAX = 30.0


def available():
    return torch.cuda.is_available()


class FlowStateGPU:
    backend = "cuda"

    def __init__(self, Z, dx, dtype=torch.float32, device="cuda", compile=None):
        self.dev, self.dt_ = torch.device(device), dtype
        self.dx = float(dx)
        z = torch.as_tensor(np.asarray(Z, "float64"), device=self.dev)
        self.zoff = float(z.min())                      # float32 keeps ~1e-4 m resolution after removing the offset
        self.Z = (z - self.zoff).to(dtype)
        self.Z0 = self.Z.clone()
        ny, nx = self.Z.shape
        mk = lambda *s: torch.zeros(*s, device=self.dev, dtype=dtype)
        self.H, self.V, self.Hmax, self.Vmax, self.ero = mk(ny, nx), mk(ny, nx), mk(ny, nx), mk(ny, nx), mk(ny, nx)
        self.Qx, self.Hfx = mk(ny, nx + 1), mk(ny, nx + 1)
        self.Qy, self.Hfy = mk(ny + 1, nx), mk(ny + 1, nx)
        self.ent_vol_t = torch.zeros((), device=self.dev, dtype=torch.float64)
        self.t = 0.0
        # Fusing ~100 elementwise kernels into a few Triton kernels is ~4x faster than the CUDA-graph path on big grids
        # but costs ~20 s to compile per grid shape, so small grids use the plain graph path (still on the GPU).
        self.compiled = (ny * nx >= 300_000) if compile is None else bool(compile)
        self._fn = None

    def _stepfn(self):
        if self._fn is None:
            self._fn = self._step
            if self.compiled:
                try:
                    import triton  # noqa: F401
                    self._fn = torch.compile(self._step, dynamic=False)
                except Exception as e:
                    print("[flow] torch.compile unavailable, using eager kernels:", e, flush=True)
        return self._fn

    # --- host <-> device
    def set_erodible(self, ero_np):
        self.ero = torch.as_tensor(np.asarray(ero_np, "float32"), device=self.dev).to(self.dt_)

    def add_release(self, depth_np):
        d = torch.as_tensor(np.nan_to_num(np.asarray(depth_np, "float32")), device=self.dev).to(self.dt_).clamp_min(0)
        self.Z -= d
        self.H += d

    @property
    def ent_vol(self):
        return np.array([float(self.ent_vol_t)])

    def volume(self):
        return float(self.H.double().sum()) * self.dx ** 2

    def hmax_now(self):
        return float(self.H.max())

    def vmax_now(self):
        return float(self.V.max())

    def cfl_dt(self, dt_max=0.2, alpha=0.6):
        h = self.hmax_now()
        if h < 0.05:
            return dt_max
        c = (G * h) ** 0.5 + self.vmax_now()
        return float(min(dt_max, alpha * self.dx / max(c, 1e-3)))

    def snapshot(self):
        vx, vy = self._vel()
        return (self.H.float().cpu().numpy().astype("float16"), vx.cpu().numpy().astype("float16"), vy.cpu().numpy().astype("float16"))

    def final(self):
        c = lambda t: t.float().cpu().numpy()
        return {"Hmax": c(self.Hmax), "Vmax": c(self.Vmax), "H": c(self.H),
                "dZ": (self.Z - self.Z0).double().cpu().numpy(), "ent_vol": float(self.ent_vol_t)}

    # --- solver
    @torch.no_grad()
    def step(self, dt, mu, xi, lam=0.0, entrain=False, ent_rate=0.0015, nu_cap=25.0):
        """Eager single step (dt may be a float or a 0-d device tensor)."""
        self._step(dt, mu, xi, lam, entrain, ent_rate, nu_cap)
        self.t += float(dt) if not torch.is_tensor(dt) else 0.0

    @torch.no_grad()
    def advance(self, dt, n, mu, xi, lam=0.0, entrain=False, ent_rate=0.0015, nu_cap=25.0):
        """n steps of size dt via a captured CUDA graph (one launch per step instead of ~50 kernels)."""
        key = (mu, xi, lam, bool(entrain), ent_rate, nu_cap)
        if getattr(self, "_gkey", None) != key:
            self._dt_t = torch.full((), float(dt), device=self.dev, dtype=self.dt_)
            for _ in range(3):                                         # warm-up on a side stream (required before capture)
                H0, V0, Q0 = self.H.clone(), self.V.clone(), (self.Qx.clone(), self.Qy.clone())
                st = torch.cuda.Stream(); st.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(st):
                    self._stepfn()(self._dt_t, mu, xi, lam, entrain, ent_rate, nu_cap)
                torch.cuda.current_stream().wait_stream(st)
                self.H.copy_(H0); self.V.copy_(V0); self.Qx.copy_(Q0[0]); self.Qy.copy_(Q0[1])
            self._graph = torch.cuda.CUDAGraph()
            snap = (self.H.clone(), self.V.clone(), self.Qx.clone(), self.Qy.clone(), self.Z.clone(), self.ero.clone(),
                    self.Hmax.clone(), self.Vmax.clone(), self.ent_vol_t.clone(), self.Hfx.clone(), self.Hfy.clone())
            with torch.cuda.graph(self._graph):
                self._stepfn()(self._dt_t, mu, xi, lam, entrain, ent_rate, nu_cap)
            for t_, v_ in zip((self.H, self.V, self.Qx, self.Qy, self.Z, self.ero, self.Hmax, self.Vmax, self.ent_vol_t, self.Hfx, self.Hfy), snap):
                t_.copy_(v_)                                           # capture does not execute; restore anyway for safety
            self._gkey = key
        self._dt_t.fill_(float(dt))
        for _ in range(n):
            self._graph.replay()
        self.t += float(dt) * n

    def _step(self, dt, mu, xi, lam=0.0, entrain=False, ent_rate=0.0015, nu_cap=25.0):
        H, Z, dx = self.H, self.Z, self.dx
        mu_eff = mu * (1.0 - 0.6 * float(lam))
        # x faces
        za, zb = Z[:, :-1], Z[:, 1:]
        ea, eb = za + H[:, :-1], zb + H[:, 1:]
        hf = torch.maximum(ea, eb) - torch.maximum(za, zb)
        wet = hf > H_WET
        q = self.Qx[:, 1:-1] - G * hf * dt * (eb - ea) / dx
        cs = torch.rsqrt(1.0 + ((zb - za) / dx) ** 2)
        hf2 = torch.clamp(hf, min=H_WET)
        m = q.abs() / (1.0 + dt * G * q.abs() / (xi * hf2 * hf2))
        m = torch.minimum(torch.clamp(m - hf * mu_eff * G * cs * dt, min=0.0), hf * nu_cap)
        self.Qx[:, 1:-1] = torch.where(wet, torch.sign(q) * m, torch.zeros_like(q))
        self.Hfx[:, 1:-1] = torch.where(wet, hf, torch.zeros_like(hf))
        # y faces (rows run north->south; positive q = toward increasing row)
        za, zb = Z[:-1, :], Z[1:, :]
        ea, eb = za + H[:-1, :], zb + H[1:, :]
        hf = torch.maximum(ea, eb) - torch.maximum(za, zb)
        wet = hf > H_WET
        q = self.Qy[1:-1, :] - G * hf * dt * (eb - ea) / dx
        cs = torch.rsqrt(1.0 + ((zb - za) / dx) ** 2)
        hf2 = torch.clamp(hf, min=H_WET)
        m = q.abs() / (1.0 + dt * G * q.abs() / (xi * hf2 * hf2))
        m = torch.minimum(torch.clamp(m - hf * mu_eff * G * cs * dt, min=0.0), hf * nu_cap)
        self.Qy[1:-1, :] = torch.where(wet, torch.sign(q) * m, torch.zeros_like(q))
        self.Hfy[1:-1, :] = torch.where(wet, hf, torch.zeros_like(hf))
        # outflow limiter
        qe, qw, qs, qn = self.Qx[:, 1:], self.Qx[:, :-1], self.Qy[1:, :], self.Qy[:-1, :]
        o = (torch.relu(qe) + torch.relu(-qw) + torch.relu(qs) + torch.relu(-qn)) * dt / dx
        out = torch.where((o > H) & (o > 0), H / torch.clamp(o, min=1e-12), torch.ones_like(H))
        qx = self.Qx[:, 1:-1]
        self.Qx[:, 1:-1] = torch.where(qx > 0, qx * out[:, :-1], torch.where(qx < 0, qx * out[:, 1:], qx))
        qy = self.Qy[1:-1, :]
        self.Qy[1:-1, :] = torch.where(qy > 0, qy * out[:-1, :], torch.where(qy < 0, qy * out[1:, :], qy))
        qe, qw, qs, qn = self.Qx[:, 1:], self.Qx[:, :-1], self.Qy[1:, :], self.Qy[:-1, :]
        h = torch.clamp(H - dt / dx * (qe - qw + qs - qn), min=0.0)
        he, hw, hs, hn = self.Hfx[:, 1:], self.Hfx[:, :-1], self.Hfy[1:, :], self.Hfy[:-1, :]
        ue = torch.where(he > 0.05, qe / torch.clamp(he, min=1e-9), torch.zeros_like(h))
        uw = torch.where(hw > 0.05, qw / torch.clamp(hw, min=1e-9), torch.zeros_like(h))
        vs = torch.where(hs > 0.05, qs / torch.clamp(hs, min=1e-9), torch.zeros_like(h))
        vn = torch.where(hn > 0.05, qn / torch.clamp(hn, min=1e-9), torch.zeros_like(h))
        v = torch.where(h > 0.3, torch.sqrt((0.5 * (ue + uw)) ** 2 + (0.5 * (vs + vn)) ** 2), torch.zeros_like(h)).clamp_(max=V_MAX)
        if entrain:
            ok = (h > 0.5) & (v > 2.0) & (self.ero > 0)
            e = torch.where(ok, torch.minimum(self.ero, ent_rate * v * dt * torch.clamp(h / 2.0, max=1.0)), torch.zeros_like(h))
            self.ero -= e; Z -= e; h = h + e
            self.ent_vol_t += e.double().sum() * dx * dx
        self.H.copy_(h); self.V.copy_(v)
        torch.maximum(self.Hmax, h, out=self.Hmax); torch.maximum(self.Vmax, v, out=self.Vmax)

    def _vel(self):
        qe, qw, qs, qn = self.Qx[:, 1:], self.Qx[:, :-1], self.Qy[1:, :], self.Qy[:-1, :]
        he, hw, hs, hn = self.Hfx[:, 1:], self.Hfx[:, :-1], self.Hfy[1:, :], self.Hfy[:-1, :]
        z = torch.zeros_like(self.H)
        ue = torch.where(he > 0.05, qe / torch.clamp(he, min=1e-9), z); uw = torch.where(hw > 0.05, qw / torch.clamp(hw, min=1e-9), z)
        us = torch.where(hs > 0.05, qs / torch.clamp(hs, min=1e-9), z); un = torch.where(hn > 0.05, qn / torch.clamp(hn, min=1e-9), z)
        wet = self.H > 0.3
        return torch.where(wet, 0.5 * (ue + uw), z).float(), torch.where(wet, -0.5 * (us + un), z).float()


def release_gpu_memory():
    """The GPU is shared with other users: hand cached blocks back after every job."""
    try:
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
