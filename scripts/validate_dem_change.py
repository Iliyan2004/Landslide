#!/usr/bin/env python3
"""Look for the Attabad rock avalanche (Hunza, 4 January 2010; it dammed the river and made a 20 km lake) in a DEM difference.

Before: the server's Pak_srtm.tif (documented as SRTM, February 2000). After: Copernicus GLO-30 tiles N36 E074 and N36 E075 (open AWS bucket copernicus-dem-30m;
TanDEM-X data of 2011-2015, so after the event), downloaded to datasets/external/cop30/. Both are resampled to a 90 m grid in UTM 43N over a 70 km window around Hunza,
the difference is smoothed (sigma 270 m) to suppress sensor striping, and the largest coherent patches of change beyond 12 m are listed. An avalanche deposit tens of metres thick
over about a square kilometre, and the raised lake surface, should stand out. Writes docs/validation/dem_change_attabad.json."""
import glob, json, sys
from pathlib import Path
import numpy as np, rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from pyproj import Transformer
from scipy import ndimage
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import paths      # noqa: E402

CX, CY, RES, HALF, EPSG, THR = 74.80, 36.35, 90.0, 35000.0, 32643, 12.0
tfm = Transformer.from_crs(4326, EPSG, always_xy=True); x0, y0 = tfm.transform(CX, CY); W = int(2 * HALF / RES); tr = from_origin(x0 - HALF, y0 + HALF, RES, RES)


def load(ps):
    o = np.full((W, W), np.nan, "float32")
    for p in (ps if isinstance(ps, list) else [ps]):
        t = np.full((W, W), np.nan, "float32")
        with rasterio.open(p) as s:
            reproject(rasterio.band(s, 1), t, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=f"EPSG:{EPSG}", resampling=Resampling.average, src_nodata=s.nodata, dst_nodata=np.nan)
        o = np.where(np.isfinite(t), t, o)
    o[o < -1000] = np.nan; return o


b, a = load(paths.get("DEM")), load(sorted(glob.glob(str(ROOT / "datasets/external/cop30/cop_*.tif")))); dz = a - b
ok = np.isfinite(dz); f = np.where(ok, dz, 0.0); w = ok.astype(float); sm = ndimage.gaussian_filter(f, 3) / np.maximum(ndimage.gaussian_filter(w, 3), 1e-3); sm[~ok] = np.nan
patches = []
for name, m in (("loss", np.nan_to_num(sm) < -THR), ("gain", np.nan_to_num(sm) > THR)):
    lab, n = ndimage.label(m)
    if n:
        sz = ndimage.sum(m, lab, np.arange(1, n + 1))
        for t in np.argsort(-sz)[:3]:
            ys, xs = np.where(lab == t + 1); lon, lat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform(x0 - HALF + xs.mean() * RES, y0 + HALF - ys.mean() * RES)
            patches.append({"kind": name, "area_km2": float(sz[t] * RES * RES / 1e6), "lon": float(lon), "lat": float(lat), "mean_dz_m": float(np.nanmean(sm[lab == t + 1]))})
out = {"event": "Attabad rock avalanche, Hunza, 4 Jan 2010", "before": "Pak_srtm.tif (documented as SRTM, Feb 2000)", "after": "Copernicus GLO-30 (2011-2015)", "window_km": 2 * HALF / 1000, "grid_m": RES,
       "raw_dz_mad_m": float(np.nanmedian(np.abs(dz - np.nanmedian(dz))) * 1.4826), "smoothed_dz_percentiles_m": {k: float(np.nanpercentile(sm, q)) for k, q in (("p0.1", .1), ("p1", 1), ("p50", 50), ("p99", 99), ("p99.9", 99.9))},
       "smoothed_dz_extremes_m": [float(np.nanmin(sm)), float(np.nanmax(sm))], "patches_beyond_threshold": patches, "threshold_m": THR,
       "result": "no coherent change beyond the threshold anywhere in the window" if not patches else "patches found: see list"}
(ROOT / "docs/validation/dem_change_attabad.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
