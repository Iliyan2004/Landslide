"""Download Sentinel-2 change layers for the Gilgit grid: how much each cell's vegetation and bare-soil indices changed between
three July-September epochs (2017, 2020, 2024). Landslide scars show up as a drop in NDVI and a rise in the bare-soil index.

Bands written (int16, value x 1000), one file per epoch pair:
  s2_change_2017_2020.tif : dNDVI, dBSI, NDVI_pre, BSI_post
  s2_change_2020_2024.tif : dNDVI, dBSI, NDVI_pre, BSI_post
Usage: python scripts/download_s2_change.py [--test-tile]
"""
import argparse, io, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[2]
DEM = ROOT / "gilgit_dem.tif"
OUT = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit")
GEE_PROJECT = "bamboo-storm-482319-s1"
TILE = 256
EPOCHS = (2017, 2020, 2024)


def composite(ee, aoi, year):
    def mask(i):
        scl = i.select("SCL")
        ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)).And(scl.neq(1))
        return i.updateMask(ok).select(["B2", "B4", "B8", "B11"]).divide(10000)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).filterDate(f"{year}-07-01", f"{year}-09-30")
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(mask))
    m = col.median()
    ndvi = m.normalizedDifference(["B8", "B4"]).rename("NDVI")
    bsi = m.expression("((s+r)-(n+b))/((s+r)+(n+b))", {"s": m.select("B11"), "r": m.select("B4"), "n": m.select("B8"), "b": m.select("B2")}).rename("BSI")
    return ndvi, bsi


def pair_image(ee, aoi, y0, y1):
    n0, b0 = composite(ee, aoi, y0); n1, b1 = composite(ee, aoi, y1)
    return ee.Image.cat(n1.subtract(n0).rename("dNDVI"), b1.subtract(b0).rename("dBSI"), n0.rename("NDVI_pre"), b1.rename("BSI_post")).multiply(1000).round().clamp(-32000, 32000).toInt16()


def fetch_tile(ee, img, crs, tf, x0, y0, w, h, retries=5):
    ox, oy = tf.c + x0 * tf.a, tf.f + y0 * tf.e
    region = ee.Geometry.Rectangle([ox, oy + h * tf.e, ox + w * tf.a, oy], crs, False)
    params = dict(format="GEO_TIFF", crs=crs, crs_transform=[tf.a, 0, ox, 0, tf.e, oy], region=region)
    for k in range(retries):
        try:
            url = img.getDownloadURL(params)
            r = requests.get(url, timeout=600); r.raise_for_status()
            with rasterio.open(io.BytesIO(r.content)) as src: return src.read()
        except Exception as e:
            if k == retries - 1: raise
            time.sleep(5 * 2 ** k)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--test-tile", action="store_true"); a = ap.parse_args()
    import ee, geopandas as gpd, json
    ee.Initialize(project=GEE_PROJECT)
    g = gpd.read_file(ROOT / "Shapefiles/Gilgit shp/Gilgit.shp").to_crs(4326).geometry.union_all()
    aoi = ee.Geometry(json.loads(gpd.GeoSeries([g]).to_json())["features"][0]["geometry"])
    with rasterio.open(DEM) as r: crs, tf, W, H = r.crs.to_string(), r.transform, r.width, r.height
    pairs = [(2017, 2020), (2020, 2024)]
    jobs = [(x, y, min(TILE, W - x), min(TILE, H - y)) for y in range(0, H, TILE) for x in range(0, W, TILE)]
    if a.test_tile:
        t0 = time.time(); arr = fetch_tile(ee, pair_image(ee, aoi, 2017, 2020), crs, tf, 1500, 1500, 256, 256)
        print("test tile", arr.shape, "valid share", float((arr[0] != 0).mean()), "seconds", round(time.time() - t0, 1)); return
    for y0, y1 in pairs:
        path = OUT / f"s2_change_{y0}_{y1}.tif"
        if path.exists(): print("skip", path.name); continue
        img = pair_image(ee, aoi, y0, y1)
        prof = dict(driver="GTiff", crs=crs, transform=tf, width=W, height=H, count=4, dtype="int16", nodata=-32768, compress="deflate", tiled=True, blockxsize=256, blockysize=256)
        tmp = path.with_suffix(".part")
        with rasterio.open(tmp, "w", **prof) as dst, ThreadPoolExecutor(6) as ex:
            futs = [(j, ex.submit(fetch_tile, ee, img, crs, tf, *j)) for j in jobs]
            for n, ((x, y, w, h), f) in enumerate(futs, 1):
                try: dst.write(f.result().astype("int16"), window=Window(x, y, w, h))
                except Exception as e: print("tile failed", x, y, e, file=sys.stderr)
                print(f"{y0}-{y1}: tile {n}/{len(jobs)}", end="\r")
        tmp.replace(path); print("\nwrote", path)


if __name__ == "__main__":
    main()
