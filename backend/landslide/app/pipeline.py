"""AOI pipeline: real rasters -> the existing physics modules -> arrays + summary + manifest (one run dir per request).

Everything here is screening-grade. Soil strength is ALWAYS a scenario range (gates.check_geotech); the national
susceptibility layer is an external ML product and is reported as such, never as a physical probability."""
from __future__ import annotations
import json
import numpy as np
from rasterio.enums import Resampling
from . import paths, rasters
from .. import manifest as M
from ..data.preprocessing import aoi as AOI, terrain, soil as SOIL
from ..errors import GateError, InsufficientData
from ..gates import check_geotech
from ..models.infiltration import green_ampt
from ..models.stability import ensemble as ENS, infinite_slope as INF
from ..models.seismic import newmark as NM
from ..models.runout import empirical as RE

VERSION = "1.1.0"
MAX_CELLS = 1_500_000          # interactive AOI budget; larger areas are coarsened, never refused
MIN_RES_M = 30.0               # DEM is 29 m: never present finer
MAX_AOI_KM2 = 1_200_000.0      # whole of Pakistan incl. disputed territory (~985k km2 in the boundary file)
MAX_SOURCES = 400
MAX_PHYSICS_RES_M = 150.0      # coarser than this slope is smoothed away: physics would be meaningless, so it is skipped

TEXTURES = list(SOIL.GA_PRIORS)
# Scenario presets (NOT measurements). Cohesion Pa, friction deg, depth m.
STRENGTH_PRESETS = {
    "colluvium_shallow": {"soil_depth": {"min": 0.5, "max": 2.0}, "effective_cohesion": {"min": 1e3, "max": 8e3},
                          "friction_angle": {"min": 26, "max": 36}},
    "calibrated_reports": {"soil_depth": {"min": 2.54, "max": 2.54}, "effective_cohesion": {"min": 916.0, "max": 916.0}, "friction_angle": {"min": 29.9, "max": 29.9}},   # point values fitted to the reports (Ch. 28); shallow-colluvium ranges do not apply
    "residual_soil": {"soil_depth": {"min": 1.0, "max": 4.0}, "effective_cohesion": {"min": 3e3, "max": 15e3},
                      "friction_angle": {"min": 22, "max": 34}},
    "weak_clayey": {"soil_depth": {"min": 1.0, "max": 3.0}, "effective_cohesion": {"min": 2e3, "max": 10e3},
                    "friction_angle": {"min": 15, "max": 26}},
}


def choose_resolution(area_km2, bbox):
    cells_at_min = area_km2 * 1e6 / MIN_RES_M ** 2
    if cells_at_min <= MAX_CELLS:
        return MIN_RES_M
    return float(np.ceil(np.sqrt(area_km2 * 1e6 / MAX_CELLS) / 10.0) * 10.0)


def build_spec(p):
    """Params dict from the UI -> explicit geotech ranges (gate-checked downstream)."""
    base = dict(STRENGTH_PRESETS[p.get("strength_preset", "colluvium_shallow")])
    for k in ("soil_depth", "effective_cohesion", "friction_angle"):
        if isinstance(p.get(k), dict):
            base[k] = p[k]
    tex = p.get("texture", "sandy loam")
    if tex not in SOIL.GA_PRIORS:
        raise GateError([f"unknown texture '{tex}'"])
    hp = SOIL.hydraulic_priors(tex, p.get("ks_factor", 10.0))
    base.update(hydraulic_conductivity=hp["hydraulic_conductivity"], suction_head=hp["suction_head"], theta_s=hp["theta_s"],
                theta_i=float(p.get("theta_i", 0.25)) , water_table={"min": 2.0, "max": 10.0},
                unit_weight=18e3, root_cohesion={"min": 0.0, "max": float(p.get("root_cohesion_max_pa", 5e3))})
    base["theta_i"] = min(base["theta_i"], base["theta_s"] - 0.02)
    return base, hp


def _gpu_ok():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def _pct_dim0(sorted_t, q):
    """Linear-interpolated percentile along dim 0 of an ascending-sorted tensor (NaN-free input)."""
    n = sorted_t.shape[0]
    pos = q / 100.0 * (n - 1)
    lo, hi = int(np.floor(pos)), int(np.ceil(pos))
    return sorted_t[lo] + (sorted_t[hi] - sorted_t[lo]) * (pos - lo)


def stability_grid(slope, valid, rain_mm_h, hours, spec, n, seed, device="auto", mobilise=True, max_soil_slope=45.0):
    """GPU first (torch/CUDA), then the NumPy path on host RAM/CPU. Same maths; results agree to float32 precision."""
    if device in ("auto", "cuda") and _gpu_ok() and slope.size >= 50_000:
        try:
            return _stability_grid_gpu(slope, valid, rain_mm_h, hours, spec, n, seed, mobilise, max_soil_slope)
        except Exception as e:                                   # out of GPU memory etc. -> fall back, never fail
            print("[stability] GPU path failed, using CPU:", str(e)[:120], flush=True)
    return _stability_grid_cpu(slope, valid, rain_mm_h, hours, spec, n, seed, mobilise, max_soil_slope)


def _stability_grid_gpu(slope, valid, rain_mm_h, hours, spec, n, seed, mobilise=True, max_soil_slope=45.0):
    import torch
    from ..units import GAMMA_W
    check_geotech(spec, "scenario_ensemble")
    ENS.validate_ranges(spec)
    p = ENS.sample_parameters(spec, n, seed)
    rain = np.full(int(hours), float(rain_mm_h))
    dev = torch.device("cuda")
    b = torch.deg2rad(torch.as_tensor(np.nan_to_num(slope, nan=0.0), device=dev, dtype=torch.float32))
    sb, cb = torch.sin(b), torch.cos(b)
    flat = torch.rad2deg(b) < INF.MIN_SLOPE_DEG
    vmask = torch.as_tensor(valid, device=dev)
    minfs = torch.empty((n,) + slope.shape, device=dev, dtype=torch.float32)
    for i in range(n):
        m0 = green_ampt.m_from_water_table(p["soil_depth"][i], p["water_table"][i])
        ga = green_ampt.run(rain, 3600, p["hydraulic_conductivity"][i], p["suction_head"][i], p["theta_s"][i], p["theta_i"][i],
                            p["soil_depth"][i], m0=m0)
        m = float(ga["m"].max())
        z, c, phi, g_, cr = (float(p[k][i]) for k in ("soil_depth", "effective_cohesion", "friction_angle", "unit_weight", "root_cohesion"))
        u = min(max(m, 0.0), 1.0) * GAMMA_W * z * cb ** 2
        sig = torch.clamp(g_ * z * cb ** 2 - u, min=0.0)
        fs = (c + cr + sig * float(np.tan(np.deg2rad(phi)))) / (g_ * z * sb * cb)
        f_i = torch.where(flat, torch.full_like(fs, 99.0), torch.nan_to_num(fs, nan=99.0, posinf=99.0))
        if mobilise:   # rain-triggered failures only: slope was stable before the event and carries soil (bare rock excluded)
            u0 = min(max(float(m0), 0.0), 1.0) * GAMMA_W * z * cb ** 2
            fs0 = (c + cr + torch.clamp(g_ * z * cb ** 2 - u0, min=0.0) * float(np.tan(np.deg2rad(phi)))) / (g_ * z * sb * cb)
            keep = (fs0 >= 1.0) & (torch.rad2deg(b) <= max_soil_slope)
            f_i = torch.where(keep, f_i, torch.full_like(f_i, 99.0))
        minfs[i] = f_i
    minfs = torch.where(vmask, minfs, torch.full_like(minfs, float("nan")))
    srt = torch.sort(torch.nan_to_num(minfs, nan=1e9), dim=0).values
    res = {"min_fs_p05": _pct_dim0(srt, 5), "min_fs_p50": _pct_dim0(srt, 50), "min_fs_p95": _pct_dim0(srt, 95),
           "frac_lt1": (minfs < 1.0).float().mean(0)}
    out = {}
    for k, v in res.items():
        a = v.cpu().numpy(); a[~valid] = np.nan; out[k] = a
    del minfs, srt, res
    torch.cuda.empty_cache()
    return out, p


def _stability_grid_cpu(slope, valid, rain_mm_h, hours, spec, n, seed, mobilise=True, max_soil_slope=45.0):
    """Per-cell min-FS ensemble. FS is non-increasing in saturation m and m(t) is non-decreasing for one member
    (wetting front only advances), so min over time is the FS at the final m: one evaluation per member."""
    check_geotech(spec, "scenario_ensemble")
    ENS.validate_ranges(spec)
    p = ENS.sample_parameters(spec, n, seed)
    rain = np.full(int(hours), float(rain_mm_h))
    minfs = np.full((n,) + slope.shape, np.nan, dtype="float32")
    for i in range(n):
        m0 = green_ampt.m_from_water_table(p["soil_depth"][i], p["water_table"][i])
        ga = green_ampt.run(rain, 3600, p["hydraulic_conductivity"][i], p["suction_head"][i], p["theta_s"][i], p["theta_i"][i],
                            p["soil_depth"][i], m0=m0)
        m_end = float(ga["m"].max())
        f_i = INF.factor_of_safety(slope, p["soil_depth"][i], p["effective_cohesion"][i], p["friction_angle"][i],
                                   p["unit_weight"][i], m=m_end, c_root=p["root_cohesion"][i])
        if mobilise:   # rain-triggered failures only: stable before the event and soil-bearing (bare rock excluded)
            fs0 = INF.factor_of_safety(slope, p["soil_depth"][i], p["effective_cohesion"][i], p["friction_angle"][i],
                                       p["unit_weight"][i], m=float(m0), c_root=p["root_cohesion"][i])
            f_i = np.where((fs0 >= 1.0) & (slope <= max_soil_slope), f_i, 99.0)
        minfs[i] = f_i
    minfs[:, ~valid] = np.nan
    minfs = np.where(np.isinf(minfs), 99.0, minfs)
    return {"min_fs_p05": np.nanpercentile(minfs, 5, axis=0), "min_fs_p50": np.nanpercentile(minfs, 50, axis=0),
            "min_fs_p95": np.nanpercentile(minfs, 95, axis=0), "frac_lt1": np.nanmean(minfs < 1.0, axis=0)}, p


def _opt(name, grid, rs=Resampling.bilinear):
    try:
        return rasters.read(paths.get(name), grid, rs)
    except Exception:
        return None


SRC_CELL_M = 90.0   # 05_risk rasters are on the 90 m LSM grid


def _count_layer(name, grid):
    """Per-cell COUNT raster (people per 90 m cell). Averaged then rescaled by cell area so that the total is preserved
    whether the analysis grid is finer or coarser than the source (bilinear on counts would multiply people by ~9 at 30 m)."""
    a = _opt(name, grid, Resampling.average)
    return None if a is None else a * (grid["resolution_m"] / SRC_CELL_M) ** 2


def run_aoi(geojson, params, progress=lambda s, f: None, run_root="runs"):
    from pathlib import Path
    bbox, area_km2, warns = AOI.validate_geojson(geojson, max_area_km2=MAX_AOI_KM2)
    epsg, w2 = AOI.select_analysis_crs(bbox)
    warns = list(warns) + list(w2)
    res = choose_resolution(area_km2, bbox)
    if res > MIN_RES_M:
        warns.append(f"AOI {area_km2:,.0f} km2: analysis coarsened to {res:.0f} m to fit the interactive budget "
                     f"(slope, hence stability, is resolution-dependent). Use the national product or a smaller AOI for 30 m.")
    progress("grid", 0.05)
    grid = rasters.make_grid(bbox, epsg, res)
    sources = []
    dem = rasters.read(paths.get("DEM"), grid, Resampling.average if res > MIN_RES_M else Resampling.bilinear)
    if dem is None:
        raise InsufficientData(["DEM coverage for this AOI (outside Pakistan DEM)"], "terrain")
    sources.append({"id": "DEM_SRTM_Pak", "path": paths.get("DEM")})
    inside = rasters.polygon_mask(geojson, grid)
    valid = inside & np.isfinite(dem)
    if valid.sum() < 25:
        raise GateError(["AOI contains fewer than 25 valid DEM cells"])
    progress("terrain", 0.15)
    dx = dy = grid["resolution_m"]
    t = terrain.slope_aspect(np.where(np.isfinite(dem), dem, np.nanmedian(dem)), dx, dy)
    slope = np.where(valid, t["slope_deg"], np.nan).astype("float32")

    out = {"dem": np.where(valid, dem, np.nan), "slope_deg": slope}
    layers = {}
    progress("susceptibility", 0.3)
    lsm = _opt("LSM_PROB", grid)
    if lsm is not None:
        out["lsm_prob"] = np.where(valid & (lsm >= 0), lsm, np.nan)
        sources.append({"id": "LSM_CNN_DNN_Ensemble", "path": paths.get("LSM_PROB")})
    else:
        warns.append("national susceptibility layer has no coverage here (NODATA, not low risk)")

    summary = {"area_km2": area_km2, "resolution_m": res, "valid_cells": int(valid.sum()), "bbox": bbox}
    coarse = res > MAX_PHYSICS_RES_M
    if coarse:
        warns.append(f"Physics (stability, earthquake, run-out) skipped: at {res:.0f} m cells slope is smoothed away and the result would "
                     f"be meaningless. Draw an area of about {MAX_CELLS*MAX_PHYSICS_RES_M**2/1e6:,.0f} km2 or less (<= {MAX_PHYSICS_RES_M:.0f} m cells), "
                     "or use the national 90 m layers and district statistics for the whole country.")
        summary["physics"] = "skipped_resolution_too_coarse"
        pop = _count_layer("POPULATION", grid)
        if pop is not None:
            summary["exposure"] = {"population_in_aoi": _sum(np.nan_to_num(pop), valid)}
        return _finalize(out, summary, sources, warns, geojson, grid, params, valid, run_root)
    spec, hp = build_spec(params)
    n = int(params.get("n_members", 40))
    rain_mm_h, hours = float(params.get("rain_mm_h", 20)), int(params.get("duration_h", 24))
    if rain_mm_h < 0 or not 1 <= hours <= 720:
        raise GateError(["rainfall must be >=0 mm/h and duration 1-720 h"])
    progress("stability", 0.45)
    sg, samples = stability_grid(slope, valid, rain_mm_h, hours, spec, n, int(params.get("seed", 0)))
    out.update({k: v for k, v in sg.items()})
    unstable = valid & (sg["frac_lt1"] >= 0.5)
    summary["stability"] = {
        "rain_mm_h": rain_mm_h, "duration_h": hours, "total_rain_mm": rain_mm_h * hours, "n_members": n,
        "area_frac_median_fs_lt1": float((sg["min_fs_p50"][valid] < 1).mean()),
        "area_frac_majority_members_fs_lt1": float(unstable[valid].mean()),
        "area_km2_majority_members_fs_lt1": float(unstable.sum() * rasters.cell_area_km2(grid)),
        "texture": params.get("texture", "sandy loam"), "strength_preset": params.get("strength_preset", "colluvium_shallow"),
        "note": "fraction of ensemble members with FS<1 is conditional on the stated priors; NOT a probability"}
    if "lsm_prob" in out:
        a = out["lsm_prob"]
        summary["susceptibility"] = {"mean_prob": float(np.nanmean(a)), "area_frac_prob_gt_0_5": float((a[valid & np.isfinite(a)] > 0.5).mean())}
        both = valid & np.isfinite(a)
        if both.sum() > 10 and np.nanstd(a[both]) > 0:
            summary["susceptibility"]["spearman_with_physics_frac_lt1"] = _spearman(a[both], sg["frac_lt1"][both])

    # --- earthquake (optional)
    pga = params.get("pga_g")
    if pga:
        progress("seismic", 0.7)
        c, phi, z = (float(np.median(samples[k])) for k in ("effective_cohesion", "friction_angle", "soil_depth"))
        ay = NM.yield_coefficient(slope, z, c, phi, 18e3, m=0.0)
        d = NM.jibson2007_displacement_cm(ay, float(pga))
        out["newmark_cm"] = np.where(valid, d, np.nan)
        summary["seismic"] = {"pga_g": float(pga), "median_params": {"z": z, "c_pa": c, "phi": phi},
                              "area_frac_disp_gt_5cm": float((d[valid & np.isfinite(d)] > 5).mean()),
                              "note": "Jibson 2007 regression, dry slope, scenario PGA uniform over the AOI; screening only"}

    # --- runout envelope
    if params.get("runout", True):
        progress("runout", 0.8)
        src = unstable & (slope > 20)
        if src.sum() > MAX_SOURCES:
            score = np.where(src, -sg["min_fs_p50"], -np.inf)
            idx = np.argpartition(score.ravel(), -MAX_SOURCES)[-MAX_SOURCES:]
            src = np.zeros_like(src); src.ravel()[idx] = True; src &= unstable
            warns.append(f"runout sources limited to the {MAX_SOURCES} lowest-FS cells")
        if src.any():
            vol = float(params.get("volume_m3", 1e4))
            lo, hi = float(params.get("alpha_min_deg", 14)), float(params.get("alpha_max_deg", 24))
            env = RE.ensemble_envelope(np.where(np.isfinite(dem), dem, 1e5), dx, dy, src, vol, (lo, hi), int(params.get("n_alpha", 12)), 0)
            f = env["envelope_frequency_conditional_on_priors"]
            out["runout_freq"] = np.where(valid, f, np.nan)
            summary["runout"] = {"source_cells": int(src.sum()), "alpha_range_deg": [lo, hi], "volume_m3": vol,
                                 "reached_area_km2": float((f > 0).sum() * rasters.cell_area_km2(grid)),
                                 "note": "reach-angle envelope, not simulated depth/velocity"}
            # --- exposure inside the envelope
            pop = _count_layer("POPULATION", grid)
            reached = (f > 0) & valid
            if pop is not None:
                pop_c = np.nan_to_num(pop)
                summary["exposure"] = {"population_in_unstable_cells": _sum(pop_c, unstable),
                                       "population_in_runout_envelope": _sum(pop_c, reached),
                                       "population_in_aoi": _sum(pop_c, valid),
                                       "note": "WorldPop 2025 constrained 100 m via 05_risk (people per cell, total preserved on resampling); screening estimate"}
            built = _opt("BUILT_FRAC", grid)
            if built is not None:
                summary.setdefault("exposure", {})["built_area_km2_in_runout_envelope"] = float(np.nansum(built[reached]) * rasters.cell_area_km2(grid))
        else:
            summary["runout"] = {"source_cells": 0, "note": "no majority-unstable steep cells under this scenario"}
    return _finalize(out, summary, sources, warns, geojson, grid, params, valid)


def _finalize(out, summary, sources, warns, geojson, grid, params, valid, run_root="runs"):
    from pathlib import Path
    risk = _opt("RISK_INDEX", grid)
    if risk is not None:
        out["risk_index"] = np.where(valid, risk, np.nan)
        sources.append({"id": "risk_index_05_risk", "path": paths.get("RISK_INDEX")})
        summary["risk"] = {"mean_risk_index": float(np.nanmean(out["risk_index"]))}
    gg = {k: v for k, v in grid.items() if k != "affine"}
    key = M.cache_key("landslide_aoi", VERSION, sources, AOI.aoi_sha256(geojson), gg, params)
    rid = key[:32]
    rdir = Path(run_root) / rid
    rdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(rdir / "arrays.npz", **{k: v.astype("float32") for k, v in out.items()})
    man = M.build_manifest("landslide_aoi", VERSION, sources, AOI.aoi_sha256(geojson), gg, parameter_mode="scenario_ensemble",
                           warnings=warns + ["Screening-grade decision support. Not for engineering design or evacuation orders.",
                                             "soil strength is a scenario range, not measured"], results=["arrays.npz", "summary.json"],
                           params=params, run_id=rid)
    summary = json.loads(json.dumps(summary, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    (rdir / "summary.json").write_text(json.dumps(summary, indent=2))
    M.write_manifest(rdir, man)
    return {"run_id": rid, "summary": summary, "manifest": man, "grid": gg, "out": out, "valid": valid, "run_dir": str(rdir)}


def _sum(a, m):
    return float(a[m].sum())


def _spearman(a, b):
    from scipy.stats import spearmanr
    r = spearmanr(a, b).statistic
    return None if not np.isfinite(r) else float(r)
