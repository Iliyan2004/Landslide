"""Exposure data for the impact assessment: roads and bridges, critical facilities, settlements and building footprints.

All coordinates are metres relative to the page's extent: (E - x0, y1 - N), so the browser can work in the same frame as the replay window.
Sources: OpenStreetMap Pakistan extract (Geofabrik) for roads, bridges, facilities and places; Google Open Buildings v3 for building footprints
(from the local GeoJSON for the Gilgit sample, from Earth Engine for other areas).
"""
from __future__ import annotations
import base64, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
OSM = ROOT / "landslide-platform/datasets/raw/gilgit/osm/pakistan.gpkg"
ROAD_CLASS = {"motorway": 0, "motorway_link": 0, "trunk": 0, "trunk_link": 0, "primary": 0, "primary_link": 0,
              "secondary": 1, "secondary_link": 1, "tertiary": 1, "tertiary_link": 1,
              "unclassified": 2, "residential": 2, "living_street": 2,
              "track": 3, "track_grade1": 3, "track_grade2": 3, "track_grade3": 3, "track_grade4": 3, "track_grade5": 3}
ROAD_NAMES = ["highway or primary", "secondary or tertiary", "local road", "track"]
POI_KIND = {"hospital": "hospital", "clinic": "clinic", "doctors": "clinic", "school": "school", "kindergarten": "school", "college": "school", "university": "school",
            "police": "police", "fire_station": "fire", "water_tower": "water", "water_well": "water", "water_works": "water", "wastewater_plant": "water"}
PLACES = ("city", "town", "village", "hamlet", "suburb")
BUILDING_MAX_KM2 = 6000.0            # building footprints are embedded only for areas up to this size
MAX_BUILDINGS = 900000


def _rel(xs, ys, x0, y1):
    return np.round(np.asarray(xs) - x0).astype(int), np.round(y1 - np.asarray(ys)).astype(int)


def osm_infra(x0, y0, x1, y1, crs, small=False):
    """Roads (with bridge and tunnel flags), facilities and places inside the extent. `small` keeps only the two main road classes."""
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform
    lo0, la0 = to_ll(x0, y0); lo1, la1 = to_ll(x1, y1)
    bb = (min(lo0, lo1) - .01, min(la0, la1) - .01, max(lo0, lo1) + .01, max(la0, la1) + .01)
    ext = box(x0, y0, x1, y1)
    out = {"roads": [], "pois": [], "places": []}
    rd = gpd.read_file(OSM, layer="gis_osm_roads_free", bbox=bb)
    rd = rd[rd.fclass.isin(ROAD_CLASS)].to_crs(crs)
    if small: rd = rd[rd.fclass.map(ROAD_CLASS) <= 1]
    for _, w in rd.iterrows():
        gm = w.geometry.intersection(ext)
        if gm.is_empty: continue
        for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if ln.geom_type != "LineString" or ln.length < 8: continue
            ln = ln.simplify(5)
            ex, ey = _rel([c[0] for c in ln.coords], [c[1] for c in ln.coords], x0, y1)
            out["roads"].append(dict(c=ROAD_CLASS[w.fclass], b=int(str(w.bridge) == "T"), t=int(str(w.tunnel) == "T"), n=(str(w["name"])[:40] if w["name"] else ""), xy=[int(v) for p in zip(ex, ey) for v in p]))
    pts = []
    for layer in ("gis_osm_pois_free", "gis_osm_pois_a_free"):
        g = gpd.read_file(OSM, layer=layer, bbox=bb)
        g = g[g.fclass.isin(POI_KIND)].to_crs(crs)
        if len(g): g["geometry"] = g.geometry.centroid
        pts.append(g)
    g = pd.concat(pts) if pts else None
    if g is not None and len(g):
        g = g[g.geometry.within(ext)]
        ex, ey = _rel(g.geometry.x, g.geometry.y, x0, y1)
        for k, (f, nm) in enumerate(zip(g.fclass, g["name"])):
            out["pois"].append(dict(k=POI_KIND[f], n=(str(nm)[:40] if nm else ""), x=int(ex[k]), y=int(ey[k])))
    pl = gpd.read_file(OSM, layer="gis_osm_places_free", bbox=bb)
    pl = pl[pl.fclass.isin(PLACES) & pl["name"].notna()].to_crs(crs)
    pl = pl[pl.geometry.within(ext)]
    ex, ey = _rel(pl.geometry.x, pl.geometry.y, x0, y1)
    for k, (c, nm, pp) in enumerate(zip(pl.fclass, pl["name"], pl["population"])):
        out["places"].append(dict(n=str(nm)[:40], c=c, p=int(pp) if pd.notna(pp) and pp else 0, x=int(ex[k]), y=int(ey[k])))
    return out


def pack_buildings(xs, ys, areas, x0, y1, inside=None):
    """Building centroids as Float32 (x, y) pairs in metres from the extent corner and footprint areas as uint16 m2 (capped)."""
    xs, ys, areas = np.asarray(xs, float), np.asarray(ys, float), np.asarray(areas, float)
    _, keep = np.unique(np.round(np.column_stack([xs, ys]) * 2).astype(np.int64), axis=0, return_index=True)   # tiles overlap: drop duplicate centroids
    xs, ys, areas = xs[keep], ys[keep], areas[keep]
    if inside is not None:
        m = inside(xs, ys); xs, ys, areas = xs[m], ys[m], areas[m]
    n = len(xs)
    if n == 0 or n > MAX_BUILDINGS: return None
    xy = np.empty(2 * n, "<f4"); xy[0::2] = xs - x0; xy[1::2] = y1 - ys
    return dict(n=n, xy=base64.b64encode(xy.tobytes()).decode(), area=base64.b64encode(np.clip(np.round(areas), 1, 65535).astype("<u2").tobytes()).decode())


def buildings_local(geojson, crs, x0, y0, x1, y1, x1y):
    """Gilgit sample: from the local Open Buildings GeoJSON."""
    g = gpd.read_file(geojson).to_crs(crs)
    c = g.geometry.centroid
    m = (c.x >= x0) & (c.x <= x1) & (c.y >= y0) & (c.y <= y1)
    col = "area_in_meters" if "area_in_meters" in g.columns else None
    ar = g[col].values[m.values] if col else g.geometry.area.values[m.values]
    return c.x.values[m.values], c.y.values[m.values], ar


def buildings_ee(poly_ll, crs, x0, y0, x1, y1, tile_km=14.0, threads=4):
    """Open Buildings v3 centroids and areas inside the polygon from Earth Engine, in tiles."""
    import requests
    import aoi_ee as EEL
    e = EEL.ee()
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform
    to_xy = Transformer.from_crs(4326, crs, always_xy=True).transform
    t = tile_km * 1000
    tiles = [(a, b) for a in np.arange(x0, x1, t) for b in np.arange(y0, y1, t)]
    col = e.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
    def fetch(tb):
        a, b = tb
        lo0, la0 = to_ll(a, b); lo1, la1 = to_ll(min(a + t, x1), min(b + t, y1))
        rect = e.Geometry.Rectangle([lo0, la0, lo1, la1])
        fc = col.filterBounds(rect).filter(e.Filter.gte("confidence", 0.7))
        def f(ft):
            c = ft.geometry().centroid(1).coordinates()
            return e.Feature(None, {"lon": c.get(0), "lat": c.get(1), "area": ft.get("area_in_meters")})
        for k in range(4):
            try:
                url = fc.map(f).getDownloadURL(filetype="csv", selectors=["lon", "lat", "area"])
                r = requests.get(url, timeout=600); r.raise_for_status()
                d = pd.read_csv(io.BytesIO(r.content))
                if len(d):
                    x, y = to_xy(d.lon.values, d.lat.values)
                    return np.asarray(x), np.asarray(y), d.area.values
                return np.array([]), np.array([]), np.array([])
            except Exception:
                import time; time.sleep(3 + 4 * k)
        return np.array([]), np.array([]), np.array([])
    with ThreadPoolExecutor(threads) as ex:
        parts = list(ex.map(fetch, tiles))
    xs = np.concatenate([p[0] for p in parts]); ys = np.concatenate([p[1] for p in parts]); ar = np.concatenate([p[2] for p in parts])
    return xs, ys, ar
