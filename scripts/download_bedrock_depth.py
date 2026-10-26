#!/usr/bin/env python3
"""Depth to bedrock (SoilGrids 2017 BDTICM, 250 m, cm) for Pakistan, read in row chunks with progress (the source is strip-organised, 172800 px wide, so a
window costs a full-width strip per row; ~1 GB for Pakistan). Output datasets/external/soilgrids/bdticm_cm.tif. Resumable: finished chunks are kept in a .npy cache."""
import sys, time
from pathlib import Path
import numpy as np, rasterio
from rasterio.windows import from_bounds, Window
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "datasets/external/soilgrids"; TMP = ROOT / "datasets/external/_bd_chunks"; TMP.mkdir(exist_ok=True)
W, S, E, N = 60.5, 23.5, 77.9, 37.2
URL = "https://files.isric.org/soilgrids/former/2017-03-10/data/BDTICM_M_250m_ll.tif"
CH = 60
with rasterio.Env(GDAL_HTTP_MAX_RETRY=10, GDAL_HTTP_RETRY_DELAY=5, CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=120, CPL_VSIL_CURL_CHUNK_SIZE=2097152):
    with rasterio.open(URL) as src:
        win = from_bounds(W, S, E, N, src.transform).round_offsets().round_lengths(); nd = src.nodata
        t0 = time.time(); parts = []
        for k, r0 in enumerate(range(0, win.height, CH)):
            f = TMP / f"c{k:03d}.npy"
            if f.exists():
                parts.append(np.load(f)); continue
            h = min(CH, win.height - r0)
            for attempt in range(8):                                   # a dropped connection fails a whole strip read: retry the chunk
                try:
                    a = src.read(1, window=Window(win.col_off, win.row_off + r0, win.width, h)); break
                except Exception as e:
                    print("retry", k, attempt, str(e)[:80], flush=True); time.sleep(10)
            else:
                raise RuntimeError(f"chunk {k} failed 8 times")
            np.save(f, a); parts.append(a)
            print(f"chunk {k} rows {r0}-{r0 + h} of {win.height}  {time.time() - t0:.0f}s", flush=True)
        arr = np.concatenate(parts, 0); tr = src.window_transform(win)
        with rasterio.open(OUT / "bdticm_cm.tif", "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=arr.dtype, crs="EPSG:4326", transform=tr, compress="deflate", nodata=nd) as o:
            o.write(arr, 1)
print("done", arr.shape, float(np.nanmedian(np.where(arr == nd, np.nan, arr))))
