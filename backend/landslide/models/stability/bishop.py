"""Simplified Bishop limit-equilibrium (methodology §5.2, M12). SITE-SPECIFIC: needs real slip geometry & strengths.

FS = sum[(c' b + (W - u b) tan phi')/m_i] / sum[W sin alpha],  m_i = cos alpha + sin alpha tan phi'/FS  (iterate).
Convention: alpha = base inclination, positive when the slice base dips in the direction of sliding.
Reports convergence; refuses non-convergent / non-physical (m_i<=0) cases.
"""
from __future__ import annotations
import numpy as np


def bishop_fs(b, W, alpha_rad, c, phi_rad, u=0.0, fs0=1.5, tol=1e-6, max_iter=100):
    b, W, a, c, phi = [np.asarray(x, float) for x in (b, W, alpha_rad, c, phi_rad)]
    u = np.broadcast_to(np.asarray(u, float), b.shape)
    drive = np.sum(W * np.sin(a))
    if drive <= 0:
        return {"fs": np.inf, "converged": True, "iterations": 0, "note": "no net driving moment"}
    fs = fs0
    for it in range(1, max_iter + 1):
        m = np.cos(a) + np.sin(a) * np.tan(phi) / fs
        if np.any(m <= 0.2):
            return {"fs": np.nan, "converged": False, "iterations": it, "note": "m_alpha<=0.2: Bishop non-physical"}
        num = np.sum((c * b + np.maximum(W - u * b, 0.0) * np.tan(phi)) / m)
        new = num / drive
        if abs(new - fs) < tol:
            return {"fs": float(new), "converged": True, "iterations": it}
        fs = new
    return {"fs": float(fs), "converged": False, "iterations": max_iter, "note": "max_iter reached"}


def slices_for_circle(profile_x, profile_z, xc, zc, R, gamma, n=40, base_z=None):
    """Build slices for a circular surface through a ground profile (homogeneous soil, no water).

    The failure mass lies between circle entry/exit; slice top = profile, slice base = circle lower arc.
    Returns dict(b, W, alpha) per unit width; slope assumed descending toward +x (sliding to +x)."""
    px, pz = np.asarray(profile_x, float), np.asarray(profile_z, float)
    xs = np.linspace(xc - R, xc + R, 4001)
    zb = zc - np.sqrt(np.maximum(R**2 - (xs - xc) ** 2, 0.0))
    zg = np.interp(xs, px, pz)
    inside = (zg > zb) & (np.abs(xs - xc) < R)
    if not inside.any():
        return None
    x0, x1 = xs[inside].min(), xs[inside].max()
    edges = np.linspace(x0, x1, n + 1)
    xm = 0.5 * (edges[:-1] + edges[1:])
    bw = np.diff(edges)
    ztop = np.interp(xm, px, pz)
    zbase = zc - np.sqrt(np.maximum(R**2 - (xm - xc) ** 2, 0.0))
    h = np.maximum(ztop - zbase, 0.0)
    alpha = np.arcsin(np.clip((xc - xm) / R, -1, 1))   # + where base dips toward +x (sliding direction)
    return {"b": bw, "W": gamma * h * bw, "alpha": alpha, "x": xm}


def search_circles(profile_x, profile_z, gamma, c, phi_deg, xr, zr, Rr, n=40, u_fn=None):
    """Brute-force grid search over circle centres/radii. Returns the minimum-FS converged surface."""
    best = None
    for xc in xr:
        for zc in zr:
            for R in Rr:
                s = slices_for_circle(profile_x, profile_z, xc, zc, R, gamma, n)
                if s is None or s["alpha"].max() <= 0:
                    continue
                r = bishop_fs(s["b"], s["W"], s["alpha"], c, np.deg2rad(phi_deg),
                              u_fn(s) if u_fn else 0.0)
                if r["converged"] and np.isfinite(r["fs"]) and (best is None or r["fs"] < best["fs"]):
                    best = {**r, "xc": xc, "zc": zc, "R": R}
    return best
