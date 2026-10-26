"""Empirical angle-of-reach envelope (M15) and Voellmy point-mass profile model. SCREENING, not impact depths.

Reach criterion (energy line): a cell at elevation z reached by a path of length L from source elevation z0 is inside
the envelope if (z0 - z)/L >= tan(alpha_reach), tan(alpha)=H/L. Flow is routed over the DEM along ANY neighbour
(Dijkstra on path length), so the envelope follows terrain instead of a radial cone. Requires a source mask & volume.
"""
from __future__ import annotations
import heapq
import numpy as np
from ...errors import InsufficientData
from ...gates import check_runout_source
from ...units import G

N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def reach_envelope(dem, dx, dy, source_mask, alpha_reach_deg, max_up_m=0.0):
    """Returns (reached bool array, path_length array, max_horizontal_reach_m). `max_up_m`: tolerated uphill step."""
    nr, nc = dem.shape
    tana = np.tan(np.deg2rad(alpha_reach_deg))
    L = np.full(dem.shape, np.inf)
    z0 = np.full(dem.shape, np.nan)
    heap = []
    for r, c in zip(*np.nonzero(source_mask)):
        L[r, c] = 0.0
        z0[r, c] = dem[r, c]
        heapq.heappush(heap, (0.0, r, c))
    while heap:
        d, r, c = heapq.heappop(heap)
        if d > L[r, c]:
            continue
        for dr, dc in N8:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < nr and 0 <= cc < nc) or np.isnan(dem[rr, cc]):
                continue
            step = np.hypot(dr * dy, dc * dx)
            nd = d + step
            if dem[rr, cc] - dem[r, c] > max_up_m:
                continue
            zs = z0[r, c]
            if (zs - dem[rr, cc]) / nd < tana:
                continue
            if nd < L[rr, cc]:
                L[rr, cc] = nd
                z0[rr, cc] = zs
                heapq.heappush(heap, (nd, rr, cc))
    reached = np.isfinite(L)
    return reached, L, float(L[reached].max()) if reached.any() else 0.0


def ensemble_envelope(dem, dx, dy, source_mask, volume_m3, alpha_range_deg, n=20, seed=0):
    """Fraction of ensemble members reaching each cell. CONDITIONAL on the prior range of alpha (not a probability
    of occurrence). Volume only gates the run here; a published V-vs-H/L relation may be plugged by the caller."""
    check_runout_source(source_mask, volume_m3)
    lo, hi = alpha_range_deg
    if not (0 < lo <= hi < 60):
        raise InsufficientData(["valid alpha_reach range"], "M15")
    rng = np.random.default_rng(seed)
    freq = np.zeros(dem.shape)
    for a in rng.uniform(lo, hi, n):
        r, _, _ = reach_envelope(dem, dx, dy, source_mask, a)
        freq += r
    return {"envelope_frequency_conditional_on_priors": freq / n,
            "status": {"type": "envelope", "calibration": "not_calibrated", "not_simulated_extent": True}}


def voellmy_profile(s, z, mu, xi, h, v0=0.0, dt=0.05, t_max=3600.0):
    """Point-mass Voellmy run-out along a profile (s: distance, z: elevation arrays).

    dv/dt = g sin b - mu g cos b - g v^2/(xi h)   (one published convention; document it with outputs).
    Returns stop distance (m), peak velocity (m/s), path of (s,v). Stops when v<=0 or profile ends."""
    s, z = np.asarray(s, float), np.asarray(z, float)
    seg = np.hypot(np.diff(s), np.diff(z))
    cum = np.concatenate([[0], np.cumsum(seg)])
    sin_b = -np.diff(z) / seg
    sin_b = np.concatenate([sin_b, sin_b[-1:]])
    pos, v, t, vmax = 0.0, float(v0), 0.0, float(v0)
    hist = [(0.0, v)]
    while t < t_max:
        i = min(np.searchsorted(cum, pos, side="right") - 1, len(sin_b) - 1)
        sb = sin_b[i]
        cb = np.sqrt(max(1 - sb**2, 0))
        a = G * sb - mu * G * cb - G * v * abs(v) / (xi * h)
        vn = v + a * dt
        if vn <= 0 and a < 0:
            pos += max(v, 0) * v / (2 * max(-a, 1e-12))   # exact stop distance for const decel
            v = 0.0
            hist.append((pos, 0.0))
            break
        pos += 0.5 * (v + vn) * dt
        v = vn
        vmax = max(vmax, v)
        t += dt
        hist.append((pos, v))
        if pos >= cum[-1]:
            break
    return {"stop_distance_m": pos, "peak_velocity_ms": vmax, "path": np.array(hist),
            "reached_end_of_profile": bool(pos >= cum[-1]), "convention": "voellmy_dv/dt=gsinb-mu g cosb-g v^2/(xi h)"}


def mass_balance_residual(v_initial, v_entrained, v_deposited, v_exported, v_residual=0.0):
    """initial + entrained - deposited - exported - airborne/residual = 0 within solver tolerance (§6.2)."""
    return v_initial + v_entrained - v_deposited - v_exported - v_residual
