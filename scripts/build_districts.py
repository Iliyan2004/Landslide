#!/usr/bin/env python3
"""Per-district national statistics (164 districts) from the national layers -> datasets/national/districts.geojson.
Run after build_national.py to include the physics product; works without it (physics columns are omitted).
Zonal stats on the 90 m LSM grid (EPSG:32643). Population is a sum of per-cell counts; susceptibility is a mean/area share."""
import json, sys
from pathlib import Path
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import paths, rasters, pipeline   # noqa: E402

with rasterio.open(paths.get("LSM_PROB")) as s:
    grid = {"crs": s.crs.to_string(), "affine": s.transform, "width": s.width, "height": s.height, "resolution_m": 90.0}
d = gpd.read_file(paths.get("DISTRICTS_SHP"))
d = d[["name", "province", "division", "geometry"]].reset_index(drop=True)
ids = rasterize(((g, i + 1) for i, g in enumerate(d.to_crs(grid["crs"]).geometry)), out_shape=(grid["height"], grid["width"]),
                transform=grid["affine"], fill=0, dtype="int32")
lsm = rasters.read(paths.get("LSM_PROB"), grid, Resampling.nearest); lsm = np.where(lsm >= 0, lsm, np.nan)
pop = np.nan_to_num(rasters.read(paths.get("POPULATION"), grid, Resampling.nearest))
risk = rasters.read(paths.get("RISK_INDEX"), grid, Resampling.nearest)
phys_rows = {}
prods = sorted((ROOT / "datasets/national").glob("stability_*_mob.tif"))
log = ROOT / "datasets/national/build.log"
if prods and log.exists() and "DONE" in log.read_text()[-400:]:
    # zonal statistics on the physics product's OWN grid (EPSG:32642, whole country), not the northern-only LSM grid
    with rasterio.open(prods[-1]) as src:
        dd = d.to_crs(src.crs)
        ids_p = rasterize(((g, i + 1) for i, g in enumerate(dd.geometry)), out_shape=(src.height, src.width), transform=src.transform, fill=0, dtype="int16")
        f = src.read(1)
        cell_p = (abs(src.res[0]) ** 2) / 1e6
    ok = f != 255
    for i in range(len(d)):
        m = (ids_p == i + 1) & ok
        if m.any():
            v = f[m] / 100.0
            phys_rows[i] = {"physics_frac_fs_lt1_mean": round(float(v.mean()), 4), "physics_area_km2_majority_fs_lt1": round(float((v >= 0.5).sum() * cell_p), 2),
                            "physics_cells_valid_km2": round(float(m.sum() * cell_p), 1)}
    del ids_p, f
    print("physics product:", prods[-1].name, "districts with physics:", len(phys_rows))
else:
    print("physics product incomplete or absent: physics columns omitted")
cell_km2 = 0.0081
rows = []
for i in range(len(d)):
    m = ids == i + 1
    n = int(m.sum())
    r = {"name": d.name[i], "province": d.province[i], "division": d.division[i], "cells": n}
    if n:
        l = lsm[m]; ok = np.isfinite(l)
        r.update(area_km2_covered=round(n * cell_km2, 1), lsm_coverage=round(float(ok.mean()), 3),
                 lsm_mean=round(float(np.nanmean(l)), 3) if ok.any() else None,
                 lsm_area_frac_gt_0_7=round(float((l[ok] > 0.7).mean()), 3) if ok.any() else None,
                 population=int(pop[m].sum()), population_lsm_gt_0_7=int(pop[m][np.where(ok, l > 0.7, False)].sum()),
                 mean_risk_index=round(float(np.nanmean(risk[m])), 4) if np.isfinite(risk[m]).any() else None)
    r.update(phys_rows.get(i, {}))
    rows.append(r)
out = d.copy()
for k in sorted({k for r in rows for k in r}):
    if k not in out.columns:
        out[k] = [r.get(k) for r in rows]
dst = ROOT / "datasets/national/districts.geojson"
out["geometry"] = out.geometry.simplify(0.002)
out.to_file(dst, driver="GeoJSON")
print("wrote", dst, len(out), "districts;", "LSM coverage <1 in", int(sum(1 for r in rows if r.get("lsm_coverage", 0) < 0.99)))
