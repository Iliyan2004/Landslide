"""A user's own elevation file (LiDAR, drone survey or another DEM) used in place of the Pakistan SRTM, as SAILAB's custom-DEM option.

The upload is checked (GeoTIFF with a coordinate system, one band, sane size), stored by content hash under datasets/state/custom_dem/, and described back to the user.
A run that carries params['custom_dem_id'] reads this file instead of the SRTM when the file covers the whole area; otherwise the run stops with a clear message
(never a silent mix of the two). A finer file allows a finer analysis grid (down to its own cell size, never below 5 m)."""
from __future__ import annotations
import hashlib, os, tempfile
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from ..errors import GateError

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "datasets" / "state" / "custom_dem"; DIR.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 800 * 1024 * 1024
MIN_RES_FLOOR = 5.0


def _path(did):
    return DIR / f"{did}.tif"


def store(fileobj):
    """Save an uploaded GeoTIFF; returns its description dict (raises GateError if unusable)."""
    tmp = Path(tempfile.mkstemp(suffix=".tif", dir=str(DIR))[1]); h = hashlib.sha256(); n = 0
    with open(tmp, "wb") as f:
        while True:
            b = fileobj.read(1 << 20)
            if not b:
                break
            n += len(b); h.update(b); f.write(b)
            if n > MAX_BYTES:
                tmp.unlink(); raise GateError([f"the file is larger than {MAX_BYTES // (1 << 20)} MB: clip it to your area first"])
    did = h.hexdigest()[:16]
    try:
        d = describe_file(tmp)
    except GateError:
        tmp.unlink(); raise
    except Exception as e:
        tmp.unlink(); raise GateError([f"could not read the file as a GeoTIFF: {str(e)[:120]}"])
    tmp.replace(_path(did)); d["id"] = did; return d


def describe_file(p):
    with rasterio.open(p) as s:
        if s.crs is None:
            raise GateError(["the file has no coordinate system: save it as a GeoTIFF with its CRS"])
        if s.count < 1:
            raise GateError(["the file has no raster band"])
        a = s.read(1, out_shape=(min(s.height, 512), min(s.width, 512)), masked=True)
        if a.count == 0:
            raise GateError(["the file contains no elevation values"])
        w, so, e, n = transform_bounds(s.crs, "EPSG:4326", *s.bounds)
        if s.crs.is_geographic:
            cell = float(abs(s.res[0]) * 111320.0 * np.cos(np.radians((so + n) / 2)))
        else:
            cell = float(abs(s.res[0]) * (s.crs.linear_units_factor[1] if s.crs.linear_units_factor else 1.0))
        lo, hi = float(a.min()), float(a.max())
        warn = []
        if hi - lo < 1.0:
            warn.append("the elevation range is under 1 m: this does not look like terrain")
        if not (-500 < lo and hi < 9000):
            warn.append("elevations outside -500 to 9000 m: check the vertical unit (metres expected)")
        return {"cellsize_m": round(cell, 2), "min_m": round(lo, 1), "max_m": round(hi, 1), "ncols": s.width, "nrows": s.height, "crs": s.crs.to_string(),
                "bounds_lonlat": [w, so, e, n], "nodata": s.nodata, "warnings": warn,
                "note": "Used instead of the Pakistan SRTM for runs whose area it fully covers; vertical unit is assumed to be metres."}


def info(did):
    p = _path(did)
    if not p.exists():
        return None
    d = describe_file(p); d["id"] = did; return d


def resolve(params, bbox_lonlat, default_path, default_min_res):
    """(dem_path, min_res_m, note). bbox_lonlat = (west, south, east, north) of the run's area. Raises GateError when a requested file is missing or does not cover the area."""
    did = (params or {}).get("custom_dem_id")
    if not did:
        return default_path, default_min_res, None
    p = _path(str(did))
    if not p.exists():
        raise GateError([f"the uploaded elevation file {did} is no longer on the server: upload it again"])
    with rasterio.open(p) as s:
        w, so, e, n = transform_bounds(s.crs, "EPSG:4326", *s.bounds)
        cell = float(abs(s.res[0]) * 111320.0 * np.cos(np.radians((so + n) / 2))) if s.crs.is_geographic else float(abs(s.res[0]) * (s.crs.linear_units_factor[1] if s.crs.linear_units_factor else 1.0))
    bw, bs, be, bn = bbox_lonlat
    if not (w <= bw and so <= bs and e >= be and n >= bn):
        raise GateError(["your elevation file does not cover the whole area: draw a smaller area inside it, or remove the file to use the Pakistan SRTM"])
    return str(p), max(MIN_RES_FLOOR, min(default_min_res, round(cell, 1))), f"Elevation from your uploaded file {did} ({cell:.1f} m cells)"
