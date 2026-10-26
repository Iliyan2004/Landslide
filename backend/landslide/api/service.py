"""Framework-independent service layer: every model run = gates -> compute -> manifest -> artifacts (§7, §11)."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .. import manifest as M
from ..data.preprocessing import aoi as AOI
from ..errors import GateError, InsufficientData
from ..models.stability import ensemble as ENS
from ..models.seismic import newmark as NM
from ..models.runout import empirical as RE
from ..models.sediment import hillslope_channel as SED
from ..models.monitoring import thresholds as TH

RUNS = Path("runs")
MODEL_VERSION = "1.0.0"
DISCLAIMER = "Screening-grade decision support. Not for engineering design or evacuation orders."


def _finish(model, aoi_hash, grid, params, summary, arrays, mode, warnings, run_root, sources=()):
    key = M.cache_key(model, MODEL_VERSION, list(sources), aoi_hash, grid, params)
    run_id = key[:32]                                         # deterministic => idempotent
    rdir = Path(run_root) / run_id
    results = []
    if arrays:
        rdir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(rdir / "arrays.npz", **arrays); results.append("arrays.npz")
    man = M.build_manifest(model, MODEL_VERSION, list(sources), aoi_hash, grid, parameter_mode=mode,
                           warnings=warnings + [DISCLAIMER], results=results, params=params, run_id=run_id)
    summary = json.loads(json.dumps(summary, default=_j))      # JSON-clean (no numpy) for API/JobStore consumers
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "summary.json").write_text(json.dumps(summary, indent=2))
    results.append("summary.json")
    M.write_manifest(rdir, man)
    return {"run_id": run_id, "manifest": man, "summary": summary}


def _j(o):
    if isinstance(o, np.ndarray): return o.tolist()
    if isinstance(o, (np.floating, np.integer)): return o.item()
    raise TypeError(type(o))


def validate_aoi(geojson):
    bbox, area, warn = AOI.validate_geojson(geojson)
    epsg, w2 = AOI.select_analysis_crs(bbox)
    return {"aoi_id": AOI.aoi_sha256(geojson)[:16], "aoi_sha256": AOI.aoi_sha256(geojson), "bbox": bbox,
            "area_km2": area, "analysis_crs": f"EPSG:{epsg}", "warnings": warn + w2}


def run_stability(req, progress=lambda s, f: None, run_root=RUNS):
    """req: {aoi_sha256, slope_deg (float|2D list), rain_mm_step [..], dt_s, params{...}, parameter_mode, n, seed}"""
    progress("gates", 0.1)
    spec, mode = req["params"], req.get("parameter_mode", "scenario_ensemble")
    slope = np.asarray(req["slope_deg"], float)
    if slope.ndim == 0:
        progress("ensemble", 0.4)
        res = ENS.run_point(float(slope), req["rain_mm_step"], req.get("dt_s", 3600), spec, mode, req.get("n", 500), req.get("seed", 0))
        summary = {k: v for k, v in res.items() if k not in ("fs_timeseries_pct", "min_fs", "t_min_index")}
        summary["fs_timeseries_pct"] = res["fs_timeseries_pct"]
        arrays = {"min_fs": res["min_fs"], "t_min_index": res["t_min_index"]}
    else:
        valid = np.isfinite(slope)
        progress("grid_ensemble", 0.4)
        g = ENS.run_grid(slope, req["rain_mm_step"], req.get("dt_s", 3600), spec, valid, mode, req.get("n", 50), req.get("seed", 0))
        arrays = g
        summary = {"min_fs_p50_stats": {"min": float(np.nanmin(g["min_fs_p50"])), "max": float(np.nanmax(g["min_fs_p50"]))},
                   "status": {"calibration": "not_calibrated", "validation": "screening_only", "not_for_engineering_design": True}}
    progress("manifest", 0.9)
    return _finish("infinite_slope_green_ampt", req["aoi_sha256"], req.get("grid", {}), {**req, "slope_deg": "<array>" if slope.ndim else float(slope)},
                   summary, arrays, mode, ["soil strength not measured" if mode == "scenario_ensemble" else "measured parameters supplied",
                                           "rainfall spatial scale much coarser than DEM"], run_root)


def run_seismic(req, progress=lambda s, f: None, run_root=RUNS):
    """Requires ground motion (PGA or acceleration series). Epicentre distance alone is refused."""
    if req.get("pga_g") is None and req.get("accel_ms2") is None:
        raise InsufficientData(["PGA_g or acceleration time history (ShakeMap/scenario)"], "M13")
    spec = req["params"]; check = {k: spec.get(k) for k in ("soil_depth", "effective_cohesion", "friction_angle")}
    miss = [k for k, v in check.items() if v is None]
    if miss:
        raise InsufficientData(miss, "M13")
    z, c, phi, g_ = spec["soil_depth"], spec["effective_cohesion"], spec["friction_angle"], spec.get("unit_weight", 18e3)
    m = spec.get("m", 0.0); b = req["slope_deg"]
    ay = float(NM.yield_acceleration(b, z, c, phi, g_, m))
    out = {"yield_acceleration_ms2": ay, "yield_coefficient": float(NM.yield_coefficient(b, z, c, phi, g_, m))}
    if req.get("accel_ms2") is not None:
        d, v = NM.newmark_displacement(req["accel_ms2"], req["dt"], ay)
        out.update(newmark_displacement_m=d, peak_block_velocity_ms=v, method="newmark_time_history")
    else:
        out["jibson2007_displacement_cm"] = float(NM.jibson2007_displacement_cm(ay / 9.80665, req["pga_g"]))
        out["method"] = "jibson2007_regression_screening"
    out["flags"] = ["liquefaction_not_covered", "displacement_is_a_modelled_proxy_not_observed_movement"]
    return _finish("pseudostatic_newmark", req["aoi_sha256"], {}, req, out, None, "measured_or_scenario", out["flags"], run_root)


def run_runout(req, progress=lambda s, f: None, run_root=RUNS):
    dem, src = np.asarray(req["dem"], float), np.asarray(req["source_mask"], bool)
    res = RE.ensemble_envelope(dem, req["dx"], req.get("dy", req["dx"]), src, req.get("volume_m3"),
                               tuple(req["alpha_range_deg"]), req.get("n", 20), req.get("seed", 0))
    freq = res["envelope_frequency_conditional_on_priors"]
    summary = {"max_envelope_frequency": float(freq.max()), "cells_ever_reached": int((freq > 0).sum()), "status": res["status"]}
    return _finish("empirical_reach_envelope", req["aoi_sha256"], {}, {k: v for k, v in req.items() if k != "dem"},
                   summary, {"envelope_frequency": freq}, "scenario_ensemble",
                   ["envelope not simulated extent", "no depth/velocity: use validated multiphase engine for those"], run_root)


def run_sediment(req, progress=lambda s, f: None, run_root=RUNS):
    out = {}
    if "rusle" in req:
        r = req["rusle"]; out["rusle"] = SED.rusle(np.asarray(r["R"]), np.asarray(r["K"]), np.asarray(r["LS"]), np.asarray(r["C"]), r.get("P", 1.0))
    if "hydraulics" in req:
        h = req["hydraulics"]
        tau = SED.bed_shear_manning(h["n"], np.asarray(h["V"]), np.asarray(h["h"]))
        qb = SED.mpm_bedload_per_width(tau, h["d50"])
        out["bedload_per_width_m2s_max"] = float(np.nanmax(qb))
        out["bedload_total_m3s"] = None if h.get("active_width_m") is None else float(np.nanmax(SED.total_bedload(qb, h["active_width_m"])))
        out["d50_note"] = "d50 must be MEASURED bed material; SoilGrids texture is not riverbed d50"
    if not out:
        raise InsufficientData(["rusle or hydraulics inputs"], "sediment")
    return _finish("sediment", req["aoi_sha256"], {}, req, json.loads(json.dumps(out, default=_j)), None, "scenario", [], run_root)


def run_watch(req):
    """Stateless watch evaluation. Never returns 'confirmed landslide'."""
    th = req["threshold"]
    ex = bool(TH.exceeds(th, req["duration_h"], req["intensity_mm_h"]))
    return TH.watch_state(ex, req.get("api_percentile"), req.get("forecast_exceeds"), req.get("hindcast_validated", False),
                          req.get("data_issued_utc"), instrument_alert=req.get("instrument_alert", False))
