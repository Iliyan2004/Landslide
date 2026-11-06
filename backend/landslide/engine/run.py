"""Tier-3 physics run: rain and/or earthquake -> failure timing -> time-stepped runout -> hazard, impacts, loss.

Everything is screening-grade: soil strength and Voellmy friction are SCENARIO values inside explicit ranges, nothing is
calibrated to an observed event (validation_status: screening_only)."""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np
from pyproj import Transformer
from rasterio.enums import Resampling
from scipy import ndimage
from ..app import paths, rasters, pipeline as P, rainfall as RF, layers as LY, custom_dem as CD
from ..data.preprocessing import aoi as AOI, terrain
from ..errors import GateError, InsufficientData
from . import loss as LS, flow as FL, trigger as TR, interventions as IV, ground as GR, access as AC, site as SITE, antecedent as ANT, ensemble as ENSM, wetness as WET, census as CEN
from .thermal import Governor

MAX_PHYS_CELLS = 700_000
MAX_PHYS_RES_M = 120.0
MAX_STEPS = 600_000
import os
_DBG = bool(os.environ.get('LS_DEBUG'))
FRAMES = 120
IMP = {"rho": 1800.0, "cost_m2": 35000.0,   # cost_m2/floors: the old flat valuation, now unused (engine/loss.py values loss as SAILAB does)
        "dr": [0, .05, .2, .55, 1.0], "med_kpa": [5, 15, 40, 100], "beta": 0.6,
       "burial_m": [0.3, 1.0, 2.0, 4.0], "floors": 1, "persons_per_building_note": "population raster used instead"}


# Fragility medians scale with the construction class of the census (assumed multipliers of the pakka medians; no Pakistani damage data to fit them)
CLASS_SCALE = {"pakka": 1.0, "semi": 0.6, "kacha": 0.3}


def _ds_probs(p_kpa, scale=1.0):
    from scipy.stats import norm
    ex = np.array([norm.cdf(np.log(max(p_kpa, 1e-6) / (m * scale)) / IMP["beta"]) for m in IMP["med_kpa"]])
    pr = np.concatenate([[1 - ex[0]], ex[:-1] - ex[1:], [ex[-1]]])
    return np.clip(pr, 0, 1)


def building_damage(hmax, vmax, area_m2, mix=None):
    """Expected damage ratio from dynamic-pressure fragility, floored by burial depth. All thresholds are ASSUMED.
    mix = (pakka, semi, kacha) shares from the district census: the damage probabilities are the mix-weighted average over the three classes (default: all pakka)."""
    p = IMP["rho"] * vmax ** 2 / 1e3; mix = mix or (1.0, 0.0, 0.0); pr = np.zeros(5)
    for share, cls in zip(mix, ("pakka", "semi", "kacha")):
        if share <= 0:
            continue
        pc = _ds_probs(p, CLASS_SCALE[cls]) if hmax >= 0.3 else np.array([1.0, 0, 0, 0, 0])
        floor_ds = int(np.searchsorted(IMP["burial_m"], hmax, side="right"))   # 0..4
        if floor_ds > 0:
            p2 = np.zeros(5); p2[floor_ds:] = pc[floor_ds:]; p2[floor_ds] += pc[:floor_ds].sum(); pc = p2
        pr += share * pc
    dr = float(np.dot(pr, IMP["dr"]))
    return dr, int(np.argmax(pr)), dr * area_m2 * IMP["floors"] * IMP["cost_m2"]        # third value: old flat valuation, kept for callers; _exposure now uses engine/loss.py


def execute(geom, params, run_dir, progress=lambda s, f: None):
    try:
        return _execute(geom, params, run_dir, progress)
    finally:
        try:
            from .flow_torch import release_gpu_memory
            release_gpu_memory()
        except Exception:
            pass


def _execute(geom, params, run_dir, progress):
    t_start = time.time()
    run_dir = Path(run_dir); run_dir.mkdir(parents=True, exist_ok=True)
    warns = []
    bbox, area_km2, w0 = AOI.validate_geojson(geom, max_area_km2=P.MAX_AOI_KM2)
    warns += list(w0)
    epsg, w1 = AOI.select_analysis_crs(bbox); warns += list(w1)
    dem_path, min_res, dem_note = CD.resolve(params, bbox, paths.get("DEM"), P.MIN_RES_M)
    if dem_note:
        warns.append(dem_note)
    step = 10.0 if min_res >= 10.0 else min_res
    res = max(min_res, float(np.ceil(np.sqrt(area_km2 * 1e6 / MAX_PHYS_CELLS) / step) * step))
    if res > MAX_PHYS_RES_M:
        raise GateError([f"{area_km2:,.0f} km2 is too large for a physics run (cells would be {res:.0f} m, slope is smoothed away). "
                         f"Draw an area of <= {MAX_PHYS_CELLS*MAX_PHYS_RES_M**2/1e6:,.0f} km2, or use Tier 1/2 for large areas."])
    if res > min_res:
        warns.append(f"Run uses {res:.0f} m cells (area {area_km2:,.0f} km2); a smaller area gives {min_res:.0f} m.")
    progress("terrain", 0.04)
    grid = rasters.make_grid(bbox, epsg, res)
    dem = rasters.read(dem_path, grid, Resampling.average if res > min_res else Resampling.bilinear)
    if dem is None:
        raise InsufficientData(["DEM coverage for this AOI"], "terrain")
    inside = rasters.polygon_mask(geom, grid)
    valid = inside & np.isfinite(dem)
    if valid.sum() < 100:
        raise GateError(["AOI has fewer than 100 valid DEM cells"])
    dem_f = np.where(np.isfinite(dem), dem, np.nanmedian(dem))
    slope = terrain.slope_aspect(dem_f, res, res)["slope_deg"].astype("float32")
    ny, nx = dem.shape; dx = res

    mode = params.get("mode", "rain")
    spec, hp = P.build_spec(params)
    q = float(params.get("strength_quantile", 0.3))
    extras, extras_rep = _extras(params, mode, grid, dem_f, valid, res)
    sp, ground_rep, ante_rep = _scenario(spec, q, params, mode, grid, slope.shape, extras)
    sp = dict(sp); sp["pressure_model"] = params.get("pressure_model", "green_ampt"); sp["diffusivity_ratio"] = float(params.get("diffusivity_ratio", 100.0))
    z = TR.soil_depth_field(slope, sp, bool(params.get("depth_vs_slope", True)))
    min_slope = float(params.get("min_slope_deg", 12))
    iv = params.get("interventions") or {}
    fields = IV.nbs_fields(iv.get("nbs"), grid, slope.shape, valid)
    barrier_add, barrier_info = IV.barriers_mask(iv.get("protection"), grid, epsg, slope.shape, slope)
    mob, mob_stats = TR.mobilisable_mask(slope, valid, z, sp, float(params.get("max_soil_slope_deg", 45)), fields)
    events = []                      # (time_s, mask)
    series = None
    area_t = None
    summary = {"area_km2": area_km2, "resolution_m": res, "grid": [ny, nx], "mode": mode}

    progress("trigger", 0.12)
    rain_fs = None
    t_fail = np.full(slope.shape, np.inf, "float32")
    if mode in ("rain", "both"):
        series = params["rain"]
        dt_s = 900
        steps = RF.to_step_depths(series["times_h"], series["rate_mm_h"], dt_s)
        if len(steps) > 4 * 24 * 14:
            raise GateError(["rainfall series longer than 14 days; shorten the window"])
        t_fail, rain_fs, area_t, ga = TR.rain_failure_times(slope, mob, steps, dt_s, sp, z, min_slope, fields)
        summary["rain"] = {"source": series.get("source"), "total_mm": float(steps.sum()), "peak_mm_h": float(max(series["rate_mm_h"])),
                           "duration_h": float(series["times_h"][-1])}
    pga = None; quake_vis = None
    if mode in ("quake", "both"):
        qk = params["quake"]
        pga, dist_km, rup, vs30_src = _quake_field(qk, grid, epsg, slope, qk.get("gmpe", "auto"), float(qk.get("depth_km", 15.0)))
        _tr = Transformer.from_crs(epsg, 4326, always_xy=True)
        _pts = [rup.coords[0]] if rup.geom_type == "Point" else list(rup.coords)
        quake_vis = {"epi": [qk["lon"], qk["lat"]], "mag": float(qk["magnitude"]), "time_s": float(qk.get("time_h", 0.0)) * 3600.0,
                     "rupture": [list(_tr.transform(x, y)) for x, y in (_pts if len(_pts) <= 60 else _pts[:: max(1, len(_pts) // 60)])]}
        fail_q, dnew, ky = TR.seismic_failures(slope, mob, pga, sp, z, float(qk.get("d_crit_cm", 5.0)), min_slope, fields)
        tq = float(qk.get("time_h", 0.0)) * 3600.0
        t_fail = np.where(fail_q & (t_fail > tq), tq, t_fail).astype("float32")
        summary["quake"] = {"magnitude": qk["magnitude"], "epicentre": [qk["lon"], qk["lat"]], "pga_g_max": float(np.nanmax(pga[valid])),
                            "pga_g_mean": float(np.nanmean(pga[valid])), "rupture_km": float(TR.rupture_length_km(qk["magnitude"])),
                            "newmark_cm_p95": float(np.nanpercentile(dnew[valid & np.isfinite(dnew)], 95)) if np.isfinite(dnew[valid]).any() else None,
                            "model": ("Joyner-Boore 1981 PGA (no site term)" if qk.get("gmpe") == "jb81" else (f"BC Hydro (Abrahamson 2016) intraslab PGA, depth {qk.get('depth_km', 15)} km, Vs30 site term ({vs30_src})" if float(qk.get("depth_km", 15)) > TR.SLAB_DEPTH_KM else f"Boore et al. 2014 NGA-West2 PGA with Vs30 site term ({vs30_src})"))
                                     + " + Wells-Coppersmith rupture length + Jibson 2007 Newmark"}
    failing = np.isfinite(t_fail)
    failing = TR.clusters_min_size(failing, int(params.get("min_cluster_cells", 3)))
    t_fail = np.where(failing, t_fail, np.inf).astype("float32")
    n_fail = int(failing.sum())
    if fields is not None or barrier_info:
        summary["interventions"] = {"nbs": {k: v for k, v in (iv.get("nbs") or {}).items() if k != "zone"}, "nbs_zone_cells": (fields or {}).get("zone_cells"),
                                    "barriers": barrier_info, "note": "scenario effect sizes set by the user; benefit = change against the unmitigated run"}
    summary["trigger"] = {"spatial_ground": ground_rep, "antecedent": ante_rep, "extras": extras_rep, "strength_quantile": q, "failing_cells": n_fail, "failing_area_km2": n_fail * dx * dx / 1e6,
                          "failing_frac_of_area": n_fail / max(1, int(valid.sum())), "soil_depth_mean_m": float(z[valid].mean()),
                          "params": {k: (round(v, 6) if isinstance(v, float) else (["per-cell", float(np.nanmean(v))] if isinstance(v, np.ndarray) else v)) for k, v in sp.items()},
                          "depth_vs_slope": bool(params.get("depth_vs_slope", True)), "mobilisable": mob_stats}
    if area_t is not None:
        summary["trigger"]["failed_cells_vs_time"] = {"t_h": [round((i + 1) * 0.25, 2) for i in range(len(area_t))],
                                                      "cells": [int(x) for x in area_t]}
    p_fail_arr = None
    n_ens = int(params.get("ensemble", 0) or 0)
    if n_ens > 0 and mode in ("rain", "both"):
        progress("ensemble", 0.17)
        ens = ENSM.pfail(slope, valid, steps, dt_s, spec, n_ens, int(params.get("seed", 0)), min_slope, float(params.get("max_soil_slope_deg", 45)),
                         bool(params.get("depth_vs_slope", True)), _post(params, mode, grid, slope.shape, extras), fields)
        ar = np.array(ens["cells_members"]) * dx * dx / 1e6; p_fail_arr = ens["p_fail"]
        summary["ensemble"] = {"members": n_ens, "device": ens["device"], "failing_area_km2": {"p05": float(np.percentile(ar, 5)), "p50": float(np.percentile(ar, 50)),
                               "p95": float(np.percentile(ar, 95)), "mean": float(ar.mean())}, "cells_p_fail_ge_0.5": int(np.nansum(p_fail_arr >= 0.5)),
                               "note": "every prior drawn independently (Latin hypercube); p_fail = share of members in which the cell fails; the main run is one scenario"}
    if n_fail / max(1, int(valid.sum())) > 0.05:
        warns.append(f"{100 * n_fail / max(1, int(valid.sum())):.0f}% of the area fails in this scenario. Real storms and earthquakes rarely fail more than a few percent of a catchment; "
                     "this usually means the strength scenario is too weak (the 'calibrated_reports_weak' preset, a low strength quantile, or a weak clayey soil) or the storm is extreme. "
                     "Read the runout as a worst case, not a forecast.")
    if n_fail == 0:
        summary["outcome"] = "no_failure"
        summary["note"] = "No cell reaches FS<1 under this scenario. Try heavier/longer rain, a weaker strength scenario, or a higher PGA."
        arrays = {"slope": slope, "fs_min": rain_fs if rain_fs is not None else np.full(slope.shape, np.nan, "float32")}
        if p_fail_arr is not None:
            arrays["p_fail"] = p_fail_arr
        _save_basic(run_dir, summary, warns, params, arrays, grid, geom, valid)
        return {"outcome": "no_failure", "summary": summary, "warnings": warns, "grid": grid, "run_dir": str(run_dir), "has_flow": False}

    # ---- event timeline & frames
    ev_times = sorted(set(float(t) for t in t_fail[failing]))
    t_first, t_last = ev_times[0], ev_times[-1]
    t0 = max(0.0, t_first - 120.0)
    t1 = t_last + 1800.0
    dt_frame = max(30.0, math.ceil((t1 - t0) / (FRAMES - 1) / 10.0) * 10.0)
    frame_t = t0 + dt_frame * np.arange(FRAMES)
    fl, backend = _make_flow(dem_f + barrier_add, dx, params.get('backend', 'auto'))
    gov = Governor()
    summary['backend'] = backend
    mu, xi, _ = TR.FAILURE_TYPES[params.get("failure_type", "debris_flow")]
    mu = float(params.get("mu", mu)); xi = float(params.get("xi", xi))
    entr = bool(params.get("entrain", True))
    if entr:
        e_depth = np.full(slope.shape, float(params.get("entrain_depth_m", 0.5)), "float32")
        cap = sp.get("regolith_cap_m")                                   # spatial ground: the flow cannot scour deeper than the regolith that exists
        if cap is not None:
            e_depth = np.minimum(e_depth, np.where(np.isfinite(cap), cap, e_depth))
        fl.set_erodible(np.where(valid & ~failing, e_depth, 0.0))
    rel_factor = float(params.get("release_factor", 1.0))
    released_total = 0.0
    frames_H, frames_vx, frames_vy = [], [], []
    stats_t = []
    sim_t = t0
    ev_i = 0
    next_f = 0
    steps_done = 0
    quiet = 0.0
    lam_series = _lambda_for(rain_fs, sp, z)
    progress("flow", 0.2)
    last_progress = time.time()
    while next_f < FRAMES:
        nxt_ev = ev_times[ev_i] if ev_i < len(ev_times) else math.inf
        nxt_fr = frame_t[next_f]
        target = min(nxt_ev, nxt_fr)
        # advance the flow (only if something is moving) up to `target`
        while sim_t < target - 1e-9:
            if fl.hmax_now() <= 0.02:
                sim_t = target; break
            dt = min(fl.cfl_dt(), target - sim_t)
            n = max(1, min(8, int((target - sim_t) / dt)))        # fixed-dt chunk: one host sync per chunk (GPU launch cost)
            lam_v = 0.0 if lam_series is None else lam_series
            if hasattr(fl, "advance"):
                fl.advance(dt, n, mu, xi, lam=lam_v, entrain=entr)
            else:
                for _ in range(n):
                    fl.step(dt, mu, xi, lam=lam_v, entrain=entr)
            sim_t += dt * n; steps_done += n
            gov.wait()
            quiet = quiet + dt * n if fl.vmax_now() < 0.2 else 0.0
            if _DBG and steps_done % 4000 < n:
                print(f'[dbg] {backend} step {steps_done} t={sim_t/3600:.3f}h Hmax={fl.hmax_now():.2f} Vmax={fl.vmax_now():.2f} quiet={quiet:.0f}', flush=True)
            if quiet > 300.0:
                sim_t = target; break                      # at rest: nothing changes until the next event
            if steps_done > MAX_STEPS:
                warns.append(f"step budget reached at t={sim_t/3600:.2f} h; later flow not simulated"); sim_t = target; ev_i = len(ev_times); break
            if time.time() - last_progress > 2.0:
                progress("flow", 0.2 + 0.6 * min(1.0, (sim_t - t0) / max(1.0, t1 - t0))); last_progress = time.time()
        if sim_t < target - 1e-9:
            sim_t = target
        if nxt_ev <= nxt_fr and ev_i < len(ev_times):
            m = failing & (t_fail == nxt_ev)
            fl.add_release(np.where(m, z * rel_factor, 0.0)); released_total += float((z * rel_factor)[m].sum() * dx * dx)
            quiet = 0.0; ev_i += 1
        else:
            h16, vx16, vy16 = fl.snapshot()
            frames_H.append(h16); frames_vx.append(vx16); frames_vy.append(vy16)
            h = h16.astype("float32")
            stats_t.append((float((h > 0.1).sum() * dx * dx / 1e6), float(h.max()), float(h.sum() * dx * dx)))
            next_f += 1
    progress("impact", 0.82)
    H = np.stack(frames_H); VX = np.stack(frames_vx); VY = np.stack(frames_vy)
    fin = fl.final()
    hmax, vmax = fin["Hmax"], fin["Vmax"]
    deposit = np.maximum(fin["dZ"], 0).astype("float32")      # net bed gain = deposition
    scour = np.maximum(-fin["dZ"], 0).astype("float32")       # net bed loss = scar + scour
    wet = hmax > 0.3
    # ---- summary
    from collections import OrderedDict
    reach_cells = int(wet.sum())
    rel = failing
    run_len = _runout_length(rel, wet, dx)
    summary["flow"] = {"failure_type": params.get("failure_type", "debris_flow"), "mu": mu, "xi": xi, "entrainment": entr,
                       "released_volume_m3": released_total, "entrained_volume_m3": fin["ent_vol"],
                       "final_flow_volume_m3": float(fin["H"].sum() * dx * dx), "impacted_area_km2": reach_cells * dx * dx / 1e6,
                       "max_depth_m": float(hmax.max()), "max_speed_ms": float(vmax.max()), "max_runout_m": run_len, "runout_stats_m": runout_stats(rel, wet, dx),
                       "mass_check_m3": float(released_total + fin["ent_vol"] - (fin["H"].sum() * dx * dx)),
                       "frame_interval_s": dt_frame, "window_h": [t0 / 3600, t1 / 3600],
                       "note": "Voellmy local-inertial solver, friction is a scenario value, not calibrated"}
    # ---- exposure
    pop = P._count_layer("POPULATION", grid)
    summary["exposure"] = _exposure(geom, bbox, grid, epsg, hmax, vmax, H, pop, dx, frame_t, warns)
    arrays = {"slope": slope, "dem": np.where(valid, dem, np.nan).astype("float32"), "hmax": np.where(valid, hmax, np.nan),
              "vmax": np.where(valid, vmax, np.nan), "deposit": deposit, "scour": scour, "t_fail_h": np.where(failing, t_fail / 3600, np.nan).astype("float32"),
              "fs_min": rain_fs if rain_fs is not None else np.full(slope.shape, np.nan, "float32"),
              "z": z}
    if pga is not None:
        arrays["pga_g"] = np.where(valid, pga, np.nan).astype("float32")
    if p_fail_arr is not None:
        arrays["p_fail"] = p_fail_arr
    summary["outcome"] = "failure_and_runout"
    summary["elapsed_s"] = round(time.time() - t_start, 1)
    progress("save", 0.95)
    out = {"summary": summary, "warnings": warns, "grid": grid, "arrays": arrays, "valid": valid, "H": H, "VX": VX, "VY": VY,
           "frame_t": frame_t, "stats_t": stats_t, "series": series, "geom": geom, "bbox": bbox, "epsg": epsg, "run_dir": str(run_dir),
           "has_flow": True, "quake_vis": quake_vis, "exposure_detail": summary["exposure"].pop("_detail", None), "dx": dx, "outcome": "failure_and_runout"}
    return out


def _make_flow(dem_f, dx, backend="auto"):
    """GPU first (CUDA), numba CPU fallback. Frames/rasters are held in host RAM."""
    if backend in ("auto", "cuda"):
        try:
            from .flow_torch import FlowStateGPU, available
            if available():
                return FlowStateGPU(dem_f, dx), "cuda"
        except Exception as e:                           # driver / memory problems -> fall back, never fail the run
            print("[flow] GPU unavailable, using CPU:", e, flush=True)
    return FL.FlowState(dem_f, dx), "numba-cpu"


def _lambda_for(rain_fs, sp, z):
    """Pore-pressure ratio (fluidization): 0.8 x the wet fraction reached in the scenario (rain events only)."""
    return None if rain_fs is None else 0.6


def _post(params, mode, grid, shape, extras=None):
    """sp -> sp2 hook applying the optional spatial ground and antecedent wetness (used by the ensemble members)."""
    cache = {}
    def post(sp):
        if params.get("spatial_ground"):
            sp, _ = GR.apply(sp, grid, shape, cache=cache)
        _ant = (params.get("rain") or {}).get("antecedent_daily_mm") if mode in ("rain", "both") else None
        if _ant and params.get("antecedent", True):
            sp, _ = ANT.apply(sp, ANT.api(_ant))
        return extras(sp) if extras else sp
    return post


def _extras(params, mode, grid, dem_f, valid, res):
    """Optional physics that needs the terrain or the gridded rain: topographic water table (wetness_beta), suction cohesion (suction_kpa), per-cell rain
    (rain_field). Returns a function sp -> sp2 plus a report. All off by default."""
    rep = {}; beta = float(params.get("wetness_beta", WET.PARAMS["beta"])); twi = WET.twi_field(dem_f, valid, res) if beta != 0.0 else None
    scale = None
    if params.get("rain_field") and mode in ("rain", "both"):
        ser = params.get("rain") or {}
        try:
            from pyproj import Transformer
            lon0, lat0 = Transformer.from_crs(grid["crs"], 4326, always_xy=True).transform(*(grid["affine"] * (grid["width"] / 2, grid["height"] / 2)))
            scale = RF.era5_scale_field(grid, ser, ser.get("grid_lat", lat0), ser.get("grid_lon", lon0))
            rep["rain_field"] = None if scale is None else {"min": float(np.nanmin(scale)), "max": float(np.nanmax(scale)), "mean": float(np.nanmean(scale))}
        except Exception as e:
            rep["rain_field"] = f"unavailable: {str(e)[:80]}"
    suc = float(params.get("suction_kpa", 0.0)) * 1000.0
    zones = params.get("strength_zones") or []
    def post(sp):
        if zones:
            sp, rep["strength_zones"] = GR.apply_zones(sp, zones, grid, valid.shape)
        sp, r = WET.apply(sp, twi, valid, beta); rep["wetness"] = r
        if scale is not None:
            sp = dict(sp); sp["rain_scale"] = scale
        if suc:
            sp = dict(sp); sp["suction_pa"] = suc; rep["suction_kpa"] = suc / 1000.0
        return sp
    return post, rep


def _scenario(spec, q, params, mode, grid, shape, extras=None):
    """The ONE place the scenario parameter set is built (main run and the paired mitigation evaluation must agree):
    prior-range point -> optional spatially varying ground -> optional antecedent wetness from the storm's 30 prior days."""
    sp = TR.scenario_point(spec, q); ground_rep = ante_rep = None
    if params.get("spatial_ground"):
        sp, ground_rep = GR.apply(sp, grid, shape)
    _ant = (params.get("rain") or {}).get("antecedent_daily_mm") if mode in ("rain", "both") else None
    if _ant and params.get("antecedent", True):
        sp, ante_rep = ANT.apply(sp, ANT.api(_ant))
    if extras:
        sp = extras(sp)
    return sp, ground_rep, ante_rep


def _quake_field(qk, grid, epsg, slope=None, model="auto", depth_km=15.0):
    from pyproj import Transformer
    import geopandas as gpd
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    ex, ey = tr.transform(qk["lon"], qk["lat"])
    fault_xy = None
    if qk.get("snap_to_fault", True):
        try:
            g = gpd.read_file(paths.get("FAULTS_SHP"), bbox=(qk["lon"] - 1.5, qk["lat"] - 1.5, qk["lon"] + 1.5, qk["lat"] + 1.5)).to_crs(epsg)
            if len(g):
                from shapely.geometry import Point
                p = Point(ex, ey)
                lines = []
                for geom in g.geometry:
                    lines += list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
                best = min(lines, key=lambda l: l.distance(p))
                if best.distance(p) < 25_000:
                    fault_xy = list(best.coords)
        except Exception:
            fault_xy = None
    ny, nx = grid["height"], grid["width"]
    vs30, src = (SITE.vs30_field(grid, slope) if model != "jb81" else (None, "not used (jb81)"))
    pga, d, geom = TR.pga_field((ny, nx), grid["affine"], (ex, ey), float(qk["magnitude"]), fault_xy, vs30=vs30, model=model, depth_km=depth_km)
    return pga, d, geom, src


def runout_stats(release_mask, wet, dx):
    """Per-slide runout (m): for every connected flow body (release patch plus wet cells), the distance from the release cells to its furthest wet cell. Returns
    {n, mean_m, median_m, p90_m, max_m} (None when nothing ran out). The mean describes the typical slide; max_runout_m describes the worst one."""
    from scipy import ndimage as ndi
    body = wet | release_mask
    lab, n = ndi.label(body, structure=np.ones((3, 3)))
    if n == 0 or not release_mask.any():
        return None
    d = ndi.distance_transform_edt(~release_mask) * dx
    mx = np.asarray(ndi.maximum(np.where(wet, d, 0.0), lab, np.arange(1, n + 1))); has = np.asarray(ndi.sum(release_mask, lab, np.arange(1, n + 1))) > 0
    r = mx[has]
    if r.size == 0:
        return None
    return {"n": int(r.size), "mean_m": float(r.mean()), "median_m": float(np.median(r)), "p90_m": float(np.percentile(r, 90)), "max_m": float(r.max())}


def _runout_length(release_mask, wet, dx):
    if not wet.any() or not release_mask.any():
        return 0.0
    d = ndimage.distance_transform_edt(~release_mask) * dx
    return float(d[wet].max())


def _exposure(geom, bbox, grid, epsg, hmax, vmax, H, pop, dx, frame_t, warns):
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    inv = ~grid["affine"]
    ny, nx = hmax.shape
    ex = {}
    ex["population_source"] = "population raster (WorldPop, 90 m)"
    if pop is None or not np.nansum(np.nan_to_num(pop)) > 0:           # south of the raster: district density from the census instead
        try:
            vmask = rasters.polygon_mask(geom, grid); pop, share = CEN.population_field(grid, vmask)
            if share > 0:
                ex["population_source"] = f"2023 census district density (uniform within each district; {100 * share:.0f}% of the area covered)"
            else:
                pop = None; ex["population_source"] = "none: no raster and no census district for this area"
        except Exception as e:
            pop = None; ex["population_source"] = f"none ({str(e)[:50]})"
    if pop is not None:
        ex["population_in_impacted_cells"] = float(np.nan_to_num(pop)[hmax > 0.3].sum())
        ex["population_in_aoi"] = float(np.nan_to_num(pop).sum())
    b = LY.buildings(bbox, geom)
    r = LY.roads(bbox, geom)
    fac = LY.facilities(bbox, geom)
    # nearest-cell lookup with a 3x3 maximum (footprints are smaller than cells)
    hm3 = ndimage.maximum_filter(hmax, size=3); vm3 = ndimage.maximum_filter(vmax, size=3)

    def cell(lon, lat):
        x, y = tr.transform(lon, lat); c, rr = inv * (x, y)
        return int(rr), int(c)
    cost = 0.0; struct = 0.0; ds_count = [0] * 5; b_out = []
    try:                                                              # census housing mix per building (engine/census.py); national mean where the census has no row
        keys = CEN.districts_for([x["cx"] for x in b], [x["cy"] for x in b]) if b else []
    except Exception as e:
        keys = [None] * len(b); warns.append(f"Census housing data unavailable ({str(e)[:60]}): all buildings treated as pakka.")
    census_known = 0; kacha_sum = 0.0; hh_people = 0.0
    for bd, key in zip(b, keys):
        rr, cc = cell(bd["cx"], bd["cy"])
        if not (0 <= rr < ny and 0 <= cc < nx):
            continue
        h, v = float(hm3[rr, cc]), float(vm3[rr, cc])
        mix, known = CEN.housing_mix(key) if keys else ((1.0, 0.0, 0.0), False); hh = CEN.hh_size(key)[0] if keys else 0.0
        census_known += int(known); kacha_sum += mix[2]
        dr, ds, _ = building_damage(h, v, bd["area_m2"], mix)
        if ds >= 2:
            hh_people += hh
        c = LS.building_structure_loss(dr, bd["area_m2"], bd.get("height_m", 6.0))
        ds_count[ds] += 1; cost += c; struct += c
        bd["rr"], bd["cc"], bd["dmg"] = rr, cc, dr
    nb = len([x for x in b if "rr" in x])
    content = struct * LS.CONTENT_TO_STRUCTURE_RATIO
    agri_pkr, agri_cells = 0.0, 0
    lc = rasters.read(paths.get("LULC"), grid, Resampling.nearest)
    if lc is not None:
        crop = np.isfinite(lc) & (np.rint(np.nan_to_num(lc)) == 5)                      # ESRI land cover class 5 = crops
        agri_pkr, agri_cells = LS.agricultural_loss(np.where(crop, hmax, 0.0), dx * dx)
    ex.update({"buildings_in_aoi": nb, "buildings_damaged_ds_ge1": int(sum(ds_count[1:])), "buildings_ds_ge3": int(sum(ds_count[3:])),
               "damage_states_count": ds_count, "direct_loss_pkr": struct + content + agri_pkr,
               "loss_parts_pkr": {"structure": struct, "contents": content, "agriculture": agri_pkr}, "cropland_cells_damaged": agri_cells,
               "census": {"buildings_with_district_census": census_known, "mean_kacha_share": (kacha_sum / nb if nb else None), "people_in_buildings_ds_ge2_est": hh_people,
                          "note": "housing mix and household size from the 2023 census by district; Gilgit-Baltistan and Azad Kashmir have no row, so the national mean is used there; people = damaged buildings (DS >= 2) x district household size (assumes one household per footprint)"},
               "loss_note": LS.method_note()})
    # roads blocked
    blocked_m, total_m = 0.0, 0.0
    road_out = []; seg_xy, seg_bl = [], []
    for rd in r:
        pts = rd["coords_lonlat"]; hit = False; xy = []; bl = []
        for p0, p1 in zip(pts[:-1], pts[1:]):
            x0, y0 = tr.transform(*p0); x1, y1 = tr.transform(*p1)
            L = math.hypot(x1 - x0, y1 - y0); total_m += L; sb = False
            for f in (0.0, 0.5):
                rr, cc = cell(p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
                if 0 <= rr < ny and 0 <= cc < nx and hm3[rr, cc] >= 0.5:
                    sb = True
            if sb:
                blocked_m += L; hit = True
            if not xy:
                xy.append((x0, y0))
            xy.append((x1, y1)); bl.append(sb)
        rd["blocked"] = hit; seg_xy.append(xy); seg_bl.append(bl)
    ex.update({"road_length_km": total_m / 1000, "road_blocked_km": blocked_m / 1000})
    fac_hit = []
    for f in fac:
        rr, cc = cell(f["lon"], f["lat"])
        if 0 <= rr < ny and 0 <= cc < nx and hm3[rr, cc] >= 0.3:
            fac_hit.append({"kind": f["kind"], "name": f["name"], "depth_m": float(hm3[rr, cc])})
    ex["facilities_impacted"] = fac_hit
    try:
        pts = [(tr.transform(x["cx"], x["cy"])) for x in b if "rr" in x] + [tr.transform(f["lon"], f["lat"]) for f in fac]
        kinds = ["house"] * len([x for x in b if "rr" in x]) + [f["kind"] for f in fac]
        if pts and seg_xy:
            ex["access"] = AC.analyse(seg_xy, seg_bl, pts, kinds)
    except Exception as e:
        ex["access"] = {"error": str(e)[:120]}
    ex["_detail"] = {"buildings": b, "roads": r}
    return ex


def _save_basic(run_dir, summary, warns, params, arrays, grid, geom, valid):
    np.savez_compressed(Path(run_dir) / "arrays.npz", **{k: np.asarray(v, "float32") for k, v in arrays.items()})
    (Path(run_dir) / "summary.json").write_text(json.dumps({"summary": summary, "warnings": warns}, indent=1, default=str))



def stability_context(geom, params):
    """Everything the stability-only evaluations need (no flow): used to rank mitigation levers quickly."""
    bbox, area_km2, _ = AOI.validate_geojson(geom, max_area_km2=P.MAX_AOI_KM2)
    epsg, _ = AOI.select_analysis_crs(bbox)
    dem_path, min_res, _n = CD.resolve(params, bbox, paths.get("DEM"), P.MIN_RES_M)
    step = 10.0 if min_res >= 10.0 else min_res
    res = max(min_res, float(np.ceil(np.sqrt(area_km2 * 1e6 / MAX_PHYS_CELLS) / step) * step))
    if res > MAX_PHYS_RES_M:
        raise GateError([f"{area_km2:,.0f} km2 is too large for this evaluation"])
    grid = rasters.make_grid(bbox, epsg, res)
    dem = rasters.read(dem_path, grid, Resampling.average if res > min_res else Resampling.bilinear)
    if dem is None:
        raise InsufficientData(["DEM coverage for this AOI"], "terrain")
    valid = rasters.polygon_mask(geom, grid) & np.isfinite(dem)
    dem_f = np.where(np.isfinite(dem), dem, np.nanmedian(dem))
    slope = terrain.slope_aspect(dem_f, res, res)["slope_deg"].astype("float32")
    spec, _ = P.build_spec(params)
    extras, _ = _extras(params, "rain", grid, dem_f, valid, res)
    sp, _, _ = _scenario(spec, float(params.get("strength_quantile", 0.3)), params, "rain", grid, slope.shape, extras)
    z = TR.soil_depth_field(slope, sp, bool(params.get("depth_vs_slope", True)))
    series = params["rain"]
    steps = RF.to_step_depths(series["times_h"], series["rate_mm_h"], 900)
    return {"slope": slope, "valid": valid, "z": z, "sp": sp, "steps": steps, "grid": grid, "res": res,
            "min_slope": float(params.get("min_slope_deg", 12)), "max_soil": float(params.get("max_soil_slope_deg", 45)), "cluster": int(params.get("min_cluster_cells", 3))}


def failing_area(ctx, nbs_spec=None):
    fields = IV.nbs_fields(nbs_spec, ctx["grid"], ctx["slope"].shape, ctx["valid"]) if nbs_spec else None
    mob, st = TR.mobilisable_mask(ctx["slope"], ctx["valid"], ctx["z"], ctx["sp"], ctx["max_soil"], fields)
    tf, fs, area_t, _ = TR.rain_failure_times(ctx["slope"], mob, ctx["steps"], 900, ctx["sp"], ctx["z"], ctx["min_slope"], fields)
    fail = TR.clusters_min_size(np.isfinite(tf), ctx["cluster"])
    # unstable_*: every soil-bearing cell that is unstable at the end of the storm, INCLUDING slopes already unstable before it. This is the like-for-like measure
    # for comparing levers: a lever that strengthens a pre-existing unstable slope moves it out of this count, whereas "failing" (stable before, fails in the storm)
    # can rise because the lever turned unstable cells into cells that can fail (planting alone did that on the Gilgit area).
    soil = ctx["valid"] & (ctx["slope"] <= ctx["max_soil"])
    tf_all, _, _, _ = TR.rain_failure_times(ctx["slope"], soil, ctx["steps"], 900, ctx["sp"], ctx["z"], ctx["min_slope"], fields)
    unst = TR.clusters_min_size(np.isfinite(tf_all), ctx["cluster"])
    return {"failing_cells": int(fail.sum()), "failing_km2": float(fail.sum() * ctx["res"] ** 2 / 1e6), "mobilisable_cells": st["cells_mobilisable"],
            "unstable_cells": int(unst.sum()), "unstable_km2": float(unst.sum() * ctx["res"] ** 2 / 1e6)}
