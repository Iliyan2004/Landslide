"""3D rockfall simulation on the DEM: a Monte Carlo of individual rocks (lumped mass, flight + bounce + rolling), run on the GPU first.

Each rock is a sphere (diameter drawn from a lognormal) released at rest on a steep rock slope.  Per time step (dt = 0.04 s):
  flight         ballistic: v_z -= g dt  (air drag neglected)
  contact        when the rock centre drops below ground + radius it is placed on the surface and the contact is resolved by impulse:
                   fast impact (normal speed > 1.5 m/s):  v_n' = -Rn v_n,   v_t' = Rt v_t,  after tilting the normal by a random roughness angle
                   slow contact (sliding / rolling):      v_n' = 0,          |v_t| -= mu |v_n|   (Coulomb / rolling resistance per step)
  stopping       |v| < 0.2 m/s for 1 s, or the rock leaves the area, or t > t_max
Rn, Rt, mu come from the surface under the rock (land-cover classes, plus shape multipliers) and are scenario values (not calibrated);
the sub-grid roughness angle stands in for the terrain detail a 30 m DEM does not carry and is the most sensitive parameter.
Barriers (rock-fall fences): a cell line with a height and an energy capacity; a rock that reaches it below the fence height with energy under the
capacity stops there; above the capacity it passes with the capacity removed; above the fence height it passes unchanged.
Energy reported is translational (0.5 m v^2); a rolling sphere carries up to 40% more in rotation.
Outputs (per cell): passage fraction, maximum energy, maximum bounce height; per rock: stop point and travel (reach) angle; a tracked subset of rocks
is recorded for animation."""
from __future__ import annotations
import numpy as np
import torch
import torch.nn.functional as F

G = 9.81
RHO = 2600.0
DT = 0.04
V_BOUNCE = 1.5          # normal impact speed above which a bounce (not sliding) is computed
SURFACES = {            # Rn (normal restitution), Rt (tangential), mu (friction / rolling resistance): SCENARIO values, uncalibrated
    "rock": (0.46, 0.86, 0.30), "talus": (0.32, 0.76, 0.45), "soil": (0.22, 0.60, 0.60), "forest": (0.17, 0.52, 0.66), "snow_ice": (0.15, 0.50, 0.22),
}
# scripts/check_rockfall_shadow.py: with the table above, rocks on a synthetic cliff-talus profile stop at reach angles 36-38 deg (literature shadow angle 27-32).
# Friction x0.4-0.5 meets both targets (1st percentile 29-31 deg, median 34-35); x0.45 is applied. A fit to published statistics, not to Pakistani deposits.
FRICTION_SCALE = 0.45
SURFACES = {k: (v[0], v[1], v[2] * FRICTION_SCALE) for k, v in SURFACES.items()}
LULC_TO_SURFACE = {8: "talus", 11: "soil", 2: "forest", 5: "soil", 7: "rock", 9: "snow_ice", 1: "soil", 4: "soil", 10: "soil"}      # ESRI land-cover classes
SHAPES = {"round": (1.0, 1.0, 1.0), "angular": (0.8, 0.9, 1.25), "platy": (0.6, 0.8, 1.5)}                                          # (Rn x, Rt x, mu x), assumed
ENERGY_CLASSES_KJ = (10, 50, 300, 1000)      # < 10, 10-50, 50-300, 300-1000, > 1000 kJ (barrier-capacity style classes)


def dev(prefer="auto"):
    if prefer in ("auto", "cuda") and torch.cuda.is_available():
        try:
            torch.zeros(1, device="cuda")
            return torch.device("cuda")
        except Exception:
            pass
    return torch.device("cpu")


def surface_maps(lulc, shape, default="talus"):
    """Per-cell (Rn, Rt, mu) arrays from a land-cover class raster (NaN/unknown -> default)."""
    rn = np.full(shape, SURFACES[default][0], "float32"); rt = np.full(shape, SURFACES[default][1], "float32"); mu = np.full(shape, SURFACES[default][2], "float32")
    if lulc is not None:
        for k, name in LULC_TO_SURFACE.items():
            m = np.isfinite(lulc) & (np.rint(np.nan_to_num(lulc)) == k)
            rn[m], rt[m], mu[m] = SURFACES[name]
    return rn, rt, mu


def auto_sources(slope, valid, min_slope=50.0, max_cells=200, rng=None):
    """Candidate release cells: steep rock faces (bare-rock slopes the soil model excludes). Returns (rows, cols)."""
    rng = rng or np.random.default_rng(0)
    r, c = np.where(valid & (slope >= min_slope))
    if len(r) > max_cells:
        w = np.clip(slope[r, c] - min_slope + 1.0, 1, None); w = w / w.sum()
        pick = rng.choice(len(r), max_cells, replace=False, p=w)
        r, c = r[pick], c[pick]
    return r, c


@torch.no_grad()
def simulate(Z, dx, src_rc, rocks_per_source=40, d50=0.8, d_sigma=0.35, shape="round", rn=None, rt=None, mu=None, rough_deg=9.0, t_max=100.0, track=250,
             rec_every=3, barriers=None, valid=None, seed=0, device="auto", stagger_s=20.0, progress=lambda s, f: None):
    """Z (ny,nx) metres, dx metres. barriers: dict of arrays {'cap_kj','height','id'} on the grid, or None. Returns a dict of numpy results."""
    d = dev(device)
    gen = torch.Generator(device=d); gen.manual_seed(int(seed))
    ny, nx = Z.shape
    Zt = torch.as_tensor(np.where(np.isfinite(Z), Z, np.nanmedian(Z)), dtype=torch.float32, device=d)
    Zx = torch.zeros_like(Zt); Zy = torch.zeros_like(Zt)
    Zx[:, 1:-1] = (Zt[:, 2:] - Zt[:, :-2]) / (2 * dx); Zx[:, 0] = (Zt[:, 1] - Zt[:, 0]) / dx; Zx[:, -1] = (Zt[:, -1] - Zt[:, -2]) / dx
    Zy[1:-1, :] = (Zt[2:, :] - Zt[:-2, :]) / (2 * dx); Zy[0, :] = (Zt[1, :] - Zt[0, :]) / dx; Zy[-1, :] = (Zt[-1, :] - Zt[-2, :]) / dx
    tex = lambda a: a[None, None]
    TZ, TX, TY = tex(Zt), tex(Zx), tex(Zy)

    def samp(T, x, y):
        grid = torch.stack([(x / dx) / (nx - 1) * 2 - 1, (y / dx) / (ny - 1) * 2 - 1], -1).view(1, -1, 1, 2)
        return F.grid_sample(T, grid, mode="bilinear", padding_mode="border", align_corners=True).view(-1)
    sh = SHAPES[shape]
    rn_t = torch.as_tensor(rn if rn is not None else np.full((ny, nx), SURFACES["talus"][0], "float32"), device=d) * sh[0]
    rt_t = torch.as_tensor(rt if rt is not None else np.full((ny, nx), SURFACES["talus"][1], "float32"), device=d) * sh[1]
    mu_t = torch.as_tensor(mu if mu is not None else np.full((ny, nx), SURFACES["talus"][2], "float32"), device=d) * sh[2]
    cap = bid = None
    if barriers is not None:
        cap = torch.as_tensor(barriers["cap_kj"], dtype=torch.float32, device=d) * 1000.0
        bh = torch.as_tensor(barriers["height"], dtype=torch.float32, device=d)
        bid = torch.as_tensor(barriers["id"], dtype=torch.long, device=d)
        nb = int(bid.max().item()) + 1
    sr, sc = np.asarray(src_rc[0]), np.asarray(src_rc[1])
    ns = len(sr)
    N = ns * rocks_per_source
    if N == 0:
        raise ValueError("no release cells")
    rr = torch.as_tensor(np.repeat(sr, rocks_per_source), device=d).float(); cc = torch.as_tensor(np.repeat(sc, rocks_per_source), device=d).float()
    x = (cc + torch.rand(N, device=d, generator=gen) - 0.5) * dx; y = (rr + torch.rand(N, device=d, generator=gen) - 0.5) * dx
    x = x.clamp(0, (nx - 1) * dx); y = y.clamp(0, (ny - 1) * dx)
    dia = torch.exp(np.log(d50) + d_sigma * torch.randn(N, device=d, generator=gen)).clamp(0.2, 6.0)
    rad = dia / 2; mass = 4.0 / 3.0 * np.pi * rad ** 3 * RHO
    z = samp(TZ, x, y) + rad + 0.05
    vx = torch.zeros(N, device=d); vy = torch.zeros(N, device=d); vz = torch.zeros(N, device=d)
    t_rel = torch.rand(N, device=d, generator=gen) * stagger_s                     # animation stagger only; physics is independent of it
    state = torch.zeros(N, dtype=torch.int8, device=d)                             # 0 not released, 1 moving, 2 stopped, 3 left the area / timeout
    still = torch.zeros(N, device=d); passed_bar = torch.zeros(N, dtype=torch.bool, device=d)
    z0 = z.clone(); x0, y0 = x.clone(), y.clone(); xs, ys, zs = x.clone(), y.clone(), z.clone()
    last_cell = torch.full((N,), -1, dtype=torch.long, device=d)
    reach = torch.zeros(ny * nx, device=d); emax = torch.zeros(ny * nx, device=d); hmax = torch.zeros(ny * nx, device=d); stops = torch.zeros(ny * nx, device=d)
    nrec = int(np.ceil((t_max + stagger_s) / (DT * rec_every))) + 1
    M = min(track, N)
    tr_ids = torch.as_tensor(np.random.default_rng(seed).choice(N, M, replace=False), device=d)
    rec = torch.zeros(nrec, M, 5, device=d)                                         # x, y, height above ground, speed, impact flag
    rec_state = torch.zeros(nrec, M, dtype=torch.int8, device=d)
    rough = float(np.deg2rad(rough_deg))
    steps = int(np.ceil((t_max + stagger_s) / DT)); k_rec = 0; imp_acc = torch.zeros(M, device=d)
    t = 0.0
    for s in range(steps):
        t = s * DT
        rel = (state == 0) & (t_rel <= t)
        state[rel] = 1
        act = state == 1
        if not bool(act.any()) and t > stagger_s:
            break
        vz = torch.where(act, vz - G * DT, vz)
        x = torch.where(act, x + vx * DT, x); y = torch.where(act, y + vy * DT, y); z = torch.where(act, z + vz * DT, z)
        out = act & ((x <= 0) | (x >= (nx - 1) * dx) | (y <= 0) | (y >= (ny - 1) * dx))
        if bool(out.any()):
            state[out] = 3; act = state == 1
        gz = samp(TZ, x, y); gx = samp(TX, x, y); gy = samp(TY, x, y)
        pen = gz + rad - z
        con = act & (pen > 0)
        impact_flag = torch.zeros(N, device=d)
        if bool(con.any()):
            nz = 1.0 / torch.sqrt(1 + gx * gx + gy * gy); nxn = -gx * nz; nyn = -gy * nz
            vn = vx * nxn + vy * nyn + vz * nz
            incoming = con & (vn < 0)
            fast = incoming & (-vn > V_BOUNCE)
            if bool(fast.any()):                                                    # tilt the normal by the sub-grid roughness before reflecting
                ang = (torch.rand(N, device=d, generator=gen) * 2 - 1) * rough; az = torch.rand(N, device=d, generator=gen) * 2 * np.pi
                tx_, ty_ = torch.cos(az) * torch.sin(ang.abs()), torch.sin(az) * torch.sin(ang.abs())
                n2x, n2y, n2z = nxn + tx_, nyn + ty_, nz * torch.cos(ang)
                nn = torch.sqrt(n2x ** 2 + n2y ** 2 + n2z ** 2); n2x, n2y, n2z = n2x / nn, n2y / nn, n2z / nn
            else:
                n2x, n2y, n2z = nxn, nyn, nz
            ci = (y / dx).round().long().clamp(0, ny - 1) * nx + (x / dx).round().long().clamp(0, nx - 1)
            Rn = rn_t.view(-1)[ci] * (1 + 0.15 * (torch.rand(N, device=d, generator=gen) * 2 - 1)); Rt = rt_t.view(-1)[ci] * (1 + 0.10 * (torch.rand(N, device=d, generator=gen) * 2 - 1))
            Mu = mu_t.view(-1)[ci]
            # fast impact: reflect about the (tilted) normal
            vnf = vx * n2x + vy * n2y + vz * n2z
            vtx, vty, vtz = vx - vnf * n2x, vy - vnf * n2y, vz - vnf * n2z
            fx = -Rn * vnf * n2x + Rt * vtx; fy = -Rn * vnf * n2y + Rt * vty; fz = -Rn * vnf * n2z + Rt * vtz
            # slow contact: keep tangential velocity (w.r.t. the true normal), reduce it by mu |vn|
            vtx2, vty2, vtz2 = vx - vn * nxn, vy - vn * nyn, vz - vn * nz
            vt = torch.sqrt(vtx2 ** 2 + vty2 ** 2 + vtz2 ** 2) + 1e-9
            red = torch.clamp(Mu * (-vn).clamp(min=0), max=vt)
            sx_, sy_, sz_ = vtx2 * (1 - red / vt), vty2 * (1 - red / vt), vtz2 * (1 - red / vt)
            slow = con & ~fast
            vx = torch.where(fast, fx, torch.where(slow, sx_, vx)); vy = torch.where(fast, fy, torch.where(slow, sy_, vy)); vz = torch.where(fast, fz, torch.where(slow, sz_, vz))
            # put the rock back on the surface
            z = torch.where(con, torch.maximum(z, gz + rad), z)
            impact_flag = fast.float()
        sp2 = vx * vx + vy * vy + vz * vz
        E = 0.5 * mass * sp2
        ci = (y / dx).round().long().clamp(0, ny - 1) * nx + (x / dx).round().long().clamp(0, nx - 1)
        h = (z - gz - rad).clamp(min=0)
        if cap is not None:
            bc = cap.view(-1)[ci]; on_bar = act & (bc > 0) & ~passed_bar
            if bool(on_bar.any()):
                hit_low = on_bar & (h <= bh.view(-1)[ci] + rad)
                stop_b = hit_low & (E <= bc)
                pass_cap = hit_low & (E > bc)
                if bool(stop_b.any()):
                    stops.index_add_(0, ci[stop_b], torch.ones(int(stop_b.sum()), device=d))
                state = torch.where(stop_b, torch.full_like(state, 2), state); vx = torch.where(stop_b, torch.zeros_like(vx), vx); vy = torch.where(stop_b, torch.zeros_like(vy), vy); vz = torch.where(stop_b, torch.zeros_like(vz), vz)
                f = torch.sqrt(((E - bc) / E.clamp(min=1.0)).clamp(min=0))
                vx = torch.where(pass_cap, vx * f, vx); vy = torch.where(pass_cap, vy * f, vy); vz = torch.where(pass_cap, vz * f, vz)
                passed_bar = passed_bar | pass_cap | (on_bar & (h > bh.view(-1)[ci] + rad))
        act = state == 1
        new_cell = act & (ci != last_cell)
        if bool(new_cell.any()):
            reach.index_add_(0, ci[new_cell], torch.ones(int(new_cell.sum()), device=d))
            last_cell = torch.where(new_cell, ci, last_cell)
        if bool(act.any()):
            emax.scatter_reduce_(0, ci[act], E[act], reduce="amax"); hmax.scatter_reduce_(0, ci[act], h[act], reduce="amax")
        sp = torch.sqrt(sp2)
        still = torch.where(act & (sp < 0.2), still + DT, torch.zeros_like(still))
        done = act & (still > 1.0)
        if bool(done.any()):
            state[done] = 2
            stops.index_add_(0, ci[done], torch.ones(int(done.sum()), device=d))
        tl = act & (t > t_max + t_rel)
        state[tl] = 3
        xs = torch.where(state >= 2, torch.where(xs == x0, x, xs), xs); ys = torch.where(state >= 2, torch.where(ys == y0, y, ys), ys); zs = torch.where(state >= 2, torch.where(zs == z0, z, zs), zs)
        imp_acc = torch.maximum(imp_acc, impact_flag[tr_ids])
        if s % rec_every == 0 and k_rec < nrec:
            rec[k_rec, :, 0] = x[tr_ids]; rec[k_rec, :, 1] = y[tr_ids]; rec[k_rec, :, 2] = h[tr_ids]; rec[k_rec, :, 3] = sp[tr_ids]; rec[k_rec, :, 4] = imp_acc
            rec_state[k_rec] = state[tr_ids]; imp_acc.zero_(); k_rec += 1
        if s % 200 == 0:
            progress("rockfall", min(0.95, s / steps))
    # final positions of rocks still moving count as stopped where they are
    still_moving = state == 1
    xs = torch.where(still_moving, x, torch.where(xs == x0, x, xs)); ys = torch.where(still_moving, y, torch.where(ys == y0, y, ys)); zs = torch.where(still_moving, z, torch.where(zs == z0, z, zs))
    L = torch.sqrt((xs - x0) ** 2 + (ys - y0) ** 2).clamp(min=1.0)
    ang = torch.rad2deg(torch.atan((z0 - zs).clamp(min=0) / L))
    res = {"reach_count": reach.view(ny, nx).cpu().numpy(), "emax_j": emax.view(ny, nx).cpu().numpy(), "hmax_m": hmax.view(ny, nx).cpu().numpy(), "stops": stops.view(ny, nx).cpu().numpy(),
           "n_rocks": int(N), "n_sources": int(ns), "stop_xy": np.c_[xs.cpu().numpy(), ys.cpu().numpy()], "src_xy": np.c_[x0.cpu().numpy(), y0.cpu().numpy()],
           "travel_angle_deg": ang.cpu().numpy(), "diameter_m": dia.cpu().numpy(), "state": state.cpu().numpy(),
           "rec": rec[:k_rec].cpu().numpy(), "rec_state": rec_state[:k_rec].cpu().numpy(), "rec_dt": DT * rec_every, "tracked": tr_ids.cpu().numpy(),
           "device": str(d), "stagger_s": float(stagger_s)}
    if str(d) != "cpu":
        torch.cuda.empty_cache()
    return res


def energy_class(e_kj):
    return int(np.searchsorted(ENERGY_CLASSES_KJ, e_kj, side="right"))
