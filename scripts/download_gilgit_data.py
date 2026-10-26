"""Download the datasets the Gilgit landslide pilot is missing, on the exact grid of gilgit_dem.tif.

Source choice per dataset (see docs/GILGIT_SMALL_SCALE_METHODOLOGY.md section 2):
  embeddings   Google Satellite Embedding V1 (Earth Engine)  -> scar detection, change, material proxy
  worldcover   ESA WorldCover v200 (Earth Engine)             -> land cover
  s2           Sentinel-2 SR dry-season composites (EE)       -> NDVI/NDMI/NBR/BSI, 2 epochs
  chirps       CHIRPS daily (EE), AOI mean 1981-today         -> rainfall history for thresholds
  worldpop     WorldPop 100 m (EE)                            -> population exposure
  buildings    Google Open Buildings v3 (EE)                  -> building footprints
  faults       GEM Global Active Faults (GitHub)              -> distance_fault

Not automatable (no open API): GLiM lithology, geotechnical samples, rock discontinuities.

Usage:  python scripts/download_gilgit_data.py --dry-run
        python scripts/download_gilgit_data.py --only worldcover s2 chirps
"""
import argparse, io, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import Window

ROOT = Path(r"D:\Downloads\CMIP6\landslide-platform").resolve().parents[2]
DEM = r"D:\Downloads\CMIP6\gilgit_dem.tif"
AOI = r"D:\Downloads\CMIP6\Shapefiles\Gilgit shp\Gilgit.shp"
OUT = ROOT / "datasets" / "raw" / "gilgit"
GEE_PROJECT = "bamboo-storm-482319-s1"
TILE = 512
EMB_YEARS = (2017, 2024)
S2_YEARS = (2018, 2024)
ALL = ["worldcover", "s2", "embeddings", "chirps", "worldpop", "buildings", "faults"]


def grid():
    with rasterio.open(DEM) as r:
        return r.crs.to_string(), r.transform, r.width, r.height


def fetch_tile(ee, img, crs, tf, x0, y0, w, h, retries=6):
    ox = tf.c + x0 * tf.a
    oy = tf.f + y0 * tf.e
    region = ee.Geometry.Rectangle([ox, oy + h * tf.e, ox + w * tf.a, oy], crs, False)
    params = dict(format="GEO_TIFF", crs=crs, crs_transform=[tf.a, 0, ox, 0, tf.e, oy], region=region)
    for k in range(retries):
        try:
            url = img.getDownloadURL(params)
            resp = requests.get(url, timeout=300)
            resp.raise_for_status()
            with rasterio.open(io.BytesIO(resp.content)) as src:
                return src.read()
        except Exception as e:  # EE throttling / transient network
            if k == retries - 1:
                raise
            time.sleep(4 * 2 ** k)


def export_image(ee, img, name, nbands, dtype, nodata=None):
    path = OUT / f"{name}.tif"
    if path.exists():
        print("skip (exists)", path.name)
        return
    crs, tf, W, H = grid()
    jobs = [(x, y, min(TILE, W - x), min(TILE, H - y)) for y in range(0, H, TILE) for x in range(0, W, TILE)]
    prof = dict(driver="GTiff", crs=crs, transform=tf, width=W, height=H, count=nbands, dtype=dtype,
                nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    tmp = path.with_suffix(".part")
    with rasterio.open(tmp, "w", **prof) as dst:
        with ThreadPoolExecutor(4) as ex:
            futs = [(j, ex.submit(fetch_tile, ee, img, crs, tf, *j)) for j in jobs]
            for n, ((x, y, w, h), f) in enumerate(futs, 1):
                dst.write(f.result().astype(dtype), window=Window(x, y, w, h))
                print(f"{name}: tile {n}/{len(jobs)}", end="\r")
    tmp.replace(path)
    print("\nwrote", path)


def aoi_geometry(ee):
    import geopandas as gpd
    g = gpd.read_file(AOI).to_crs(4326).geometry.union_all()
    return ee.Geometry(json.loads(gpd.GeoSeries([g]).to_json())["features"][0]["geometry"])


def get_worldcover(ee, aoi):
    img = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").toUint8()
    export_image(ee, img, "worldcover_2021", 1, "uint8", nodata=0)


def s2_composite(ee, aoi, year):
    def mask(i):
        scl = i.select("SCL")
        ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))  # shadow, cloud, cirrus, snow
        return i.updateMask(ok).divide(10000)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
           .filterDate(f"{year}-07-01", f"{year}-09-30").map(mask))
    m = col.median()
    ndvi = m.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndmi = m.normalizedDifference(["B8", "B11"]).rename("NDMI")
    nbr = m.normalizedDifference(["B8", "B12"]).rename("NBR")
    bsi = m.expression("((s+r)-(n+b))/((s+r)+(n+b))", {"s": m.select("B11"), "r": m.select("B4"),
                                                      "n": m.select("B8"), "b": m.select("B2")}).rename("BSI")
    return ee.Image.cat(ndvi, ndmi, nbr, bsi).toFloat()


def get_s2(ee, aoi):
    for y in S2_YEARS:
        export_image(ee, s2_composite(ee, aoi, y), f"s2_indices_{y}_JulSep", 4, "float32", nodata=-9999)


def get_embeddings(ee, aoi):
    """64 bands, stored as int8: q = round(sign(v)*sqrt(|v|)*127.5). Decode: v = sign(q)*(q/127.5)**2."""
    col = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
    for y in EMB_YEARS:
        c = col.filterDate(f"{y}-01-01", f"{y+1}-01-01").filterBounds(aoi)
        native = c.first().select(0).projection()
        m = c.mosaic().setDefaultProjection(native)
        m = m.reduceResolution(ee.Reducer.mean(), maxPixels=256)  # 10 m -> 26.6 m by averaging
        q = m.signum().multiply(m.abs().sqrt()).multiply(127.5).round().clamp(-127, 127).toInt8()
        export_image(ee, q, f"embedding_{y}_int8", 64, "int8", nodata=-128)


def get_chirps(ee, aoi):
    path = OUT / "chirps_daily_aoi_mean.csv"
    if path.exists():
        print("skip (exists)", path.name)
        return
    import pandas as pd
    rows = []
    for y in range(1981, time.gmtime().tm_year + 1):
        col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(f"{y}-01-01", f"{y+1}-01-01")
        fc = col.map(lambda i: ee.Feature(None, {"date": i.date().format("YYYY-MM-dd"),
                                                  "precip_mm": i.reduceRegion(ee.Reducer.mean(), aoi, 5566).get("precipitation")}))
        rows += [f["properties"] for f in fc.getInfo()["features"]]
        print("chirps", y, end="\r")
    pd.DataFrame(rows).to_csv(path, index=False)
    print("\nwrote", path)


def get_worldpop(ee, aoi):
    img = ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "PAK")).filter(ee.Filter.eq("year", 2020)).mosaic()
    export_image(ee, img.toFloat(), "worldpop_2020", 1, "float32", nodata=-9999)


def get_buildings(ee, aoi):
    path = OUT / "open_buildings_v3.geojson"
    if path.exists():
        print("skip (exists)", path.name)
        return
    fc = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(aoi).filter(ee.Filter.gte("confidence", 0.7))
    print("buildings in AOI (conf>=0.7):", fc.size().getInfo())
    url = fc.getDownloadURL("GEO_JSON")
    path.write_bytes(requests.get(url, timeout=600).content)
    print("wrote", path)


def get_faults(ee, aoi):
    import geopandas as gpd
    url = "https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/master/geojson/gem_active_faults_harmonized.geojson"
    path = OUT / "gem_active_faults_pakistan.gpkg"
    if path.exists():
        print("skip (exists)", path.name)
        return
    g = gpd.read_file(url).cx[60:82, 23:38]
    g.to_file(path, driver="GPKG")
    print("wrote", path, len(g), "faults")


FUNCS = dict(worldcover=get_worldcover, s2=get_s2, embeddings=get_embeddings, chirps=get_chirps,
             worldpop=get_worldpop, buildings=get_buildings, faults=get_faults)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=ALL, default=ALL)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    crs, tf, W, H = grid()
    print(f"grid: {crs}, {W}x{H}, {tf.a:.3f} m  ->  {OUT}")
    print("datasets:", ", ".join(a.only))
    if a.dry_run:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    import ee
    ee.Initialize(project=GEE_PROJECT)
    aoi = aoi_geometry(ee)
    for k in a.only:
        print(f"== {k}")
        try:
            FUNCS[k](ee, aoi)
        except Exception as e:
            print(f"FAILED {k}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
