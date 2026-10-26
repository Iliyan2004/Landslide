"""2D rockfall trajectory model (M14): exact ballistic flight + normal/tangential restitution per terrain class.

Profile: polyline (x_i, z_i) with per-segment terrain class -> (e_n, e_t). No fragmentation, rolling approximated
by termination when post-impact speed < v_stop. Requires site-resolution terrain & CALIBRATED restitution.
Flight/segment intersection is solved analytically (quadratic) so there is no time-step tunnelling.
"""
from __future__ import annotations
import numpy as np
from ...units import G


def _first_hit(x0, z0, vx, vz, X, Z, skip_seg=None, eps=1e-9):
    best_t, best_i = np.inf, None
    for i in range(len(X) - 1):
        x1, x2, z1, z2 = X[i], X[i + 1], Z[i], Z[i + 1]
        if x2 == x1:
            continue
        s = (z2 - z1) / (x2 - x1)
        # z0+vz t -0.5 g t^2 - z1 - s(x0+vx t - x1) = 0
        A, B, C = -0.5 * G, vz - s * vx, z0 - z1 - s * (x0 - x1)
        disc = B * B - 4 * A * C
        if disc < 0:
            continue
        sq = np.sqrt(disc)
        for t in ((-B + sq) / (2 * A), (-B - sq) / (2 * A)):
            if t <= eps:
                continue
            xt = x0 + vx * t
            if min(x1, x2) - 1e-9 <= xt <= max(x1, x2) + 1e-9 and t < best_t:
                best_t, best_i = t, i
    return best_t, best_i


def simulate(X, Z, seg_class, restitution, x0, z0, vx0=0.0, vz0=0.0, mass_kg=1000.0,
             v_stop=0.5, max_bounces=200):
    """restitution: {class: (e_n, e_t)}. Returns trajectory points, impact list (x, KE_J) and run-out x.

    Velocities are in the global frame; at each impact they're resolved on the segment tangent/normal."""
    x, z, vx, vz = float(x0), float(z0), float(vx0), float(vz0)
    pts, impacts = [(x, z)], []
    last = None
    for _ in range(max_bounces):
        t, i = _first_hit(x, z, vx, vz, X, Z, last)
        if i is None or not np.isfinite(t):
            break
        xn, zn = x + vx * t, z + vz * t - 0.5 * G * t * t
        vxn, vzn = vx, vz - G * t
        # sample flight for plotting
        for tt in np.linspace(0, t, 12)[1:]:
            pts.append((x + vx * tt, z + vz * tt - 0.5 * G * tt * tt))
        dx_, dz_ = X[i + 1] - X[i], Z[i + 1] - Z[i]
        L = np.hypot(dx_, dz_)
        tx, tz = dx_ / L, dz_ / L
        nx, nz = -tz, tx
        if nz < 0:
            nx, nz = -nx, -nz            # upward normal
        vt, vn = vxn * tx + vzn * tz, vxn * nx + vzn * nz
        en, et = restitution[seg_class[i]]
        impacts.append((xn, 0.5 * mass_kg * (vxn**2 + vzn**2)))
        vn_new, vt_new = -en * vn, et * vt
        vx, vz = vt_new * tx + vn_new * nx, vt_new * tz + vn_new * nz
        x, z = xn, zn
        last = i
        if np.hypot(vx, vz) < v_stop:
            break
    return {"path": np.array(pts), "impacts": impacts, "runout_x": x,
            "max_impact_energy_J": max((e for _, e in impacts), default=0.0),
            "note": "no fragmentation; stop rule v<v_stop; restitution must be calibrated per terrain class"}
