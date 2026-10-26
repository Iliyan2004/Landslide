"""Windowed, reprojected raster reads onto a frozen analysis grid. Works for a village or the whole country
because WarpedVRT only touches the tiles that overlap the requested grid."""
from __future__ import annotations
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom, transform_bounds
from ..data.preprocessing import aoi as AOI


def make_grid(bbox_lonlat, epsg, res_m):
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox_lonlat, densify_pts=21)
    g = AOI.grid_spec((x0, y0, x1, y1), res_m, epsg)
    t = g["transform"]
    return {**g, "affine": Affine(t[1], 0, t[0], 0, t[5], t[3])}


def read(path, grid, resampling=Resampling.bilinear, band=1, dtype="float32"):
    """Read `path` onto `grid`; nodata -> NaN. Returns None if the grid is wholly outside the raster."""
    with rasterio.open(path) as src:
        nd = src.nodata
        with WarpedVRT(src, crs=grid["crs"], transform=grid["affine"], width=grid["width"], height=grid["height"],
                       resampling=resampling, nodata=nd if nd is not None else np.nan) as v:
            a = v.read(band).astype(dtype)
    if nd is not None and np.isfinite(nd):
        a[a == nd] = np.nan
    a[a < -1e30] = np.nan
    return a if np.isfinite(a).any() else None


def polygon_mask(geojson, grid):
    g = transform_geom("EPSG:4326", grid["crs"], geojson)
    return rasterize([(g, 1)], out_shape=(grid["height"], grid["width"]), transform=grid["affine"], fill=0, dtype="uint8").astype(bool)


def cell_area_km2(grid):
    return grid["resolution_m"] ** 2 / 1e6
