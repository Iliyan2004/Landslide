"""Rock-slope kinematic feasibility (methodology §5.2, M14 pre-screen). Needs MEASURED joint orientations.

Planar sliding (Markland-type): plane dips out of the face (dip_p < dip_slope), dip_p > phi, and dip direction within
`lateral_limit` (default 20 deg) of slope dip direction. Wedge: line of plane intersection plunges out of face,
plunge < slope dip (daylights) and plunge > phi.
"""
import numpy as np


def _normal(dip, dipdir):
    d, a = np.deg2rad(dip), np.deg2rad(dipdir)
    # downward-pointing pole expressed in (E, N, Up)
    return np.array([np.sin(d) * np.sin(a), np.sin(d) * np.cos(a), np.cos(d)])


def planar_feasible(plane_dip, plane_dipdir, slope_dip, slope_dipdir, phi_deg, lateral_limit=20.0):
    dd = abs((plane_dipdir - slope_dipdir + 180) % 360 - 180)
    return bool((plane_dip < slope_dip) and (plane_dip > phi_deg) and (dd <= lateral_limit))


def intersection_line(dip1, dd1, dip2, dd2):
    """Plunge & trend (deg) of the intersection of two planes (pointing downward)."""
    n1, n2 = _normal(dip1, dd1), _normal(dip2, dd2)
    l = np.cross(n1, n2)
    nrm = np.linalg.norm(l)
    if nrm < 1e-9:
        return None
    l = l / nrm
    if l[2] > 0:
        l = -l
    plunge = np.rad2deg(np.arcsin(-l[2]))
    trend = np.rad2deg(np.arctan2(l[0], l[1])) % 360
    return plunge, trend


def wedge_feasible(dip1, dd1, dip2, dd2, slope_dip, slope_dipdir, phi_deg, trend_limit=90.0):
    il = intersection_line(dip1, dd1, dip2, dd2)
    if il is None:
        return False
    plunge, trend = il
    dd = abs((trend - slope_dipdir + 180) % 360 - 180)
    return bool(plunge < slope_dip and plunge > phi_deg and dd <= trend_limit)
