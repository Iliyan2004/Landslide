"""Run packaging: execute the engine, build the 3D scene and 2D overlays, persist everything under runs/<id>/."""
from __future__ import annotations
import hashlib, json, os, time
from pathlib import Path
import numpy as np
from .. import manifest as M
from ..engine import run as ENG
from . import pipeline as P, render, viewer, paths

VERSION = "2.5.0"
LAYER_INFO = {
    "hmax": "Maximum flow depth", "vmax": "Maximum flow speed", "deposit": "Net deposit thickness", "scour": "Scar / scour depth",
    "t_fail_h": "Failure time", "fs_min": "Minimum factor of safety", "pga_g": "Peak ground acceleration", "slope": "Slope", "p_fail": "Failure probability (ensemble)",
}


def run_id_for(geom, params):
    return hashlib.sha256(json.dumps({"g": geom, "p": params, "v": VERSION}, sort_keys=True, default=str).encode()).hexdigest()[:20]


def execute(geom, params, runs_root, token, progress=lambda s, f: None, force=False):
    rid = run_id_for(geom, params)
    rdir = Path(runs_root) / rid
    if (rdir / "summary.json").exists() and not force:
        d = json.loads((rdir / "summary.json").read_text()); d["cached"] = True; d["run_id"] = rid
        return d
    t0 = time.time()
    out = ENG.execute(geom, params, rdir, progress)
    summary = out["summary"]
    try:                                                      # the complete inputs, for 'Save run file' (the manifest keeps only a subset of the parameters)
        (rdir / "inputs.json").write_text(json.dumps({"geometry": geom, "params": params}, default=str))
    except Exception:
        pass
    man_extra = {}
    pending_scene = False
    if out.get("has_flow"):
        H, VX, VY = out["H"], out["VX"], out["VY"]
        ever = (H.max(0) > 0.05)
        rel = np.isfinite(out["arrays"]["t_fail_h"])
        act = ever | rel
        rows, cols = np.where(act)
        m = 12
        ny, nx = act.shape
        r0, r1 = max(0, rows.min() - m), min(ny, rows.max() + m + 1)
        c0, c1 = max(0, cols.min() - m), min(nx, cols.max() + m + 1)
        crop = (int(r0), int(r1), int(c0), int(c1))
        sl = (slice(None), slice(r0, r1), slice(c0, c1))
        A = out["arrays"]
        # everything needed to rebuild the 3D scene later WITHOUT re-simulating (viewer changes, new palettes, rebuild-scene route)
        np.savez_compressed(rdir / "frames.npz", H=H[sl], VX=VX[sl], VY=VY[sl], frame_t=out["frame_t"], crop=np.array(crop),
                            tfail_s=(A["t_fail_h"] * 3600.0)[r0:r1, c0:c1].astype("float32"), bedchange=(A["deposit"] - A["scour"])[r0:r1, c0:c1].astype("float32"),
                            stats=np.array(out["stats_t"], "float32"),
                            pga=(A["pga_g"][r0:r1, c0:c1].astype("float32") if "pga_g" in A else np.zeros(0, "float32")))
        (rdir / "geom.json").write_text(json.dumps({"geom": out["geom"], "series": out["series"], "epsg": out["epsg"], "dx": out["dx"], "t0_s": float(out["frame_t"][0]), "quake": out.get("quake_vis")}))
        _save_impacts(rdir, out["exposure_detail"])
        pending_scene = True
        summary["stats_t"] = {"t_min": [round(float(t) / 60, 1) for t in out["frame_t"]], "area_km2": [round(s[0], 5) for s in out["stats_t"]],
                              "max_depth_m": [round(s[1], 2) for s in out["stats_t"]], "volume_m3": [round(s[2], 1) for s in out["stats_t"]]}
        np.savez_compressed(rdir / "arrays.npz", **{k: np.asarray(v, "float32") for k, v in out["arrays"].items()})
    gg = {k: v for k, v in out["grid"].items() if k != "affine"}
    srcs = [{"id": ("DEM_custom_" + str(params["custom_dem_id"])) if params.get("custom_dem_id") else "DEM_SRTM_Pak", "path": paths.get("DEM")}]
    man = M.build_manifest("landslide_physics_run", VERSION, srcs, hashlib.sha256(json.dumps(geom, sort_keys=True).encode()).hexdigest(), gg,
                           parameter_mode="scenario_ensemble",
                           warnings=out["warnings"] + ["Screening-grade decision support. Not for engineering design or evacuation orders.",
                                                       "Soil strength and flow friction are scenario values, not measurements or calibrations."],
                           results=["summary.json", "arrays.npz", "mapbox_3d.html"], params={k: v for k, v in params.items() if k != "rain"}, run_id=rid)
    man["rainfall"] = {k: v for k, v in (params.get("rain") or {}).items() if k not in ("times_h", "rate_mm_h", "times_iso")}
    M.write_manifest(rdir, man)
    if pending_scene:
        summary["scene"] = _build_scene(rdir, token, rebuilt=False)
    summary["elapsed_total_s"] = round(time.time() - t0, 1)
    summary["params"] = {k: v for k, v in params.items() if k not in ("rain",)}
    if params.get("rain"):
        summary["rain_series"] = {"times_h": params["rain"]["times_h"], "rate_mm_h": params["rain"]["rate_mm_h"], "source": params["rain"].get("source")}
    d = {"run_id": rid, "outcome": out["outcome"], "summary": summary, "warnings": man["warnings"], "has_scene": bool(out.get("has_flow")),
         "layers": [k for k in LAYER_INFO if k in (out.get("arrays") or {})], "bbox": out.get("bbox")}
    (rdir / "summary.json").write_text(json.dumps(d, indent=1, default=str))
    return d


def overlay(run_id, layer, runs_root):
    from affine import Affine
    rdir = Path(runs_root) / run_id
    man = json.loads((rdir / "manifest.json").read_text()); g = man["grid"]; t = g["transform"]
    grid = {**g, "affine": Affine(t[1], 0, t[0], 0, t[5], t[3])}
    z = np.load(rdir / "arrays.npz")
    if layer not in z.files:
        raise KeyError(layer)
    a = z[layer]
    ramp = {"slope": "slope_deg", "fs_min": "min_fs_p50", "p_fail": "frac_lt1"}.get(layer, layer)
    if layer in ("hmax", "deposit", "scour", "vmax"):
        a = np.where(a > 0.05, a, np.nan)
    return render.overlay_png(a, grid, ramp)


# ---------- Tier 2: instant stability library (precomputed rain ladder, interpolated client-side)
LADDER_MM = [0, 25, 50, 100, 150, 200, 300, 450, 600]


def instant_library(geom, params):
    """Median-parameter FS grids over a ladder of 24 h rain totals -> critical-rain map + area-vs-rain curve + overlay PNGs."""
    import base64
    from rasterio.enums import Resampling
    from ..data.preprocessing import aoi as AOI, terrain
    from ..engine import trigger as TR
    from . import rasters
    bbox, area_km2, warn = AOI.validate_geojson(geom, max_area_km2=P.MAX_AOI_KM2)
    epsg, _ = AOI.select_analysis_crs(bbox)
    from . import custom_dem as CD
    dem_path, min_res, _n = CD.resolve(params, bbox, paths.get("DEM"), P.MIN_RES_M)
    res = max(min_res, P.choose_resolution(area_km2, bbox)) if min_res >= P.MIN_RES_M else max(min_res, float(np.ceil(np.sqrt(area_km2 * 1e6 / P.MAX_CELLS) / min_res) * min_res))
    if res > P.MAX_PHYSICS_RES_M:
        raise P.GateError([f"{area_km2:,.0f} km2 is too large for the instant library (cells {res:.0f} m). Draw <= ~{P.MAX_CELLS*P.MAX_PHYSICS_RES_M**2/1e6:,.0f} km2."])
    grid = rasters.make_grid(bbox, epsg, res)
    dem = rasters.read(dem_path, grid, Resampling.average if res > min_res else Resampling.bilinear)
    valid = rasters.polygon_mask(geom, grid) & np.isfinite(dem)
    slope = terrain.slope_aspect(np.where(np.isfinite(dem), dem, np.nanmedian(dem)), res, res)["slope_deg"].astype("float32")
    spec, _ = P.build_spec(params)
    sp = TR.scenario_point(spec, float(params.get("strength_quantile", 0.3)))
    z = TR.soil_depth_field(slope, sp, bool(params.get("depth_vs_slope", True)))
    mob, _ms = TR.mobilisable_mask(slope, valid, z, sp, float(params.get("max_soil_slope_deg", 45)))
    steps_hours = 24
    fs_stack, curve = [], []
    for mm in LADDER_MM:
        rain = np.full(steps_hours * 4, mm / steps_hours / 4.0)       # mm per 15-min step, uniform over 24 h
        if mm == 0:
            rain = np.zeros(steps_hours * 4)
        _, fs, _, _ = TR.rain_failure_times(slope, mob, rain, 900, sp, z, float(params.get("min_slope_deg", 12)))
        fs = np.where(mob & np.isfinite(fs), fs, np.nan)
        fs_stack.append(fs)
    fs_stack = np.stack(fs_stack)
    # critical rain: first ladder value with FS<1 (linear interpolation of FS between rungs)
    crit = np.full(slope.shape, np.nan, "float32")
    lad = np.array(LADDER_MM, float)
    for i in range(len(lad)):
        f = fs_stack[i]
        newly = np.isnan(crit) & (f < 1.0) & mob
        if i == 0:
            crit[newly] = 0.0
        else:
            f0 = fs_stack[i - 1]
            frac = np.clip((f0 - 1.0) / np.maximum(f0 - f, 1e-9), 0, 1)
            crit[newly] = (lad[i - 1] + frac[newly] * (lad[i] - lad[i - 1])).astype("float32")
    gg = {k: v for k, v in grid.items() if k != "affine"}
    out = {"ladder_mm": LADDER_MM, "area_km2": area_km2, "resolution_m": res,
           "unstable_area_km2": [float(np.nansum(fs_stack[i][mob] < 1.0) * res * res / 1e6) for i in range(len(lad))],
           "never_fails_within_ladder_frac": float(np.mean(np.isnan(crit[mob]))) if mob.any() else 1.0, "mobilisable": _ms, "params": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in sp.items()},
           "median_critical_rain_mm": float(np.nanmedian(crit[mob])) if np.isfinite(crit[mob]).any() else None}
    pngs = {}
    for i, mm in enumerate(LADDER_MM):
        png, corners = render.overlay_png(np.where(fs_stack[i] < 1.0, 1.0, np.where(mob, 0.0, np.nan)).astype("float32"), grid, "frac_lt1")
        pngs[str(mm)] = base64.b64encode(png).decode()
        pf, _c = render.overlay_png(np.where(fs_stack[i] < 1.0, 1.0, np.nan).astype("float32"), grid, "frac_lt1")      # failing cells only (LANDLAB Instant draws just these)
        pngs["f" + str(mm)] = base64.b64encode(pf).decode()
    png, corners = render.overlay_png(crit, grid, "crit_rain_mm")
    pngs["crit"] = base64.b64encode(png).decode()
    out["corners"] = corners; out["png"] = pngs; out["bbox"] = bbox
    return out


def _save_impacts(rdir, detail):
    """Building and road results of a run (footprints, damage state, expected damage ratio, loss, blocked flag) for 3D rebuilds and GIS export."""
    import gzip
    if not detail:
        return
    b = [{"c": x["coords_lonlat"], "a": x["area_m2"], "h": x["height_m"], "rr": x.get("rr"), "cc": x.get("cc"), "dmg": x.get("dmg"), "ds": x.get("ds"), "loss": x.get("loss"), "cx": x.get("cx"), "cy": x.get("cy")} for x in detail["buildings"]]
    r = [{"c": x["coords_lonlat"], "k": x.get("class"), "blocked": bool(x.get("blocked"))} for x in detail["roads"]]
    with gzip.open(rdir / "impacts.json.gz", "wt") as f:
        json.dump({"buildings": b, "roads": r}, f)


def _load_impacts(rdir):
    import gzip
    p = rdir / "impacts.json.gz"
    if not p.exists():
        return [], []
    d = json.load(gzip.open(p, "rt"))
    b = [{"coords_lonlat": x["c"], "area_m2": x["a"], "height_m": x["h"], "rr": x["rr"], "cc": x["cc"], "dmg": x["dmg"], "ds": x["ds"], "loss": x["loss"], "cx": x["cx"], "cy": x["cy"]} for x in d["buildings"]]
    r = [{"coords_lonlat": x["c"], "class": x["k"], "blocked": x["blocked"]} for x in d["roads"]]
    return b, r


LEGEND = ("<b>Landslide run</b><br>Rain &rarr; Green-Ampt infiltration &rarr; infinite-slope FS(t) &rarr; failure &rarr; Voellmy depth-averaged runout. "
          "<b>Red-orange flash</b> = a slope failing; <b>pale scar</b> stays behind. <b>Dark wet mud</b> = moving, <b>pale cracked mud</b> = at rest. "
          "Buildings turn by expected damage from the depth reached (assumed fragility, not calibrated). <i>Screening-grade, not for design.</i>")


def _build_scene(rdir, token, rebuilt=True):
    """Build mapbox_3d.html from the saved frames (no simulation)."""
    from affine import Affine
    z = np.load(rdir / "frames.npz")
    g = json.loads((rdir / "geom.json").read_text())
    man = json.loads((rdir / "manifest.json").read_text()) if (rdir / "manifest.json").exists() else None
    gg = man["grid"] if man else None
    if gg is None:
        raise FileNotFoundError("manifest.json missing: cannot place the scene")
    t = gg["transform"]; affine = Affine(t[1], 0, t[0], 0, t[5], t[3])
    bld, rds = _load_impacts(rdir)
    crop = tuple(int(x) for x in z["crop"])
    ft = z["frame_t"]
    legend = LEGEND + f"<br>Animation window starts {float(ft[0])/3600:.2f} h after the start of the rainfall series (or the earthquake time)."
    return viewer.build(str(rdir / "mapbox_3d.html"), "Landslide run", g["geom"], token, g["epsg"], affine, crop, z["H"], z["VX"], z["VY"], ft, z["stats"], g["series"], g["t0_s"],
                        bld, rds, g["dx"], legend, tfail_s=z["tfail_s"], bedchange=z["bedchange"], quake=(dict(g.get("quake") or {}, pga=z["pga"]) if (g.get("quake") and z["pga"].size) else None))


def rebuild_scene(run_id, runs_root, token):
    return _build_scene(Path(runs_root) / run_id, token)
