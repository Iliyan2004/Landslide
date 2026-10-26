#!/usr/bin/env python3
"""Cut the USGS global Vs30 grid (netCDF without CRS, 30 arcsec) to Pakistan as a georeferenced GeoTIFF: datasets/external/vs30/vs30_pk.tif."""
from pathlib import Path
import numpy as np, xarray as xr, rasterio
from rasterio.transform import from_origin
ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "datasets/external/vs30"
W, S, E, N = 60.5, 23.5, 77.9, 37.2
ds = xr.open_dataset(D / "global_vs30.grd"); name = list(ds.data_vars)[0]; da = ds[name]
lon = [c for c in da.dims if c.startswith("lon") or c == "x"][0]; lat = [c for c in da.dims if c.startswith("lat") or c == "y"][0]
da = da.sortby(lat, ascending=False).sel({lon: slice(W, E), lat: slice(N, S)})
a = da.values.astype("float32"); dx = float(abs(da[lon][1] - da[lon][0])); dy = float(abs(da[lat][1] - da[lat][0]))
tr = from_origin(float(da[lon][0]) - dx / 2, float(da[lat][0]) + dy / 2, dx, dy)
with rasterio.open(D / "vs30_pk.tif", "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype="float32", crs="EPSG:4326", transform=tr, compress="deflate", nodata=np.nan) as o:
    o.write(a, 1)
print(name, a.shape, float(np.nanmin(a)), float(np.nanmedian(a)), float(np.nanmax(a)))
for nm, lo, la in [("Indus plain Multan", 71.5, 30.2), ("Karakoram Gilgit hills", 74.3, 36.0), ("Peshawar basin", 71.6, 34.0), ("Balochistan Kirthar", 67.0, 26.5)]:
    print(nm, float(da.sel({lon: lo, lat: la}, method="nearest")))
