"""Rain-driven and earthquake-driven failure timing (hydro-mechanical trigger).

Rain: Green-Ampt wetting front F(t) (independent of slip depth) -> per-cell saturation m(t) = max(m0, F/(dtheta z)) ->
infinite-slope FS(t) with root cohesion. A cell fails at the first step with FS < 1. Soil depth may thin with slope
(assumption, stated in the run). Parameters are a SCENARIO point inside the explicit prior ranges (quantile q)."""
from __future__ import annotations
import numpy as np
from scipy import ndimage
from ..models.infiltration import green_ampt, iverson as IVS
from ..models.stability import infinite_slope as INF
from ..models.seismic import newmark as NM

FAILURE_TYPES = {   # (mu, xi, label). Voellmy parameters: scenario values, NOT calibrated to any event.
    "debris_flow": (0.12, 200.0, "Debris flow / mudflow"),
    "earth_flow": (0.20, 250.0, "Earth / soil flow"),
    "shallow_slide": (0.30, 300.0, "Shallow slide (short runout)"),
}


def at_quantile(rng, q, log=False):
    lo, hi = float(rng["min"]), float(rng["max"])
    if log:
        return float(np.exp(np.log(lo) + q * (np.log(hi) - np.log(lo))))
    return lo + q * (hi - lo)


def scenario_point(spec, q):
    """Pick one parameter set from the prior ranges. q=0 weakest .. 1 strongest (cohesion/friction/depth-min)."""
    p = {}
    for k, v in spec.items():
        if isinstance(v, dict) and "min" in v:
            p[k] = at_quantile(v, q, log=(k == "hydraulic_conductivity"))
        else:
            p[k] = v
    # weak scenario = lower strength AND deeper soil AND more conductive soil (all are the pessimistic side)
    if "soil_depth" in spec and isinstance(spec["soil_depth"], dict):
        p["soil_depth_max"] = float(spec["soil_depth"]["max"]); p["soil_depth_min"] = float(spec["soil_depth"]["min"])
        p["soil_depth"] = at_quantile(spec["soil_depth"], 1 - q)
    return p


def _eff(slope, p, fields):
    """Effective slope (regrading), root cohesion (planting) and water table (drainage) with optional per-cell intervention fields."""
    f = fields or {}
    cap = f.get("slope_cap")
    slope_e = slope if cap is None else np.minimum(slope, np.where(np.isfinite(cap), cap, 1e9))
    c_root = p["root_cohesion"] + (f.get("c_root_add") if f.get("c_root_add") is not None else 0.0)
    wt = p["water_table"] + (f.get("wt_add") if f.get("wt_add") is not None else 0.0)
    return slope_e, c_root, wt, f.get("m_scale")


def suction_cohesion(p, m):
    """Apparent cohesion from matric suction (Pa): p['suction_pa'] x (1 - m). The unsaturated soil above the wetting front is held by suction, which is lost as
    the saturated fraction m of the slip layer rises (Fredlund et al. 1978 with the suction term scaled to its dry value; m = 1 gives none).
    Absent or zero by default: it needs a soil-water retention measurement that does not exist here, so it is a scenario input."""
    sa = p.get("suction_pa", 0.0)
    return 0.0 if (np.isscalar(sa) and sa == 0.0) else sa * (1.0 - np.clip(m, 0.0, 1.0))


def mobilisable_mask(slope, valid, z, p, max_soil_slope=45.0, fields=None):
    """Cells that can fail in an event: soil can exist (slope <= max_soil_slope; steeper = bare rock) and the slope was STABLE
    before the event (FS >= 1 at the baseline water table). Pre-existing unstable cells would already have failed."""
    slope_e, c_root, wt, _ = _eff(slope, p, fields)
    m0 = green_ampt.m_from_water_table(z, wt)
    fs0 = INF.factor_of_safety(slope_e, z, p["effective_cohesion"], p["friction_angle"], p["unit_weight"], m=m0, c_root=c_root + suction_cohesion(p, m0))
    soil = valid & (slope <= max_soil_slope)
    stable = soil & (fs0 >= 1.0)
    return stable, {"cells_valid": int(valid.sum()), "cells_rock_too_steep": int((valid & ~(slope <= max_soil_slope)).sum()),
                    "cells_already_unstable_dry": int((soil & ~(fs0 >= 1.0)).sum()), "cells_mobilisable": int(stable.sum())}


def soil_depth_field(slope_deg, p, slope_dependent=True):
    zmax, zmin = p["soil_depth_max"], p["soil_depth_min"]
    if not slope_dependent:
        z = np.full(slope_deg.shape, p["soil_depth"], "float32")
    else:
        f = np.clip(np.nan_to_num(slope_deg) / 50.0, 0, 1)
        z = (zmax - (zmax - zmin) * f).astype("float32")
    cap = p.get("regolith_cap_m")                                   # depth to bedrock (spatial ground): the slip surface cannot be deeper than the regolith
    if cap is not None:
        z = np.minimum(z, np.where(np.isfinite(cap), cap, z)).astype("float32")
    return z


def rain_failure_times(slope, valid, rain_mm_step, dt_s, p, z, min_slope=10.0, fields=None):
    """Returns t_fail_s (inf = never), min_fs, m_end, F history, and unstable-area-vs-time."""
    ga = green_ampt.run(rain_mm_step, dt_s, p["hydraulic_conductivity"], p["suction_head"], p["theta_s"], p["theta_i"], 1.0, m0=0.0)
    F = ga["F_m"]                                          # (T,) scalar series, independent of z
    # spatially varying rain: p['rain_scale'] (ny, nx) multiplies the storm depth per cell (gridded ERA5/IMERG totals). Green-Ampt is not linear in rain, so the
    # front is run for a handful of representative scale values and each cell takes its nearest one.
    rs = p.get("rain_scale"); F_cell = None
    if rs is not None and np.ndim(rs) == 2 and np.isfinite(rs).any():
        reps = np.unique(np.round(np.nanpercentile(rs, [5, 25, 50, 75, 95]), 2)); idx = np.abs(np.nan_to_num(rs, nan=1.0)[..., None] - reps).argmin(-1)
        Fb = np.stack([green_ampt.run(rain_mm_step * r, dt_s, p["hydraulic_conductivity"], p["suction_head"], p["theta_s"], p["theta_i"], 1.0, m0=0.0)["F_m"] for r in reps])
        F_cell = (Fb, idx)
    dth = max(p["theta_s"] - p["theta_i"], 1e-6)
    slope_e, c_root, wt, m_scale = _eff(slope, p, fields)
    m0 = green_ampt.m_from_water_table(z, wt)
    t_fail = np.full(slope.shape, np.inf, "float32")
    min_fs = np.full(slope.shape, np.inf, "float32")
    area_t = np.zeros(len(F))
    failed = np.zeros(slope.shape, bool)
    cand = valid & (slope >= min_slope)
    col = None
    if p.get("pressure_model") == "iverson":                  # TRIGRS-type transient pressure head instead of the Green-Ampt wetting front (opt-in, CPU-heavy on big areas)
        if float(np.count_nonzero(cand)) * len(F) ** 2 / 2.0 > 6e10:
            raise ValueError("the Iverson pressure model is too heavy for this area and storm length (cells x steps^2); use a smaller area, a shorter storm or the Green-Ampt model")
        col = IVS.Column(rain_mm_step, dt_s, p["hydraulic_conductivity"], slope_e, z, wt, float(p.get("diffusivity_ratio", 100.0)))
    for t in range(len(F)):
        Ft = F[t] if F_cell is None else F_cell[0][:, t][F_cell[1]]
        m = np.maximum(m0, np.clip(Ft / np.maximum(dth * z, 1e-9), 0.0, 1.0)) if col is None else col.m(t)
        if m_scale is not None:
            m = np.clip(m * m_scale, 0.0, 1.0)                       # subsurface drainage lowers the saturated fraction
        fs = INF.factor_of_safety(slope_e, z, p["effective_cohesion"], p["friction_angle"], p["unit_weight"], m=m, c_root=c_root + suction_cohesion(p, m))
        fs = np.where(cand, fs, np.inf)
        min_fs = np.minimum(min_fs, np.where(np.isfinite(fs), fs, np.inf))
        new = (fs < 1.0) & ~failed
        t_fail[new] = (t + 1) * dt_s
        failed |= new
        area_t[t] = failed.sum()
    return t_fail, np.where(np.isinf(min_fs), np.nan, min_fs), area_t, ga


def clusters_min_size(mask, min_cells):
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes >= min_cells
    return keep[lab]


def seismic_failures(slope, valid, pga_g, p, z, d_crit_cm=5.0, min_slope=10.0, fields=None):
    """Coseismic failure: Newmark displacement (Jibson 2007 PGA regression) > d_crit on a dry slope."""
    slope_e, c_root, _, _ = _eff(slope, p, fields)
    ky = NM.yield_coefficient(slope_e, z, p["effective_cohesion"], p["friction_angle"], p["unit_weight"], m=0.0, c_root=c_root)
    d = NM.jibson2007_displacement_cm(ky, pga_g)
    fail = valid & (slope >= min_slope) & np.isfinite(d) & (d >= d_crit_cm)
    # already statically unstable (ky<=0) and shaken: fails too
    return fail, d, ky


def jb81_pga_g(magnitude, dist_km):
    """Joyner & Boore (1981) PGA (g, mean of horizontal) for M5.0-7.7 at <= 370 km; no site amplification.
    log10 y = -1.02 + 0.249 M - log10 r - 0.00255 r,  r = sqrt(d^2 + 7.3^2). sigma(log10) ~ 0.26. Screening only."""
    r = np.sqrt(np.asarray(dist_km, float) ** 2 + 7.3 ** 2)
    return 10.0 ** (-1.02 + 0.249 * magnitude - np.log10(r) - 0.00255 * r)


# Boore, Stewart, Seyhan & Atkinson (2014) NGA-West2, PGA row of the published table (global anelastic term, Dc3 = 0)
_B14 = dict(e0=0.4473, e1=0.4856, e2=0.2459, e3=0.4539, e4=1.431, e5=0.05053, e6=-0.1662, Mh=5.5, c1=-1.134, c2=0.1917, c3=-0.008088, h=4.5,
            c=-0.6, Vc=1500.0, f4=-0.15, f5=-0.00701, Mref=4.5, Rref=1.0, Vref=760.0, f1=0.0, f3=0.1, R1=110.0, R2=270.0, dfr=0.1, dfv=0.07,
            phi1=0.695, phi2=0.495, tau1=0.398, tau2=0.348)
_MECH = {"U": "e0", "SS": "e1", "NS": "e2", "RS": "e3"}


def bssa14_pga_g(magnitude, rjb_km, vs30=760.0, mech="U", return_sigma=False):
    """Boore et al. (2014) median PGA (g, RotD50) for shallow crustal earthquakes: M3-8.5, Rjb <= 400 km, Vs30 150-1500 m/s, with the nonlinear site term.
    Rjb = distance to the surface projection of the rupture (what pga_field computes). Optionally returns the total sigma (ln units)."""
    B = _B14; M = float(magnitude); rjb = np.maximum(np.asarray(rjb_km, float), 0.0); vs = np.clip(np.asarray(vs30, float), 150.0, 1500.0)
    dm = M - B["Mh"]
    fe = B[_MECH.get(mech, "e0")] + (B["e4"] * dm + B["e5"] * dm ** 2 if M <= B["Mh"] else B["e6"] * dm)
    R = np.sqrt(rjb ** 2 + B["h"] ** 2)
    fp = (B["c1"] + B["c2"] * (M - B["Mref"])) * np.log(R / B["Rref"]) + B["c3"] * (R - B["Rref"])
    pga_r = np.exp(fe + fp)                                                    # rock reference (Vs30 = 760): the site term is zero there
    flin = B["c"] * np.log(np.minimum(vs, B["Vc"]) / B["Vref"])
    f2 = B["f4"] * (np.exp(B["f5"] * (np.minimum(vs, 760.0) - 360.0)) - np.exp(B["f5"] * (760.0 - 360.0)))
    fnl = B["f1"] + f2 * np.log((pga_r + B["f3"]) / B["f3"])
    y = np.exp(fe + fp + flin + fnl)
    if not return_sigma:
        return y
    mm = np.clip(M - 4.5, 0.0, 1.0); tau = B["tau1"] + (B["tau2"] - B["tau1"]) * mm; phi = B["phi1"] + (B["phi2"] - B["phi1"]) * mm
    phi = phi + B["dfr"] * np.clip(np.log(np.maximum(rjb, 1e-3) / B["R1"]) / np.log(B["R2"] / B["R1"]), 0, 1)
    phi = phi - B["dfv"] * np.clip(np.log(500.0 / vs) / np.log(500.0 / 200.0), 0, 1)
    return y, np.sqrt(tau ** 2 + phi ** 2)


# Abrahamson et al. (2016) "BC Hydro" subduction model, intraslab branch, PGA row (point source at the hypocentre; Dc1 = -0.3, forearc/no back-arc term)
_BCH = dict(vlin=865.1, b=-1.186, th1=4.2203, th2=-1.35, th3=0.1, th4=0.9, th6=-0.0012, th9=0.4, th10=3.12, th11=0.013, th12=0.98, th13=-0.0135, th14=-0.4,
            c4=10.0, C1=7.8, n=1.18, c=1.88, dc1=-0.3, sigma=0.74, th7=1.0988, th8=-1.42)


def bchydro_slab_pga_g(magnitude, dist_km, depth_km, vs30=1000.0, return_sigma=False, backarc=False):
    """Intermediate-depth (intraslab) PGA, e.g. the Hindu Kush earthquakes at 150-250 km depth. dist_km = epicentral distance; the hypocentral distance
    sqrt(d^2 + depth^2) is used. Valid M5-8, hypocentral distance 60-500 km."""
    B = _BCH; M = float(magnitude); r = np.sqrt(np.asarray(dist_km, float) ** 2 + float(depth_km) ** 2); vs = np.asarray(vs30, float)
    dmag = B["C1"] + B["dc1"]
    fmag = B["th1"] + B["th4"] * B["dc1"] + (0.0 if M > dmag else B["th4"] * (M - dmag)) + B["th13"] * (10.0 - M) ** 2
    fdist = (B["th2"] + B["th14"] + B["th3"] * (M - B["C1"])) * np.log(r + B["c4"] * np.exp((M - 6.0) * B["th9"])) + B["th6"] * r + B["th10"]
    fdep = B["th11"] * (min(float(depth_km), 120.0) - 60.0)
    if backarc:                                              # faster attenuation behind the volcanic front: theta7 + theta8 ln(max(R, 85) / 40)
        fdep = fdep + B["th7"] + B["th8"] * np.log(np.maximum(r, 85.0) / 40.0)
    pga1000 = np.exp(fmag + fdist + fdep + (B["th12"] + B["b"] * B["n"]) * np.log(1000.0 / B["vlin"]))
    arg = np.minimum(vs, 1000.0) / B["vlin"]
    site = B["th12"] * np.log(arg) + np.where(vs >= B["vlin"], B["b"] * B["n"] * np.log(arg),
                                              -B["b"] * np.log(pga1000 + B["c"]) + B["b"] * np.log(pga1000 + B["c"] * arg ** B["n"]))
    y = np.exp(fmag + fdist + fdep + site)
    return (y, B["sigma"]) if return_sigma else y


SLAB_DEPTH_KM = 40.0     # events deeper than this are intraslab (Hindu Kush, Pamir), shallower use the crustal model
# Regional adjustment of the global intraslab model for the Hindu Kush-Pamir slab: BC Hydro minus USGS ShakeMap PGA = +0.65 ln units (sd 0.34 after removing it;
# 120 events, 1.5 M cells, flat with distance), see docs/validation/pga_validation.json. It is a fit to the ShakeMap PRODUCT, not to station records.
SLAB_REGIONAL_LN = -0.65


def pga_model(magnitude, dist_km, vs30=None, model="bssa14", depth_km=None):
    """PGA (g) from the chosen ground-motion model. 'jb81' ignores the site; 'bssa14' uses vs30 (array or scalar, default 760 = rock);
    'auto' = bchydro_slab for depth > SLAB_DEPTH_KM else bssa14."""
    if model == "jb81":
        return jb81_pga_g(magnitude, dist_km)
    if model == "auto" and depth_km is not None and depth_km > SLAB_DEPTH_KM:
        return bchydro_slab_pga_g(magnitude, dist_km, depth_km, 760.0 if vs30 is None else vs30) * np.exp(SLAB_REGIONAL_LN)
    return bssa14_pga_g(magnitude, dist_km, 760.0 if vs30 is None else vs30)


def rupture_length_km(magnitude):
    """Wells & Coppersmith (1994) all-slip-type subsurface rupture length: log10 L = -2.44 + 0.59 M."""
    return 10.0 ** (-2.44 + 0.59 * magnitude)


def pga_field(grid_shape, affine, epicentre_xy_m, magnitude, fault_xy_m=None, edt_cell_m=None, vs30=None, model="auto", depth_km=None):
    """PGA (g) per cell from distance to a rupture line (fault trace segment centred on the epicentre, else the point).
    model 'auto' (default: BSSA14 crustal, or BC Hydro intraslab when depth_km > 40), 'bssa14', or 'jb81' (the 1981 screening relation)."""
    from rasterio.features import rasterize
    from shapely.geometry import LineString, Point
    L = rupture_length_km(magnitude) * 1000.0
    ex, ey = epicentre_xy_m
    deep = model == "auto" and depth_km is not None and depth_km > SLAB_DEPTH_KM          # intraslab: a point source at the hypocentre, no rupture line
    if deep:
        fault_xy_m = None
    if fault_xy_m is not None and len(fault_xy_m) >= 2:
        line = LineString(fault_xy_m)
        s0 = line.project(Point(ex, ey))
        seg = _substring(line, max(0, s0 - L / 2), min(line.length, s0 + L / 2))
        geom = seg if seg is not None and seg.length > 0 else Point(ex, ey)
    else:
        geom = Point(ex, ey)
    # distance from every cell centre to the rupture, in km
    if geom.geom_type == "Point":
        h, w = grid_shape
        cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
        xs, ys = affine * (cols, rows)
        d = np.hypot(xs - geom.x, ys - geom.y) / 1000.0
    else:
        mask = rasterize([(geom.buffer(abs(affine.a) * 0.75), 1)], out_shape=grid_shape, transform=affine, fill=0, dtype="uint8")
        d = ndimage.distance_transform_edt(mask == 0) * abs(affine.a) / 1000.0
    return pga_model(magnitude, d, vs30, model, depth_km).astype("float32"), d.astype("float32"), geom


def _substring(line, a, b):
    from shapely.ops import substring
    try:
        return substring(line, a, b)
    except Exception:
        return None
