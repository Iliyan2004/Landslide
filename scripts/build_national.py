#!/usr/bin/env python3
"""Whole-of-Pakistan rainfall-stability product (tier N). Tiled, resumable, single process, niced.

Grid: EPSG:32642 (the DEM's own CRS), 90 m (matches the national susceptibility layer), clipped to the Pakistan border.
Per 2048x2048 tile: DEM (area-averaged to 90 m) -> slope -> Green-Ampt + infinite-slope scenario ensemble -> uint8 bands.
Outputs datasets/national/stability_<scenario>.tif  bands: 1 frac FS<1 (0-100), 2 median min-FS x50 (cap 254), 3 slope deg.
Rule: only slopes that were stable before the storm and are soil-bearing (<= 45 deg) can fail (pipeline.stability_grid mobilise=True).
Usage: ~/flood/venv/bin/python scripts/build_national.py [--rain 20 --hours 24 --n 20 --preset colluvium_shallow --texture "sandy loam" --res 90]
Slope from a 90 m average understates local slope; read this product as regional screening, drill into an AOI for 30 m."""
import argparse, json, os, sys, time
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
import geopandas as gpd
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import paths, rasters, pipeline as P          # noqa: E402
from landslide.data.preprocessing import terrain                  # noqa: E402
from rasterio.transform import Affine                            # noqa: E402
from rasterio.enums import Resampling                             # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--rain", type=float, default=20.0); ap.add_argument("--hours", type=int, default=24)
ap.add_argument("--n", type=int, default=20); ap.add_argument("--res", type=float, default=90.0)
ap.add_argument("--preset", default="colluvium_shallow"); ap.add_argument("--texture", default="sandy loam")
ap.add_argument("--tile", type=int, default=2048); ap.add_argument("--out", default=str(ROOT / "datasets/national"))
a = ap.parse_args()
os.nice(10)

name = f"stability_{a.preset}_{a.texture.replace(' ', '')}_{a.rain:g}mmh_{a.hours}h_{a.res:g}m_mob"   # _mob: stable-before-event, soil-bearing slopes only
out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
tif, done_f = out_dir / f"{name}.tif", out_dir / f"{name}.done.json"

bd = gpd.read_file(paths.get("BOUNDARY_SHP")).to_crs(32642)
x0, y0, x1, y1 = bd.total_bounds
res = a.res
X0, Y1 = np.floor(x0 / res) * res, np.ceil(y1 / res) * res
W, H = int(np.ceil((x1 - X0) / res)), int(np.ceil((Y1 - y0) / res))
aff = Affine(res, 0, X0, 0, -res, Y1)
print(f"national grid {W}x{H} @ {res} m = {W*H/1e6:.0f} M cells", flush=True)
spec, _ = P.build_spec({"strength_preset": a.preset, "texture": a.texture})

if not tif.exists():
    prof = dict(driver="GTiff", width=W, height=H, count=3, dtype="uint8", crs="EPSG:32642", transform=aff, nodata=255,
                tiled=True, blockxsize=512, blockysize=512, compress="lzw")
    with rasterio.open(tif, "w", **prof) as d:
        d.update_tags(model="infinite_slope+green_ampt scenario ensemble", rain_mm_h=a.rain, hours=a.hours, n_members=a.n,
                     preset=a.preset, texture=a.texture, status="not_calibrated screening_only",
                     bands="1=frac FS<1 pct; 2=median min FS x50; 3=slope deg")
done = set(json.loads(done_f.read_text())) if done_f.exists() else set()
t0 = time.time(); ntile = 0
for r0 in range(0, H, a.tile):
    for c0 in range(0, W, a.tile):
        key = f"{r0}_{c0}"
        if key in done:
            continue
        h, w = min(a.tile, H - r0), min(a.tile, W - c0)
        ta = aff * Affine.translation(c0, r0)
        sub = bd.geometry.union_all()
        grid = {"crs": "EPSG:32642", "affine": ta, "width": w, "height": h, "resolution_m": res}
        inside = rasterize([(sub, 1)], out_shape=(h, w), transform=ta, fill=0, dtype="uint8").astype(bool)
        if inside.any():
            dem = rasters.read(paths.get("DEM"), grid, Resampling.average)
            if dem is not None:
                valid = inside & np.isfinite(dem)
                if valid.any():
                    t = terrain.slope_aspect(np.where(np.isfinite(dem), dem, np.nanmedian(dem)), res, res)
                    slope = np.where(valid, t["slope_deg"], np.nan)
                    g, _ = P.stability_grid(slope, valid, a.rain, a.hours, spec, a.n, 0)   # GPU first, CPU fallback
                    blk = np.full((3, h, w), 255, "uint8")
                    blk[0] = np.where(valid, np.clip(np.rint(g["frac_lt1"] * 100), 0, 100), 255)
                    blk[1] = np.where(valid, np.clip(np.rint(np.nan_to_num(g["min_fs_p50"], nan=5.0) * 50), 0, 254), 255)
                    blk[2] = np.where(valid, np.clip(np.rint(slope), 0, 90), 255)
                    with rasterio.open(tif, "r+") as d:
                        d.write(blk, window=Window(c0, r0, w, h))
                    ntile += 1
        done.add(key); done_f.write_text(json.dumps(sorted(done)))
        print(f"tile {key} ok  ({ntile} computed, {time.time()-t0:.0f}s)", flush=True)
print("DONE", tif, flush=True)
