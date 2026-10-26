"""Depth-averaged debris-flow / landslide runout solver (numba, multi-core).

Scheme: Bates et al. (2010) local-inertial shallow-water update on a staggered grid, with a Voellmy basal resistance
(Coulomb mu*cos(theta) + turbulent v^2/xi) applied semi-implicitly, flux limiting so a cell cannot lose more than it holds,
optional pore-pressure fluidization (mu_eff = mu (1 - 0.6 lambda)) and bed entrainment. This is the same scheme that the
platform's browser solver verified (mass conservation, well-balanced rest, Voellmy steady speed; docs/VALIDATION_REPORT V4-V7,
V29-V31) ported to compiled code. Faces carry discharge per unit width q [m2/s]; Qx is (ny, nx+1), Qy is (ny+1, nx).

Screening-grade: friction parameters are scenario values, not calibrated to any event."""
from __future__ import annotations
import numpy as np
from numba import njit, prange

G = 9.81
H_WET = 0.02       # face depth below which no flux (m)
V_MAX = 30.0       # velocity cap (m/s), prevents blow-up on near-vertical cells


@njit(parallel=True, cache=True, fastmath=True)
def _fluxes(H, Z, Qx, Qy, Hfx, Hfy, row_on, dx, dt, mu_eff, xi, nu_cap):
    ny, nx = H.shape
    for j in prange(ny):
        if not (row_on[j]):
            continue
        for i in range(1, nx):
            a = i - 1
            eA = Z[j, a] + H[j, a]
            eB = Z[j, i] + H[j, i]
            hf = max(eA, eB) - max(Z[j, a], Z[j, i])
            if hf <= H_WET:
                Qx[j, i] = 0.0
                Hfx[j, i] = 0.0
                continue
            Hfx[j, i] = hf
            q = Qx[j, i] - G * hf * dt * (eB - eA) / dx
            bs = (Z[j, i] - Z[j, a]) / dx
            cs = 1.0 / np.sqrt(1.0 + bs * bs)
            m = abs(q) / (1.0 + dt * G * abs(q) / (xi * hf * hf))
            m = max(0.0, m - hf * mu_eff * G * cs * dt)
            m = min(m, hf * nu_cap)
            Qx[j, i] = m if q >= 0 else -m
    for j in prange(1, ny):
        if not (row_on[j] or row_on[j - 1]):
            continue
        for i in range(nx):
            a = j - 1
            eA = Z[a, i] + H[a, i]
            eB = Z[j, i] + H[j, i]
            hf = max(eA, eB) - max(Z[a, i], Z[j, i])
            if hf <= H_WET:
                Qy[j, i] = 0.0
                Hfy[j, i] = 0.0
                continue
            Hfy[j, i] = hf
            # rows run north->south: eA is the northern cell, so gradient sign mirrors the x-direction
            q = Qy[j, i] - G * hf * dt * (eB - eA) / dx
            bs = (Z[j, i] - Z[a, i]) / dx
            cs = 1.0 / np.sqrt(1.0 + bs * bs)
            m = abs(q) / (1.0 + dt * G * abs(q) / (xi * hf * hf))
            m = max(0.0, m - hf * mu_eff * G * cs * dt)
            m = min(m, hf * nu_cap)
            Qy[j, i] = m if q >= 0 else -m


@njit(parallel=True, cache=True, fastmath=True)
def _limit_and_update(H, Z, Qx, Qy, Hfx, Hfy, V, Hmax, Vmax, ero, ent_vol, row_on, dx, dt, entrain, ent_rate):
    ny, nx = H.shape
    out = np.zeros((ny, nx))
    for j in prange(ny):
        for i in range(nx):
            qe = Qx[j, i + 1]
            qw = Qx[j, i]
            qs = Qy[j + 1, i] if j + 1 < ny else 0.0   # south face of row j (positive = southward = increasing row index)
            qn = Qy[j, i]
            # Qy[j,i] is the face between rows j-1 and j; positive q means flow toward increasing row (south)
            o = (qe if qe > 0 else 0.0) + (-qw if qw < 0 else 0.0) + (qs if qs > 0 else 0.0) + (-qn if qn < 0 else 0.0)
            o = o * dt / dx
            out[j, i] = H[j, i] / o if (o > H[j, i] and o > 0) else 1.0
    for j in prange(ny):
        for i in range(1, nx):
            q = Qx[j, i]
            if q > 0:
                Qx[j, i] = q * out[j, i - 1]
            elif q < 0:
                Qx[j, i] = q * out[j, i]
    for j in prange(1, ny):
        for i in range(nx):
            q = Qy[j, i]
            if q > 0:
                Qy[j, i] = q * out[j - 1, i]
            elif q < 0:
                Qy[j, i] = q * out[j, i]
    for j in prange(ny):
        for i in range(nx):
            qe = Qx[j, i + 1]
            qw = Qx[j, i]
            qs = Qy[j + 1, i] if j + 1 < ny else 0.0
            qn = Qy[j, i]
            h = H[j, i] - dt / dx * (qe - qw + qs - qn)
            if h < 0:
                h = 0.0
            ue = qe / Hfx[j, i + 1] if Hfx[j, i + 1] > 0.05 else 0.0
            uw = qw / Hfx[j, i] if Hfx[j, i] > 0.05 else 0.0
            vs = qs / Hfy[j + 1, i] if (j + 1 < ny and Hfy[j + 1, i] > 0.05) else 0.0
            vn = qn / Hfy[j, i] if Hfy[j, i] > 0.05 else 0.0
            v = np.sqrt(((ue + uw) * 0.5) ** 2 + ((vs + vn) * 0.5) ** 2) if h > 0.3 else 0.0
            if v > V_MAX:
                v = V_MAX
            if entrain and h > 0.5 and v > 2.0 and ero[j, i] > 0:
                e = min(ero[j, i], ent_rate * v * dt * min(1.0, h / 2.0))
                ero[j, i] -= e
                Z[j, i] -= e
                h += e
                ent_vol[0] += e * dx * dx
            H[j, i] = h
            V[j, i] = v
            if h > Hmax[j, i]:
                Hmax[j, i] = h
            if v > Vmax[j, i]:
                Vmax[j, i] = v


class FlowState:
    backend = "numba-cpu"

    def __init__(self, Z, dx):
        ny, nx = Z.shape
        import numba
        # thread start/sync cost dwarfs the work on small grids (measured: 8.8 ms/step on 20 threads vs 0.11 ms on 1 for 22k cells)
        numba.set_num_threads(int(min(numba.config.NUMBA_NUM_THREADS, max(1, (ny * nx) // 60000), 8)))
        self.dx = float(dx)
        self.Z = Z.astype("float64").copy()
        self.Z0 = self.Z.copy()
        self.H = np.zeros((ny, nx))
        self.V = np.zeros((ny, nx))
        self.Hmax = np.zeros((ny, nx))
        self.Vmax = np.zeros((ny, nx))
        self.Qx = np.zeros((ny, nx + 1))
        self.Qy = np.zeros((ny + 1, nx))
        self.Hfx = np.zeros((ny, nx + 1))
        self.Hfy = np.zeros((ny + 1, nx))
        self.ero = np.zeros((ny, nx))
        self.ent_vol = np.zeros(1)
        self.t = 0.0
        self.vx = np.zeros((ny, nx), "float32")
        self.vy = np.zeros((ny, nx), "float32")

    def add_release(self, depth_m):
        """Failed soil mass: the bed drops by the slide thickness, the flow gains it (mass moves, never created)."""
        d = np.where(np.isfinite(depth_m), np.maximum(depth_m, 0.0), 0.0)
        self.Z -= d
        self.H += d

    def volume(self):
        return float(self.H.sum() * self.dx ** 2)

    def moving(self, v_thr=0.3):
        return bool((self.V > v_thr).any())

    def cfl_dt(self, dt_max=0.2, alpha=0.6):
        hmax = float(self.H.max())
        if hmax < 0.05:
            return dt_max
        c = np.sqrt(G * hmax) + float(self.V.max())
        return float(min(dt_max, alpha * self.dx / max(c, 1e-3)))

    def step(self, dt, mu, xi, lam=0.0, entrain=False, ent_rate=0.0015, nu_cap=25.0):
        wet = (self.H > 0.0).any(axis=1)
        row_on = wet.copy()
        row_on[1:] |= wet[:-1]
        row_on[:-1] |= wet[1:]
        mu_eff = mu * (1.0 - 0.6 * float(lam))
        _fluxes(self.H, self.Z, self.Qx, self.Qy, self.Hfx, self.Hfy, row_on, self.dx, dt, mu_eff, float(xi), nu_cap)
        _limit_and_update(self.H, self.Z, self.Qx, self.Qy, self.Hfx, self.Hfy, self.V, self.Hmax, self.Vmax, self.ero,
                          self.ent_vol, row_on, self.dx, dt, bool(entrain), ent_rate)
        self.t += dt

    def velocity_components(self):
        """Cell-centre vx (east) and vy (north) in m/s for the particle overlay."""
        qe, qw = self.Qx[:, 1:], self.Qx[:, :-1]
        he, hw = self.Hfx[:, 1:], self.Hfx[:, :-1]
        ue = np.where(he > 0.05, qe / np.maximum(he, 1e-9), 0.0)
        uw = np.where(hw > 0.05, qw / np.maximum(hw, 1e-9), 0.0)
        qs, qn = self.Qy[1:, :], self.Qy[:-1, :]
        hs, hn = self.Hfy[1:, :], self.Hfy[:-1, :]
        us = np.where(hs > 0.05, qs / np.maximum(hs, 1e-9), 0.0)
        un = np.where(hn > 0.05, qn / np.maximum(hn, 1e-9), 0.0)
        vx = 0.5 * (ue + uw)
        vy_south = 0.5 * (us + un)
        wet = self.H > 0.3
        return np.where(wet, vx, 0.0).astype("float32"), np.where(wet, -vy_south, 0.0).astype("float32")

    # --- interface shared with flow_torch.FlowStateGPU
    def set_erodible(self, ero):
        self.ero = np.asarray(ero, "float64").copy()

    def hmax_now(self):
        return float(self.H.max())

    def vmax_now(self):
        return float(self.V.max())

    def snapshot(self):
        vx, vy = self.velocity_components()
        return self.H.astype("float16"), vx.astype("float16"), vy.astype("float16")

    def final(self):
        return {"Hmax": self.Hmax.astype("float32"), "Vmax": self.Vmax.astype("float32"), "H": self.H.astype("float32"),
                "dZ": self.Z - self.Z0, "ent_vol": float(self.ent_vol[0])}
