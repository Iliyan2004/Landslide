"""Site conditions for ground-motion amplification: time-averaged shear-wave velocity Vs30 (m/s) on the analysis grid.
Primary source: the USGS global Vs30 grid (Heath et al. 2020: terrain slope + geology/geomorphology; 30 arcsec) at datasets/external/vs30/vs30_pk.tif (scripts/build_vs30_pk.py cuts it from the global grid).
Fallback when the grid is absent: the slope proxy of Wald & Allen (2007) for active tectonic regions, anchors interpolated in log-log."""
from __future__ import annotations
import os
import numpy as np
from rasterio.enums import Resampling
from ..app import rasters

VS30 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "datasets", "external", "vs30", "vs30_pk.tif")
# (slope m/m, Vs30 m/s) anchors of the active-tectonic slope proxy
_ANCHORS = np.array([[1e-4, 180.0], [2.2e-3, 240.0], [6.3e-3, 300.0], [0.018, 360.0], [0.05, 490.0], [0.10, 620.0], [0.138, 760.0], [0.30, 900.0]])


def vs30_from_slope(slope_deg):
    s = np.maximum(np.tan(np.deg2rad(np.nan_to_num(slope_deg))), 1e-5)
    return np.exp(np.interp(np.log(s), np.log(_ANCHORS[:, 0]), np.log(_ANCHORS[:, 1]))).astype("float32")


def vs30_field(grid, slope_deg=None):
    """(vs30 array, source string). The USGS grid is read with bilinear resampling; cells it lacks fall back to the slope proxy when slope is given."""
    v = rasters.read(VS30, grid, Resampling.bilinear) if os.path.exists(VS30) else None
    if v is None:
        if slope_deg is None:
            return None, "none (rock 760 m/s assumed)"
        return vs30_from_slope(slope_deg), "slope proxy (Wald & Allen 2007)"
    if slope_deg is not None:
        miss = ~np.isfinite(v); v[miss] = vs30_from_slope(slope_deg)[miss]
    return np.clip(v, 150.0, 1500.0).astype("float32"), "USGS global Vs30 (Heath et al. 2020)"
