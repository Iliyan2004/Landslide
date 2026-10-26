"""Tier T orchestrator (M08): Green-Ampt + infinite slope over scenario ensembles (methodology §6, §9.3).

Parameter priors are ALWAYS explicit: either measured scalars or {min,max[,dist]} scenario ranges. Output FS
percentiles and a *conditional-on-priors* fraction FS<1 — NOT a calibrated failure probability.
"""
from __future__ import annotations
import warnings
import numpy as np
from scipy.stats import qmc
from ...errors import GateError
from ...gates import check_geotech
from ..infiltration import green_ampt
from . import infinite_slope as inf

PARAMS = ("soil_depth", "effective_cohesion", "friction_angle", "hydraulic_conductivity",
          "water_table", "unit_weight", "root_cohesion", "suction_head", "theta_s", "theta_i")


def _is_range(v):
    return isinstance(v, dict) and "min" in v and "max" in v


def sample_parameters(spec: dict, n: int, seed=0):
    """Latin-hypercube sampling of range-valued params; scalars broadcast. Log-uniform for Ks."""
    rng_keys = [k for k, v in spec.items() if _is_range(v)]
    out = {k: np.full(n, float(v)) for k, v in spec.items() if not _is_range(v) and v is not None}
    if rng_keys:
        u = qmc.LatinHypercube(d=len(rng_keys), seed=seed).random(n)
        for j, k in enumerate(rng_keys):
            lo, hi = float(spec[k]["min"]), float(spec[k]["max"])
            if lo > hi:
                raise GateError([f"{k}: min>max"])
            if k == "hydraulic_conductivity" or spec[k].get("dist") == "loguniform":
                if lo <= 0:
                    raise GateError([f"{k}: log-uniform needs min>0"])
                out[k] = np.exp(np.log(lo) + u[:, j] * (np.log(hi) - np.log(lo)))
            else:
                out[k] = lo + u[:, j] * (hi - lo)
    return out


def validate_ranges(spec):
    lim = {"soil_depth": (0.05, 30), "effective_cohesion": (0, 1e6), "friction_angle": (5, 55),
           "hydraulic_conductivity": (1e-12, 1e-1), "water_table": (0, 100), "unit_weight": (10e3, 25e3),
           "theta_s": (0.2, 0.7), "theta_i": (0.01, 0.7), "root_cohesion": (0, 50e3), "suction_head": (0.01, 5)}
    bad = []
    for k, v in spec.items():
        if v is None or k not in lim:
            continue
        vals = [v["min"], v["max"]] if _is_range(v) else [v]
        for x in vals:
            if not lim[k][0] <= float(x) <= lim[k][1]:
                bad.append(f"{k}={x} outside plausible [{lim[k][0]}, {lim[k][1]}]")
    if bad:
        raise GateError(bad)


def run_point(slope_deg, rain_mm_step, dt_s, spec, mode="scenario_ensemble", n=500, seed=0):
    """Single-cell/slope ensemble. Returns FS(t) percentiles, min FS distribution & time of minimum."""
    check_geotech(spec, mode)
    validate_ranges(spec)
    n_eff = n if mode == "scenario_ensemble" else 1
    p = sample_parameters(spec, n_eff, seed)
    p.setdefault("unit_weight", np.full(n_eff, 18e3))
    p.setdefault("root_cohesion", np.zeros(n_eff))
    p.setdefault("suction_head", np.full(n_eff, 0.2))
    p.setdefault("theta_s", np.full(n_eff, 0.45))
    p.setdefault("theta_i", np.full(n_eff, 0.20))
    m0 = green_ampt.m_from_water_table(p["soil_depth"], p["water_table"])
    ga = green_ampt.run(rain_mm_step, dt_s, p["hydraulic_conductivity"], p["suction_head"],
                        p["theta_s"], p["theta_i"], p["soil_depth"], m0=m0)
    fs = inf.factor_of_safety(slope_deg, p["soil_depth"], p["effective_cohesion"], p["friction_angle"],
                              p["unit_weight"], m=ga["m"], c_root=p["root_cohesion"])
    min_fs = np.nanmin(fs, axis=0)
    t_min = np.nanargmin(np.where(np.isfinite(fs), fs, np.inf), axis=0)
    pct = {q: np.nanpercentile(fs, q, axis=1) for q in (5, 50, 95)}
    return {"fs_timeseries_pct": pct, "min_fs": min_fs, "t_min_index": t_min,
            "frac_fs_lt_1_conditional_on_priors": float(np.mean(min_fs < 1.0)),
            "min_fs_pct": {q: float(np.nanpercentile(min_fs, q)) for q in (5, 50, 95)},
            "mass_balance_max_abs_resid_m": float(np.max(np.abs(ga["mass_balance_residual_m"]))),
            "n_members": int(n_eff), "parameter_mode": mode,
            "status": {"calibration": "not_calibrated", "validation": "screening_only",
                       "not_for_engineering_design": True,
                       "note": "fraction FS<1 is conditional on the stated priors, NOT an annual probability"}}


def run_grid(slope_deg, rain_mm_step, dt_s, spec, valid_mask, mode="scenario_ensemble", n=100, seed=0):
    """Gridded min-FS ensemble: every ensemble member applied uniformly across cells (spatially constant
    parameter draw per member unless the user supplies per-cell arrays). Cells outside mask -> NaN."""
    check_geotech(spec, mode)
    validate_ranges(spec)
    p = sample_parameters(spec, n if mode == "scenario_ensemble" else 1, seed)
    for k, d in (("unit_weight", 18e3), ("root_cohesion", 0.0), ("suction_head", 0.2), ("theta_s", 0.45), ("theta_i", 0.2)):
        p.setdefault(k, np.full_like(p["soil_depth"], d))
    nmem = p["soil_depth"].size
    minfs = np.full((nmem,) + slope_deg.shape, np.nan)
    for i in range(nmem):
        m0 = green_ampt.m_from_water_table(p["soil_depth"][i], p["water_table"][i])
        ga = green_ampt.run(rain_mm_step, dt_s, p["hydraulic_conductivity"][i], p["suction_head"][i],
                            p["theta_s"][i], p["theta_i"][i], p["soil_depth"][i], m0=m0)
        fs_t = np.array([inf.factor_of_safety(slope_deg, p["soil_depth"][i], p["effective_cohesion"][i],
                         p["friction_angle"][i], p["unit_weight"][i], m=ga["m"][t, ...],
                         c_root=p["root_cohesion"][i]) for t in range(ga["m"].shape[0])])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN = NODATA cells, masked below
            minfs[i] = np.nanmin(fs_t, axis=0)
    minfs[:, ~valid_mask] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return _summ(minfs)


def _summ(minfs):
    return {"min_fs_p05": np.nanpercentile(minfs, 5, axis=0), "min_fs_p50": np.nanpercentile(minfs, 50, axis=0),
            "min_fs_p95": np.nanpercentile(minfs, 95, axis=0),
            "frac_lt1_conditional": np.nanmean(minfs < 1.0, axis=0)}
