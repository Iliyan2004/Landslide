"""Earth Engine layers for a user-drawn AOI, computed on the AOI's coarse (web) grid.

Every layer is reduced inside Earth Engine to the coarse cell (mean, mode or sum, from the native 10 to 250 m data), so each request returns
one small raster (a few hundred cells on a side) however large the area is. All functions take a Grid and return numpy arrays shaped
(bands, rows, cols) on exactly the coarse grid of the dashboard (EPSG:32642, north-up).
"""
from __future__ import annotations
import io, time, json
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
import requests

GEE_PROJECT = "bamboo-storm-482319-s1"
_ee = None


def ee():
    global _ee
    if _ee is None:
        import ee as _e
        _e.Initialize(project=GEE_PROJECT)
        _ee = _e
    return _ee


@dataclass
class Grid:
    crs: str          # "EPSG:32642"
    x0: float         # left edge of the coarse grid (m)
    y1: float         # top edge (m)
    cs: float         # coarse cell size (m)
    w: int
    h: int

    def region(self):
        e = ee()
        return e.Geometry.Rectangle([self.x0, self.y1 - self.h * self.cs, self.x0 + self.w * self.cs, self.y1], self.crs, False)

    def transform(self):
        return [self.cs, 0, self.x0, 0, -self.cs, self.y1]


def _download(img, g: Grid, retries=5, timeout=900, max_cells=None, threads=4):
    """Download a multi-band image on the coarse grid as a numpy array, in row bands: small enough for the request size limit, and for
    heavy layers small enough that Earth Engine finishes each band inside its time limit. Bands are fetched in parallel."""
    e = ee()
    nb = len(img.bandNames().getInfo())
    cap = int(30e6 // max(1, nb * 4))                         # request size: about 30 MB at 4 bytes per value
    cells = min(cap, max_cells) if max_cells else cap
    rows = max(2, min(g.h, cells // g.w))
    bands = [(r0, min(g.h, r0 + rows)) for r0 in range(0, g.h, rows)]

    def fetch(rr):
        r0, r1 = rr
        y1 = g.y1 - r0 * g.cs
        reg = e.Geometry.Rectangle([g.x0, y1 - (r1 - r0) * g.cs, g.x0 + g.w * g.cs, y1], g.crs, False)
        params = dict(format="GEO_TIFF", crs=g.crs, crs_transform=[g.cs, 0, g.x0, 0, -g.cs, y1], region=reg)
        for k in range(retries):
            try:
                url = img.getDownloadURL(params)
                resp = requests.get(url, timeout=timeout)
                if resp.status_code >= 400: raise RuntimeError(f"Earth Engine {resp.status_code}: {resp.text[:300]}")
                with rasterio.open(io.BytesIO(resp.content)) as src:
                    return rr, src.read()
            except Exception as ex:
                if k == retries - 1: raise
                time.sleep(4 * 2 ** k)
    out = None
    with ThreadPoolExecutor(threads) as pool:
        for (r0, r1), a in pool.map(fetch, bands):
            if out is None: out = np.zeros((a.shape[0], g.h, g.w), a.dtype)
            out[:, r0:r1, :] = a[:, :r1 - r0, :g.w]
    return out


def _cells_for(g, native_m, budget=12e6):
    """Largest number of coarse cells per request so the request's footprint stays under about 12 million native pixels (Earth Engine refuses larger reprojections)."""
    r = max(1.0, g.cs / native_m)
    return max(200, int(budget // (r * r)))


def _to_grid(img, g: Grid, reducer, native_scale_m, maxpix=65535):
    """Reduce an image from its native resolution to the coarse grid inside Earth Engine."""
    e = ee()
    ratio = max(1, int(round(g.cs / native_scale_m)))
    mp = min(maxpix, int(ratio * ratio * 2.4) + 64)
    return img.reduceResolution(reducer=reducer, maxPixels=mp).reproject(crs=g.crs, crsTransform=g.transform())


def worldcover(g: Grid):
    e = ee()
    img = e.ImageCollection("ESA/WorldCover/v200").first().select("Map").toUint8()
    return _download(_to_grid(img, g, e.Reducer.mode(), 10), g, max_cells=_cells_for(g, 10))[0]


def landcover_area_km2(poly_lonlat, scale=100):
    e = ee()
    img = e.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    h = img.reduceRegion(e.Reducer.frequencyHistogram(), e.Geometry(poly_lonlat), scale, maxPixels=int(1e10), bestEffort=True).getInfo()["Map"]
    return {int(float(k)): float(v) * scale * scale / 1e6 for k, v in h.items()}


def population(g: Grid):
    e = ee()
    col = e.ImageCollection("WorldPop/GP/100m/pop").filter(e.Filter.eq("country", "PAK")).filter(e.Filter.eq("year", 2020))
    img = col.mosaic().setDefaultProjection(col.first().projection()).toFloat().unmask(0)
    return _download(_to_grid(img, g, e.Reducer.sum(), 100), g, max_cells=_cells_for(g, 100))[0]


def buildings(g: Grid):
    """Count of Open Buildings v3 footprints (confidence 0.7 or more) per coarse cell, by footprint centroid."""
    e = ee()
    fc = e.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(g.region()).filter(e.Filter.gte("confidence", 0.7))
    pts = fc.map(lambda f: e.Feature(f.geometry().centroid(1), {"c": 1}))
    img = pts.reduceToImage(["c"], e.Reducer.count()).unmask(0).toFloat()
    return _download(img.reproject(crs=g.crs, crsTransform=g.transform()), g, max_cells=min(4000, _cells_for(g, 10)))[0]


def soil_texture(g: Grid):
    """Sand, silt, clay (g/kg), 0 to 30 cm depth-weighted, SoilGrids 2.0, bands in that order."""
    e = ee()
    def m030(n):
        im = e.Image(f"projects/soilgrids-isric/{n}_mean")
        return im.select(f"{n}_0-5cm_mean").multiply(5).add(im.select(f"{n}_5-15cm_mean").multiply(10)).add(im.select(f"{n}_15-30cm_mean").multiply(15)).divide(30).rename(n)
    img = e.Image.cat([m030("sand"), m030("silt"), m030("clay")]).float()
    return _download(img.reproject(crs=g.crs, crsTransform=g.transform()), g)


def _emb_year(y, g):
    e = ee()
    col = e.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate(f"{y}-01-01", f"{y+1}-01-01").filterBounds(g.region())
    return col.mosaic(), col.first().select(0).projection()


def embeddings(g: Grid):
    """The 2017 Satellite Embedding (64 bands) averaged to the coarse cell, as float32 [64, h, w].
    Uses the image pyramid (mean of the 10 m pixels), which is about three times faster than reduceResolution and correlates 0.98 with the exact mean."""
    e = ee()
    a, native = _emb_year(2017, g)
    q = a.signum().multiply(a.abs().sqrt()).multiply(127.5).round().clamp(-127, 127).toFloat().reproject(crs=g.crs, crsTransform=g.transform())
    parts = [_download(q.select(list(range(b0, b0 + 16))), g, max_cells=min(3000, _cells_for(g, 10))).astype("float32") for b0 in range(0, 64, 16)]
    emb = np.concatenate(parts, 0) / 127.5
    return np.sign(emb) * emb ** 2


def _s2_composite(y, region):
    e = ee()
    def mask(i):
        scl = i.select("SCL")
        ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)).And(scl.neq(1))
        return i.updateMask(ok).select(["B2", "B4", "B8", "B11"]).divide(10000)
    col = (e.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(f"{y}-07-01", f"{y}-09-30")
           .filter(e.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(mask))
    m = col.median()
    ndvi = m.normalizedDifference(["B8", "B4"])
    bsi = m.expression("((s+r)-(n+b))/((s+r)+(n+b))", {"s": m.select("B11"), "r": m.select("B4"), "n": m.select("B8"), "b": m.select("B2")})
    return ndvi, bsi


def scar_fraction(g: Grid, y0, y1):
    """Share (0 to 1) of each coarse cell that is a Sentinel-2 scar candidate between two July to September composites.
    Rule as in the Gilgit work: dNDVI <= -0.12 and dBSI >= 0.10, slope >= 15 degrees, not snow or water, below 4800 m, connected groups of 4 or more
    pixels, evaluated at 30 m."""
    e = ee()
    reg = g.region()
    n0, b0 = _s2_composite(y0, reg)
    n1, b1 = _s2_composite(y1, reg)
    proj30 = dict(crs=g.crs, scale=30)
    dn = n1.subtract(n0).reproject(**proj30)
    db = b1.subtract(b0).reproject(**proj30)
    dem = e.Image("USGS/SRTMGL1_003")
    slope = e.Terrain.slope(dem).reproject(**proj30)
    wc = e.ImageCollection("ESA/WorldCover/v200").first().select("Map").reproject(**proj30)
    cand = dn.lte(-0.12).And(db.gte(0.10)).And(slope.gte(15)).And(wc.neq(70)).And(wc.neq(80)).And(wc.neq(0)).And(dem.lt(4800))
    cand = cand.selfMask()
    big = cand.connectedPixelCount(8, True).gte(4)
    frac = big.unmask(0).toFloat().reproject(**proj30)
    return _download(_to_grid(frac, g, e.Reducer.mean(), 30), g, max_cells=min(4000, _cells_for(g, 30)))[0]


def chirps_daily_mean(poly_lonlat, years=range(1981, 2027), threads=8):
    """Daily CHIRPS precipitation (mm) averaged over the AOI, 1981 to the present, as a pandas Series."""
    import pandas as pd
    e = ee()
    geom = e.Geometry(poly_lonlat)
    def one(y):
        col = e.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(f"{y}-01-01", f"{y+1}-01-01")
        fc = col.map(lambda i: e.Feature(None, {"date": i.date().format("YYYY-MM-dd"),
                                                "p": i.reduceRegion(e.Reducer.mean(), geom, 5566, bestEffort=True).get("precipitation")}))
        for k in range(5):
            try:
                return [f["properties"] for f in fc.getInfo()["features"]]
            except Exception:
                time.sleep(3 + 3 * k)
        return []
    with ThreadPoolExecutor(threads) as ex:
        rows = [r for part in ex.map(one, list(years)) for r in part]
    s = pd.DataFrame(rows)
    s["date"] = pd.to_datetime(s["date"]); s = s.set_index("date")["p"].astype(float).sort_index()
    return s.rename("precip_mm")
