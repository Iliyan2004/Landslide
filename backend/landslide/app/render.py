"""Colour ramps -> PNG. Overlays are reprojected to EPSG:4326 so Mapbox image sources line up."""
from __future__ import annotations
import io
import numpy as np
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds

# name: (stops [(value, rgb)], vmin, vmax, label, unit)
RAMPS = {
    "min_fs_p50": ([(0.0, (127, 0, 0)), (0.8, (215, 48, 39)), (1.0, (252, 141, 89)), (1.3, (254, 224, 139)), (2.0, (166, 217, 106)), (4.0, (26, 150, 65))], "Median minimum FS", ""),
    "frac_lt1": ([(0.0, (255, 255, 204)), (0.25, (254, 217, 118)), (0.5, (253, 141, 60)), (0.75, (227, 26, 28)), (1.0, (128, 0, 38))], "Share of members FS<1", ""),
    "lsm_prob": ([(0.0, (26, 150, 65)), (0.4, (255, 255, 191)), (0.7, (253, 174, 97)), (1.0, (165, 0, 38))], "National susceptibility (ML)", ""),
    "newmark_cm": ([(0.0, (255, 255, 204)), (2.0, (254, 204, 92)), (10.0, (253, 141, 60)), (50.0, (227, 26, 28)), (100.0, (128, 0, 38))], "Newmark displacement", "cm"),
    "runout_freq": ([(0.0, (255, 245, 240)), (0.5, (252, 146, 114)), (1.0, (103, 0, 13))], "Run-out envelope frequency", ""),
    "slope_deg": ([(0.0, (255, 255, 229)), (15.0, (217, 240, 163)), (30.0, (120, 198, 121)), (45.0, (35, 132, 67)), (70.0, (0, 69, 41))], "Slope", "deg"),
    "hmax": ([(0.0, (255, 245, 214)), (0.5, (240, 190, 110)), (2.0, (200, 120, 50)), (5.0, (125, 66, 24)), (12.0, (58, 31, 10))], "Maximum flow depth", "m"),
    "vmax": ([(0.0, (255, 240, 200)), (3.0, (250, 190, 70)), (8.0, (240, 100, 40)), (15.0, (170, 20, 20))], "Maximum flow speed", "m/s"),
    "deposit": ([(0.0, (255, 250, 230)), (0.5, (228, 190, 130)), (2.0, (190, 130, 70)), (6.0, (110, 62, 24))], "Net deposit thickness", "m"),
    "scour": ([(0.0, (255, 255, 255)), (0.5, (190, 215, 235)), (1.5, (80, 140, 200)), (4.0, (20, 60, 130))], "Scar / scour depth", "m"),
    "t_fail_h": ([(0.0, (255, 255, 178)), (3.0, (253, 141, 60)), (8.0, (189, 0, 38)), (24.0, (60, 0, 20))], "Failure time", "h"),
    "pga_g": ([(0.0, (255, 255, 204)), (0.1, (161, 218, 180)), (0.25, (254, 217, 118)), (0.5, (240, 59, 32)), (1.0, (110, 0, 40))], "Peak ground acceleration", "g"),
    "crit_rain_mm": ([(0.0, (127, 0, 0)), (50.0, (215, 48, 39)), (150.0, (252, 141, 89)), (300.0, (254, 224, 139)), (600.0, (26, 150, 65))], "Rain needed to fail (24 h)", "mm"),
    "risk_index": ([(0.0, (255, 255, 204)), (0.06, (254, 217, 118)), (0.2, (253, 141, 60)), (0.28, (128, 0, 38))], "Risk index (hazard x exposure x vulnerability)", ""),
}


def colorize(a, name, alpha=0.82):
    stops, _, _ = RAMPS[name]
    xs = np.array([s[0] for s in stops], float)
    cols = np.array([s[1] for s in stops], float)
    ok = np.isfinite(a)
    rgba = np.zeros(a.shape + (4,), np.uint8)
    v = np.where(ok, a, xs[0])
    for k in range(3):
        rgba[..., k] = np.interp(v, xs, cols[:, k]).astype(np.uint8)
    rgba[..., 3] = np.where(ok, int(255 * alpha), 0)
    return rgba


def to_png(rgba):
    b = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(b, "PNG", optimize=False)
    return b.getvalue()


def overlay_png(a, grid, name, max_px=2400):
    """Return (png_bytes, [[w,n],[e,n],[e,s],[w,s]] corner coordinates)."""
    h, w = a.shape
    src_t = grid["affine"]
    west, south, east, north = transform_bounds(grid["crs"], "EPSG:4326", *array_bounds(h, w, src_t), densify_pts=21)
    s = max(1.0, max(h, w) / max_px)
    ow, oh = int(w / s), int(h / s)
    dst = np.full((oh, ow), np.nan, np.float32)
    reproject(a.astype(np.float32), dst, src_transform=src_t, src_crs=CRS.from_string(grid["crs"]),
              dst_transform=from_bounds(west, south, east, north, ow, oh), dst_crs="EPSG:4326",
              src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
    return to_png(colorize(dst, name)), [[west, north], [east, north], [east, south], [west, south]]
