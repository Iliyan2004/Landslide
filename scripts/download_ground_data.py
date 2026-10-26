#!/usr/bin/env python3
"""Download ground-property rasters for Pakistan from ISRIC (windowed reads, nothing global is stored).
 - BDTICM: absolute depth to bedrock (SoilGrids 2017, 250 m, cm)  -> soil thickness for the infinite-slope model
 - clay / sand / silt / bdod / cfvo, 0-5, 5-15, 15-30, 30-60 cm (SoilGrids 2.0, 250 m) -> texture-based strength (see engine/ground.py)
Output: datasets/external/soilgrids/<name>.tif (EPSG:4326, Pakistan window). Existing files are skipped."""
import sys
from pathlib import Path
import rasterio
from rasterio.windows import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
import rasterio.transform
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "datasets/external/soilgrids"; OUT.mkdir(parents=True, exist_ok=True)
W, S, E, N = 60.5, 23.5, 77.9, 37.2
BD = "https://files.isric.org/soilgrids/former/2017-03-10/data/BDTICM_M_250m_ll.tif"
SG = "https://files.isric.org/soilgrids/latest/data/{p}/{p}_{d}_mean.vrt"
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]


def window(url, dst, res=0.0025):
    """Read the Pakistan window; SoilGrids 2.0 is in Interrupted Goode Homolosine so it is warped to EPSG:4326 (nearest, 0.0025 deg ~ 250 m)."""
    if dst.exists():
        print("skip", dst.name); return
    with rasterio.Env(GDAL_HTTP_MAX_RETRY=8, GDAL_HTTP_RETRY_DELAY=3, CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.vrt", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(url) as src:
            if src.crs.to_epsg() == 4326:
                win = from_bounds(W, S, E, N, src.transform).round_offsets().round_lengths()
                arr = src.read(1, window=win); tr = src.window_transform(win)
            else:
                w, h = int(round((E - W) / res)), int(round((N - S) / res)); tr = rasterio.transform.from_origin(W, N, res, res)
                with WarpedVRT(src, crs="EPSG:4326", transform=tr, width=w, height=h, resampling=Resampling.nearest) as v:
                    arr = v.read(1)
            nd = src.nodata
            with rasterio.open(dst.with_suffix(".part"), "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=arr.dtype, crs="EPSG:4326", transform=tr, compress="deflate", nodata=nd) as o:
                o.write(arr, 1)
            dst.with_suffix(".part").rename(dst)
    print("wrote", dst.name, arr.shape, flush=True)


if __name__ == "__main__":
    for p, ds in [("clay", DEPTHS), ("sand", DEPTHS), ("cfvo", ["15-30cm"]), ("bdod", ["15-30cm"])]:   # silt = 100 - clay - sand
        for d in ds:
            window(SG.format(p=p, d=d), OUT / f"{p}_{d}.tif")
    window(BD, OUT / "bdticm_cm.tif")
