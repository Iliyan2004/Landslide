"""Rockfall run: AOI -> release cells (steep rock faces, user polygons, or earthquake ground motion) -> GPU Monte Carlo -> hazard maps and impacts.
A separate hazard from the debris-flow runs: rocks are discrete bodies (flight, bounce, rolling), not a depth-averaged flow."""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import LineString, shape
from shapely.ops import transform as shp_transform
from ..app import paths, rasters, pipeline as P, layers as LY
from ..data.preprocessing import aoi as AOI, terrain
from ..errors import GateError, InsufficientData
from . import rockfall as RK, trigger as TR

MAX_CELLS = 700_000
MAX_RES_M = 90.0
MAX_ROCKS = 60_000
RELEASE_FRAC = 0.01          # a cell/building counts as "reached" when at least this fraction of released rocks passed it


def _barrier_rasters(barriers, grid, epsg, shape_hw):
    cap = np.zeros(shape_hw, "float32"); ht = np.zeros(shape_hw, "float32"); bid = np.zeros(shape_hw, "int64"); info = []
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    for i, b in enumerate(barriers or []):
        pts = b["coords"]
        if len(pts) < 2:
            continue
        line = shp_transform(tr.transform, LineString(pts))
        m = rasterize([(line.buffer(max(grid["resolution_m"], float(b.get("width_m", 0))) / 2.0), 1)], out_shape=shape_hw, transform=grid["affine"], fill=0, dtype="uint8").astype(bool)
        cap[m] = np.maximum(cap[m], float(b.get("capacity_kj", 500.0))); ht[m] = np.maximum(ht[m], float(b.get("height_m", 4.0))); bid[m] = i
        info.append({"length_m": float(line.length), "height_m": float(b.get("height_m", 4.0)), "capacity_kj": float(b.get("capacity_kj", 500.0))})
    return (None if not info else {"cap_kj": cap, "height": ht, "id": bid}), info


def execute(geom, params, run_dir, progress=lambda s, f: None):
    t0 = time.time()
    run_dir = Path(run_dir); run_dir.mkdir(parents=True, exist_ok=True)
    warns = []
    bbox, area_km2, w0 = AOI.validate_geojson(geom, max_area_km2=P.MAX_AOI_KM2); warns += list(w0)
    epsg, w1 = AOI.select_analysis_crs(bbox); warns += list(w1)
    res = max(P.MIN_RES_M, float(np.ceil(np.sqrt(area_km2 * 1e6 / MAX_CELLS) / 10.0) * 10.0))
    if res > MAX_RES_M:
        raise GateError([f"{area_km2:,.0f} km2 is too large for a rockfall run (cells {res:.0f} m). Draw <= {MAX_CELLS*MAX_RES_M**2/1e6:,.0f} km2."])
    progress("terrain", 0.04)
    grid = rasters.make_grid(bbox, epsg, res)
    dem = rasters.read(paths.get("DEM"), grid, Resampling.average if res > P.MIN_RES_M else Resampling.bilinear)
    if dem is None:
        raise InsufficientData(["DEM coverage for this AOI"], "terrain")
    valid = rasters.polygon_mask(geom, grid) & np.isfinite(dem)
    dem_f = np.where(np.isfinite(dem), dem, np.nanmedian(dem))
    slope = terrain.slope_aspect(dem_f, res, res)["slope_deg"].astype("float32")
    ny, nx = dem.shape
    rng = np.random.default_rng(int(params.get("seed", 0)))
    # ---- release cells
    mode = params.get("source_mode", "auto"); min_slope = float(params.get("min_source_slope_deg", 50.0)); max_src = int(params.get("max_sources", 150))
    pga = None; quake_vis = None
    if mode == "quake":
        from .run import _quake_field
        qk = params["quake"]
        pga, _, rup, _ = _quake_field(qk, grid, epsg, None, qk.get("gmpe", "auto"), float(qk.get("depth_km", 15.0)))
        cand = valid & (slope >= min_slope) & (pga >= 0.10)
        r, c = np.where(cand)
        if len(r) > max_src:
            w = np.clip((pga[r, c] - 0.10) / 0.4, 0.02, 1.0) * np.clip(slope[r, c] - min_slope + 1, 1, None); w = w / w.sum()
            pick = rng.choice(len(r), max_src, replace=False, p=w); r, c = r[pick], c[pick]
        src = (r, c)
    elif mode == "polygons":
        m = np.zeros((ny, nx), bool)
        for pg in params.get("source_polygons", []):
            m |= rasters.polygon_mask(pg, grid)
        r, c = np.where(m & valid & (slope >= float(params.get("min_source_slope_deg", 35.0))))
        if len(r) > max_src:
            pick = rng.choice(len(r), max_src, replace=False); r, c = r[pick], c[pick]
        src = (r, c)
    else:
        src = RK.auto_sources(slope, valid, min_slope, max_src, rng)
    if len(src[0]) == 0:
        raise GateError([f"no release cells: no slopes of at least {min_slope:.0f} degrees inside the area (lower 'minimum source slope' or draw source polygons)"])
    per = int(params.get("rocks_per_source", 40))
    if len(src[0]) * per > MAX_ROCKS:
        per = max(1, MAX_ROCKS // len(src[0])); warns.append(f"rocks per source reduced to {per} (limit {MAX_ROCKS} rocks)")
    lulc = rasters.read(paths.get("LULC"), grid, Resampling.nearest)
    rn, rt, mu = RK.surface_maps(lulc, (ny, nx), params.get("default_surface", "talus"))
    if params.get("surface_override"):
        s = RK.SURFACES[params["surface_override"]]; rn[:] = s[0]; rt[:] = s[1]; mu[:] = s[2]
    iv = params.get("barriers") or []
    barr, binfo = _barrier_rasters(iv, grid, epsg, (ny, nx))
    progress("simulate", 0.12)
    sim = RK.simulate(dem_f, res, src, per, float(params.get("d50_m", 0.8)), float(params.get("d_sigma", 0.35)), params.get("shape", "round"), rn, rt, mu,
                      float(params.get("rough_deg", 9.0)), float(params.get("t_max_s", 100.0)), int(params.get("track", 250)), 3, barr, valid, int(params.get("seed", 0)),
                      params.get("backend", "auto"), float(params.get("stagger_s", 20.0)), lambda s, f: progress(s, 0.12 + 0.7 * f))
    progress("impact", 0.85)
    N = sim["n_rocks"]
    reach = (sim["reach_count"] / N).astype("float32"); emax = (sim["emax_j"] / 1000.0).astype("float32"); hmax = sim["hmax_m"].astype("float32")
    for a in (reach, emax, hmax):
        a[~valid] = np.nan
    st = sim["state"]; ang = sim["travel_angle_deg"]
    summary = {"mode": "rockfall", "area_km2": area_km2, "resolution_m": res, "grid": [ny, nx], "backend": sim["device"],
               "release": {"source_mode": mode, "source_cells": int(len(src[0])), "rocks": int(N), "rocks_per_source": per, "min_source_slope_deg": min_slope,
                           "d50_m": float(params.get("d50_m", 0.8)), "shape": params.get("shape", "round"), "rough_deg": float(params.get("rough_deg", 9.0)),
                           "median_mass_kg": float(np.median(4 / 3 * np.pi * (sim["diameter_m"] / 2) ** 3 * RK.RHO))},
               "outcome_rocks": {"stopped": float((st == 2).mean()), "left_area": float((st == 3).mean()), "still_moving_at_end": float((st == 1).mean())},
               "travel_angle_deg": {"p10": float(np.percentile(ang, 10)), "p50": float(np.percentile(ang, 50)), "p90": float(np.percentile(ang, 90)),
                                    "share_below_27_5": float((ang < 27.5).mean()),
                                    "note": "reach (Fahrboeschung) angle source->stop; literature shadow-angle values 22-32 degrees"},
               "max_runout_m": float(np.sqrt(((sim["stop_xy"] - sim["src_xy"]) ** 2).sum(1)).max()),
               "peak_energy_kj": float(np.nanmax(emax)), "p99_energy_kj": float(np.nanpercentile(emax[reach > 0], 99)) if (reach > 0).any() else 0.0,
               "max_bounce_height_m": float(np.nanmax(hmax)), "p95_bounce_height_m": float(np.nanpercentile(hmax[reach > 0], 95)) if (reach > 0).any() else 0.0,
               "reached_area_km2": float(((reach >= RELEASE_FRAC) & valid).sum() * res * res / 1e6),
               "energy_note": "translational energy 0.5 m v^2; a rolling sphere carries up to 40% more in rotation"}
    if barr is not None:
        summary["barriers"] = binfo
        summary["barriers_stopped_rocks"] = float(sim["stops"][barr["cap_kj"] > 0].sum() / N)
    if pga is not None:
        summary["quake"] = {"magnitude": params["quake"]["magnitude"], "pga_g_max": float(np.nanmax(pga[valid]))}
    # ---- exposure
    summary["exposure"], detail = _exposure(geom, bbox, grid, epsg, reach, emax, hmax, res, warns)
    # ---- tracked rocks to lon/lat
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    rec = sim["rec"]                                                         # (nrec, M, 5): x,y (m, row/col axes), height, speed, impact
    X = grid["affine"].c + rec[..., 0] / res * grid["affine"].a; Y = grid["affine"].f + rec[..., 1] / res * grid["affine"].e
    lon, lat = tr.transform(X.ravel(), Y.ravel()); lon = np.asarray(lon).reshape(X.shape).astype("float64"); lat = np.asarray(lat).reshape(X.shape).astype("float64")
    s_x = grid["affine"].c + sim["src_xy"][:, 0] / res * grid["affine"].a; s_y = grid["affine"].f + sim["src_xy"][:, 1] / res * grid["affine"].e
    slon, slat = tr.transform(s_x, s_y)
    arrays = {"dem": np.where(valid, dem, np.nan).astype("float32"), "slope": slope, "reach_frac": reach, "emax_kj": emax, "hmax_m": hmax}
    if pga is not None:
        arrays["pga_g"] = np.where(valid, pga, np.nan).astype("float32")
    np.savez_compressed(run_dir / "arrays.npz", **{k: np.asarray(v, "float32") for k, v in arrays.items()})
    ti = sim["tracked"]
    np.savez_compressed(run_dir / "rocks.npz", lon=lon.astype("float64"), lat=lat.astype("float64"), h=rec[..., 2].astype("float32"), v=rec[..., 3].astype("float32"), imp=rec[..., 4].astype("uint8"),
                        state=sim["rec_state"], dt=np.array(sim["rec_dt"]), dia=sim["diameter_m"][ti].astype("float32"),
                        src_lon=np.asarray(slon)[::max(1, len(slon) // 400)], src_lat=np.asarray(slat)[::max(1, len(slat) // 400)])
    (run_dir / "geom_rock.json").write_text(json.dumps({"geom": geom, "epsg": epsg, "rocks": int(N), "sources": int(len(src[0])), "barriers": iv}))
    summary["elapsed_s"] = round(time.time() - t0, 1)
    return {"summary": summary, "warnings": warns, "grid": grid, "arrays": arrays, "valid": valid, "bbox": bbox, "epsg": epsg, "geom": geom, "run_dir": str(run_dir), "detail": detail,
            "outcome": "rockfall", "barriers": iv, "res": res}


def _exposure(geom, bbox, grid, epsg, reach, emax, hmax, dx, warns):
    inv = ~grid["affine"]; tr = Transformer.from_crs(4326, epsg, always_xy=True)
    ny, nx = reach.shape
    rz = np.nan_to_num(reach); ez = np.nan_to_num(emax)
    rm = ndimage.maximum_filter(rz, size=3); em = ndimage.maximum_filter(ez, size=3); hm = ndimage.maximum_filter(np.nan_to_num(hmax), size=3)

    def cell(lon, lat):
        x, y = tr.transform(lon, lat); c, r = inv * (x, y); return int(r), int(c)
    pop = P._count_layer("POPULATION", grid)
    ex = {}
    if pop is not None:
        ex["population_in_reached_cells"] = float(np.nan_to_num(pop)[rz >= RELEASE_FRAC].sum())
    b = LY.buildings(bbox, geom); roads = LY.roads(bbox, geom); fac = LY.facilities(bbox, geom)
    cls_count = [0] * 5; hit = 0
    for bd in b:
        r, c = cell(bd["cx"], bd["cy"])
        if 0 <= r < ny and 0 <= c < nx:
            rf, e = float(rm[r, c]), float(em[r, c]); bd["reach"], bd["emax_kj"], bd["rr"], bd["cc"] = rf, e, r, c
            if rf >= RELEASE_FRAC:
                hit += 1; bd["cls"] = RK.energy_class(e); cls_count[bd["cls"]] += 1
            else:
                bd["cls"] = -1
    ex.update({"buildings_in_aoi": len([x for x in b if "reach" in x]), "buildings_reached": hit, "buildings_by_energy_class": cls_count,
               "energy_classes_kj": ["<10", "10-50", "50-300", "300-1000", ">1000"], "reached_threshold": f">= {RELEASE_FRAC:.0%} of released rocks pass the building"})
    rl, tl = 0.0, 0.0; rc = [0.0] * 5
    for rd in roads:
        pts = rd["coords_lonlat"]; worst = -1
        for p0, p1 in zip(pts[:-1], pts[1:]):
            x0, y0 = tr.transform(*p0); x1, y1 = tr.transform(*p1); L = math.hypot(x1 - x0, y1 - y0); tl += L
            hitseg = False
            for f in (0.0, 0.5):
                r, c = cell(p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
                if 0 <= r < ny and 0 <= c < nx and rm[r, c] >= RELEASE_FRAC:
                    hitseg = True; k = RK.energy_class(float(em[r, c])); worst = max(worst, k); rc[k] += L / 2
            rl += L if hitseg else 0.0
        rd["cls"] = worst
    ex.update({"road_length_km": tl / 1000, "road_reached_km": rl / 1000, "road_reached_by_energy_class_km": [round(x / 1000, 3) for x in rc]})
    fh = []
    for f in fac:
        r, c = cell(f["lon"], f["lat"])
        if 0 <= r < ny and 0 <= c < nx and rm[r, c] >= RELEASE_FRAC:
            fh.append({"kind": f["kind"], "name": f["name"], "reach": float(rm[r, c]), "energy_kj": float(em[r, c])})
    ex["facilities_reached"] = fh
    return ex, {"buildings": b, "roads": roads, "facilities": fac}
