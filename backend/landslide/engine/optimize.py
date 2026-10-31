"""Automatic placement of debris barriers (check dams) with a hard evaluation budget.

Every evaluation is a FULL runout simulation (seconds on the GPU), so this is expensive and is only run on request; there is no surrogate.
Search space (per barrier): position along the main flow corridor s in [0.15, 0.95] (fraction of its length), height h in [2, 12] m, length
L in [40, 400] m, oriented across the local flow direction. The flow corridor is the steepest-descent path from the centroid of the baseline run's
failing cells, followed while the baseline flow reached 0.3 m.
Objective (minimise):  loss_pkr + road_blocked_km x road_penalty_pkr_per_km + wall_cost_pkr_per_m2 x sum(L x h)
where the wall cost is a USER input (no default cost data exists here); with a zero wall cost the optimiser will always choose the biggest wall.
Uses scipy differential evolution; stops at max_evals."""
from __future__ import annotations
import numpy as np
from pyproj import Transformer
from ..data.preprocessing import terrain


class BudgetExceeded(Exception):
    pass


def flow_corridor(dem, hmax, failing_rc, dx, max_steps=2000):
    """Steepest-descent path (list of (row, col)) from the failing-cell centroid, following cells the baseline flow reached."""
    z = np.asarray(dem, float)     # NaN cells (outside the area) stay NaN so they act as outlets; filling them with a HIGH value made the priority-flood fill the whole area flat (no flow path)
    d8 = terrain.d8_flow(terrain.fill_pits(z), dx, dx)["downstream"]
    ny, nx = z.shape
    r0, c0 = int(round(np.mean([a for a, _ in failing_rc]))), int(round(np.mean([b for _, b in failing_rc])))
    # start at the failing cell nearest the centroid, so the path begins on the slide
    d = [(a - r0) ** 2 + (b - c0) ** 2 for a, b in failing_rc]
    r, c = failing_rc[int(np.argmin(d))]
    path, quiet = [(r, c)], 0
    for _ in range(max_steps):
        j = int(d8[r, c])
        if j < 0:
            break
        r, c = divmod(j, nx)
        path.append((r, c))
        quiet = quiet + 1 if not (hmax[r, c] > 0.3) else 0
        if quiet >= 3:
            break
    return path


def barrier_at(path, s_frac, length_m, height_m, affine, epsg, dx):
    """A barrier segment across the corridor at fraction s_frac of its length, as lon/lat coordinates."""
    P = np.array(path, float)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    k = int(np.clip(np.searchsorted(seg, s_frac * seg[-1]), 1, len(P) - 1))
    t = P[k] - P[k - 1]; t = t / (np.hypot(*t) + 1e-9)                       # direction in (row, col)
    perp = np.array([-t[1], t[0]])                                            # across the flow
    half = 0.5 * length_m / dx
    a = P[k] + half * perp; b = P[k] - half * perp
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    out = []
    for rr, cc in (a, b):
        x, y = affine * (cc + 0.5, rr + 0.5)
        out.append(list(tr.transform(x, y)))
    return {"coords": out, "height_m": float(height_m), "width_m": float(dx)}


def optimise(evaluate, path, affine, epsg, dx, n_barriers=2, max_evals=40, wall_cost_pkr_per_m2=0.0, road_penalty_pkr_per_km=0.0, seed=0, progress=lambda s, f: None):
    """evaluate(barriers) -> {'loss_pkr':..., 'road_blocked_km':...}. Returns best barriers and the history of evaluations."""
    from scipy.optimize import differential_evolution
    hist = []
    def decode(x):
        return [barrier_at(path, x[3 * i], x[3 * i + 2], x[3 * i + 1], affine, epsg, dx) for i in range(n_barriers)]
    def f(x):
        if len(hist) >= max_evals:
            raise BudgetExceeded()
        bars = decode(x)
        r = evaluate(bars)
        cost = wall_cost_pkr_per_m2 * sum(x[3 * i + 1] * x[3 * i + 2] for i in range(n_barriers))
        obj = float(r["loss_pkr"]) + float(r.get("road_blocked_km", 0.0)) * road_penalty_pkr_per_km + cost
        hist.append({"x": [float(v) for v in x], "objective": obj, "loss_pkr": float(r["loss_pkr"]), "road_blocked_km": float(r.get("road_blocked_km", 0.0)), "wall_cost_pkr": cost})
        progress(f"evaluation {len(hist)}/{max_evals}", len(hist) / max_evals)
        return obj
    bounds = [(0.15, 0.95), (2.0, 12.0), (40.0, 400.0)] * n_barriers
    try:
        differential_evolution(f, bounds, seed=seed, popsize=max(4, min(8, max_evals // (3 * n_barriers) or 4)), maxiter=50, polish=False, tol=0, init="sobol", updating="immediate")
    except BudgetExceeded:
        pass
    best = min(hist, key=lambda h: h["objective"])
    return {"best": {**best, "barriers": decode(np.array(best["x"]))}, "evaluations": len(hist), "history": hist, "budget": max_evals,
            "note": "no surrogate: every point is a full simulation; with the evaluation budget small the result is a good option, not a proven optimum"}
