"""Before-and-after imagery and change mapping around a reported landslide (Earth Engine).

hist_assess(lon, lat, date) returns
  before / after   thumbnail URLs of true-colour composites over a 6 km square (Sentinel-2 from 2016, Landsat 8 for 2013 to 2015, Landsat 5 and 7 before)
  stats            vegetation loss, scar-candidate and disturbed-ground areas from the change in NDVI and the bare-soil index
  overlay          RGBA PNG (base64) of the candidate mask for the map, with its lon/lat corners
The compositing windows are 120 days before and 120 days after the report date (a day is left out on each side, because report dates have no time of
day), medians of cloud-masked scenes. Scenes in the two windows can differ in snow and season, so the result is evidence to look at, not a mapping.
"""
from __future__ import annotations
import base64, datetime as dt, io

import numpy as np
from PIL import Image
import requests

import aoi_ee as EEL

HALF = 3000.0


def _ndvi_bsi(col, kind):
    e = EEL.ee()
    if kind == "s2":
        def prep(i):
            scl = i.select("SCL")
            ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)).And(scl.neq(1))
            return i.updateMask(ok).select(["B2", "B3", "B4", "B8", "B11"], ["blue", "green", "red", "nir", "swir"]).divide(10000)
    else:
        l8 = kind == "l8"
        names = (["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"] if l8 else ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"])
        def prep(i):
            qa = i.select("QA_PIXEL")
            ok = qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0)).And(qa.bitwiseAnd(1 << 4).eq(0)).And(qa.bitwiseAnd(1 << 5).eq(0))
            return i.updateMask(ok).select(names, ["blue", "green", "red", "nir", "swir"]).multiply(0.0000275).add(-0.2)
    m = col.map(prep).median()
    ndvi = m.normalizedDifference(["nir", "red"]).rename("ndvi")
    bsi = m.expression("((s+r)-(n+b))/((s+r)+(n+b))", {"s": m.select("swir"), "r": m.select("red"), "n": m.select("nir"), "b": m.select("blue")}).rename("bsi")
    return m, ndvi, bsi


def _collection(date, region, start, end):
    e = EEL.ee()
    d = dt.date.fromisoformat(date)
    if d >= dt.date(2016, 1, 1):
        kind, col = "s2", e.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filter(e.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    elif d >= dt.date(2013, 5, 1):
        kind, col = "l8", e.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    else:
        kind, col = "l57", e.ImageCollection("LANDSAT/LE07/C02/T1_L2").merge(e.ImageCollection("LANDSAT/LT05/C02/T1_L2"))
    return kind, col.filterBounds(region).filterDate(start, end)


def hist_assess(lon, lat, date):
    e = EEL.ee()
    d = dt.date.fromisoformat(date)
    if d < dt.date(1999, 1, 1): raise ValueError("no usable satellite imagery before 1999")
    if d > dt.date.today() - dt.timedelta(days=10): raise ValueError("the report is too recent for an after image")
    cx, cy = _utm(lon, lat)
    reg = e.Geometry.Rectangle([cx - HALF, cy - HALF, cx + HALF, cy + HALF], "EPSG:32642", False)
    ll = _ll_bounds(cx, cy)
    b0, b1 = (d - dt.timedelta(days=120)).isoformat(), (d - dt.timedelta(days=1)).isoformat()
    a0, a1 = (d + dt.timedelta(days=1)).isoformat(), min(d + dt.timedelta(days=120), dt.date.today()).isoformat()
    kind, cb = _collection(date, reg, b0, b1)
    _, ca = _collection(date, reg, a0, a1)
    nb, na = cb.size().getInfo(), ca.size().getInfo()
    if nb == 0 or na == 0: raise ValueError(f"no usable scenes: {nb} before and {na} after (120 day windows)")
    mb, nb_, bb = _ndvi_bsi(cb, kind); ma, na_, ba = _ndvi_bsi(ca, kind)
    vis = {"bands": ["red", "green", "blue"], "min": 0.02, "max": 0.35 if kind != "s2" else 0.3, "gamma": 1.1}
    thumb = lambda im: im.visualize(**vis).getThumbURL({"region": reg, "dimensions": 512, "format": "png", "crs": "EPSG:32642"})
    url_b, url_a = thumb(mb), thumb(ma)
    dn, db = na_.subtract(nb_).rename("dndvi"), ba.subtract(bb).rename("dbsi")
    slope = e.Terrain.slope(e.Image("USGS/SRTMGL1_003")).rename("slope")
    img = e.Image.cat([dn, db, nb_.rename("ndvi0"), slope]).float()
    scale = 20 if kind == "s2" else 30
    n = int(2 * HALF / scale)
    url = img.getDownloadURL({"region": reg, "crs": "EPSG:32642", "scale": scale, "format": "GEO_TIFF"})
    r = requests.get(url, timeout=600); r.raise_for_status()
    import rasterio
    with rasterio.open(io.BytesIO(r.content)) as src:
        a = src.read().astype("float32")
    dndvi, dbsi, ndvi0, slp = a
    ok = np.isfinite(dndvi) & np.isfinite(dbsi) & np.isfinite(ndvi0)
    dndvi = np.where(ok, dndvi, 0); dbsi = np.where(ok, dbsi, 0); ndvi0 = np.where(ok, ndvi0, 0)
    veg = ndvi0 >= 0.3
    loss = (dndvi <= -0.15) & veg
    cand = loss & (dbsi >= 0.10)
    steep = cand & (slp >= 25); gentle = cand & (slp < 25)
    cell = scale * scale / 1e6
    rgba = np.zeros(a.shape[1:] + (4,), np.uint8)
    rgba[loss] = (255, 214, 74, 110); rgba[gentle] = (255, 140, 40, 200); rgba[steep] = (230, 50, 50, 220)
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    stats = dict(sensor={"s2": "Sentinel-2", "l8": "Landsat 8", "l57": "Landsat 5 and 7"}[kind], scale_m=scale, scenes_before=nb, scenes_after=na,
                 window_km2=(2 * HALF / 1000) ** 2, vegetated_km2=float(veg.sum() * cell), veg_loss_km2=float(loss.sum() * cell),
                 candidate_km2=float(cand.sum() * cell), source_km2=float(steep.sum() * cell), disturbed_km2=float(gentle.sum() * cell),
                 mean_dndvi_candidates=float(dndvi[cand & np.isfinite(dndvi)].mean()) if (cand & np.isfinite(dndvi)).any() else None, windows=dict(before=[b0, b1], after=[a0, a1]))
    return dict(before=url_b, after=url_a, stats=stats, overlay=base64.b64encode(buf.getvalue()).decode(), bounds=ll)


def _utm(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs(4326, 32642, always_xy=True).transform(lon, lat)


def _ll_bounds(cx, cy):
    from pyproj import Transformer
    t = Transformer.from_crs(32642, 4326, always_xy=True).transform
    return [list(t(cx - HALF, cy + HALF)), list(t(cx + HALF, cy + HALF)), list(t(cx + HALF, cy - HALF)), list(t(cx - HALF, cy - HALF))]
