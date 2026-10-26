"""Score a finished run against an OBSERVED deposit / affected extent supplied by the user (polygons as GeoJSON or zipped shapefile, or a
raster of 0/1). The model extent is the cells reached by the flow at the chosen depth threshold (default 0.3 m). Metrics: CSI (critical
success index), POD, false-alarm ratio, F1, IoU, frequency bias. All are computed on the run's own grid, inside the analysed area."""
from __future__ import annotations
import io, json, zipfile, tempfile
from pathlib import Path
import numpy as np
from rasterio.features import rasterize


def observed_mask(raw, filename, grid):
    import geopandas as gpd
    name = filename.lower()
    if name.endswith((".tif", ".tiff")):
        import rasterio
        from rasterio.io import MemoryFile
        from ..app import rasters
        with MemoryFile(raw) as mf:
            with mf.open() as src:
                from rasterio.vrt import WarpedVRT
                with WarpedVRT(src, crs=grid["crs"], transform=grid["affine"], width=grid["width"], height=grid["height"], nodata=0) as v:
                    return v.read(1) > 0
    if name.endswith(".zip"):
        td = tempfile.mkdtemp(); zipfile.ZipFile(io.BytesIO(raw)).extractall(td)
        g = gpd.read_file(next(Path(td).rglob("*.shp")))
    else:
        g = gpd.read_file(io.BytesIO(raw))
    g = g.to_crs(grid["crs"])
    return rasterize([(geom, 1) for geom in g.geometry if geom is not None and not geom.is_empty], out_shape=(grid["height"], grid["width"]),
                     transform=grid["affine"], fill=0, dtype="uint8").astype(bool)


def score(model, obs, valid):
    m, o = model & valid, obs & valid
    tp = int((m & o).sum()); fp = int((m & ~o).sum()); fn = int((~m & o).sum())
    div = lambda a, b: float(a / b) if b > 0 else None
    return {"hits": tp, "false_alarms": fp, "misses": fn, "observed_cells": int(o.sum()), "model_cells": int(m.sum()),
            "CSI": div(tp, tp + fp + fn), "POD": div(tp, tp + fn), "FAR": div(fp, tp + fp), "F1": div(2 * tp, 2 * tp + fp + fn),
            "IoU": div(tp, tp + fp + fn), "bias": div(tp + fp, tp + fn)}
