"""Exposure layers for an AOI: Google Open Buildings (local parquet tiles), HOTOSM roads, hospitals, schools.
Same server data SAILAB reads (read-only); nothing is copied or modified."""
from __future__ import annotations
import glob, math, os
import numpy as np
from . import paths

FLOOD = os.path.expanduser("~/Desktop/DGX-Shared/Tasks/Reselli_AI/flood/global_data")
BUILD_DIR = os.environ.get("LANDSLIDE_BUILDINGS", os.path.join(FLOOD, "buildings_pk"))
ROADS = os.environ.get("LANDSLIDE_ROADS", os.path.join(FLOOD, "roads_pk", "pak_roads_indexed.gpkg"))
VEC = os.path.join(paths.SHARE, "4. Vector Data")
HOSPITALS = os.path.join(VEC, "Hospital", "Hospitals.shp")
SCHOOLS = os.path.join(VEC, "Schools", "Schools.shp")
ASSUMED_HEIGHT_M = 6.0


def quadkey(lat, lon, zoom=6):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    q = ""
    for i in range(zoom, 0, -1):
        d, m = 0, 1 << (i - 1)
        if x & m: d += 1
        if y & m: d += 2
        q += str(d)
    return q


def buildings(bbox, aoi_geom=None, limit=40000):
    """List of {coords_lonlat, area_m2, height_m} inside bbox (and AOI polygon if given)."""
    import duckdb
    from shapely import wkt as swkt
    from shapely.geometry import shape
    lon0, lat0, lon1, lat1 = bbox
    files = {quadkey(la, lo) for la in (lat0, lat1) for lo in (lon0, lon1)}
    srcs = [os.path.join(BUILD_DIR, f"PK_{q}.parquet") for q in files]
    srcs = [s for s in srcs if os.path.exists(s)]
    if not srcs:
        return []
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    poly = shape(aoi_geom) if aoi_geom else None
    out = []
    for s in srcs:
        rows = con.execute(f"SELECT area_in_meters, ST_AsText(geometry) FROM read_parquet('{s}') "
                           f"WHERE ST_Intersects(geometry, ST_MakeEnvelope({lon0},{lat0},{lon1},{lat1}))").fetchall()
        for a, w in rows:
            g = swkt.loads(w)
            if g.geom_type == "MultiPolygon":
                g = max(g.geoms, key=lambda p: p.area)
            if poly is not None and not poly.contains(g.centroid):
                continue
            out.append({"coords_lonlat": [list(c) for c in g.exterior.coords], "area_m2": float(a), "height_m": ASSUMED_HEIGHT_M,
                        "cx": g.centroid.x, "cy": g.centroid.y})
    if len(out) > limit:
        out.sort(key=lambda b: -b["area_m2"]); out = out[:limit]
    return out


def roads(bbox, aoi_geom=None, limit=6000):
    import geopandas as gpd
    from shapely.geometry import shape, box
    if not os.path.exists(ROADS):
        return []
    g = gpd.read_file(ROADS, bbox=tuple(bbox))
    poly = shape(aoi_geom) if aoi_geom else box(*bbox)
    out = []
    for _, r in g.iterrows():
        geom = r.geometry.intersection(poly)
        if geom.is_empty:
            continue
        lines = [geom] if geom.geom_type == "LineString" else [x for x in getattr(geom, "geoms", []) if x.geom_type == "LineString"]
        for ln in lines:
            out.append({"coords_lonlat": [list(c) for c in ln.coords], "class": str(r.get("highway", r.get("fclass", "road")))})
    return out[:limit]


def facilities(bbox, aoi_geom=None):
    import geopandas as gpd
    from shapely.geometry import shape, box
    poly = shape(aoi_geom) if aoi_geom else box(*bbox)
    res = []
    for kind, p in (("hospital", HOSPITALS), ("school", SCHOOLS)):
        if os.path.exists(p):
            g = gpd.read_file(p, bbox=tuple(bbox)).to_crs(4326)
            for _, r in g.iterrows():
                if poly.contains(r.geometry.centroid):
                    res.append({"kind": kind, "lon": r.geometry.centroid.x, "lat": r.geometry.centroid.y,
                                "name": str(next((r[c] for c in g.columns if "name" in c.lower() and r[c]), kind))})
    return res
