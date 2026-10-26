#!/usr/bin/env python3
"""30 m slope raster (deg x2, uint8, 255=nodata) for the northern study region on the DEM's own grid (EPSG:32642).
Used by the calibration/validation package to sample terrain under any inventory point's location-uncertainty radius.
Horn (1981) slope from the 29 m SRTM DEM, computed in 4096-cell tiles with a 1-cell halo (torch on GPU if available)."""
import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import paths   # noqa: E402

OUT = ROOT / "datasets/derived/slope29_north_x2.tif"
LON0, LAT0, LON1, LAT1 = 69.0, 31.0, 77.5, 37.2
T = 4096
with rasterio.open(paths.get("DEM")) as src:
    tr = Transformer.from_crs(4326, src.crs, always_xy=True)
    xs, ys = zip(*[tr.transform(lo, la) for lo in np.linspace(LON0, LON1, 9) for la in np.linspace(LAT0, LAT1, 9)])
    c0, r0 = (~src.transform) * (min(xs), max(ys)); c1, r1 = (~src.transform) * (max(xs), min(ys))
    c0, r0 = max(0, int(c0)), max(0, int(r0)); c1, r1 = min(src.width, int(c1) + 1), min(src.height, int(r1) + 1)
    W, H = c1 - c0, r1 - r0
    aff = src.transform * rasterio.Affine.translation(c0, r0)
    dx = abs(src.res[0])
    print(f"window {W}x{H} cells ({W*H/1e6:.0f} M), dx={dx:.2f} m", flush=True)
    try:
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        torch, dev = None, "cpu"
    prof = dict(driver="GTiff", width=W, height=H, count=1, dtype="uint8", crs=src.crs, transform=aff, nodata=255, tiled=True,
                blockxsize=512, blockysize=512, compress="lzw")
    with rasterio.open(OUT, "w", **prof) as dst:
        for rr in range(0, H, T):
            for cc in range(0, W, T):
                h, w = min(T, H - rr), min(T, W - cc)
                ra, ca = max(0, rr - 1), max(0, cc - 1)
                rb, cb = min(H, rr + h + 1), min(W, cc + w + 1)
                z = src.read(1, window=Window(c0 + ca, r0 + ra, cb - ca, rb - ra), masked=True).astype("float32")
                bad = np.ma.getmaskarray(z); z = np.where(bad, np.nan, z.filled(0))
                if np.isnan(z).all():
                    continue
                zf = np.where(np.isnan(z), np.nanmedian(z), z)
                p = np.pad(zf, 1, mode="edge")
                a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]; d, f = p[1:-1, :-2], p[1:-1, 2:]; g, hh, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
                dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx); dzdy = ((a + 2 * b + c) - (g + 2 * hh + i)) / (8 * dx)
                s = np.rad2deg(np.arctan(np.hypot(dzdx, dzdy)))
                s = s[rr - ra:rr - ra + h, cc - ca:cc - ca + w]; bd = bad[rr - ra:rr - ra + h, cc - ca:cc - ca + w]
                q = np.where(bd, 255, np.clip(np.rint(s * 2), 0, 180)).astype("uint8")
                dst.write(q, 1, window=Window(cc, rr, w, h))
        print("done", OUT, flush=True)
