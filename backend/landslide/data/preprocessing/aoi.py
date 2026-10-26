"""AOI validation, hashing and CRS selection (§4.1). Pure python (shapely/pyproj optional at the edges)."""
from __future__ import annotations
import hashlib, json, math
from ...errors import GateError

PAKISTAN_BBOX = (60.8, 23.6, 77.9, 37.2)   # lon_min, lat_min, lon_max, lat_max (loose national envelope)


def _rings(geom):
    t = geom["type"]
    if t == "Polygon":
        return [geom["coordinates"][0]]
    if t == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    raise GateError([f"AOI geometry must be Polygon/MultiPolygon, got {t}"])


def _segments_intersect(p1, p2, p3, p4):
    def o(a, b, c): return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = o(p3, p4, p1), o(p3, p4, p2), o(p1, p2, p3), o(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def validate_geojson(geom: dict, max_area_km2=50000.0):
    """Reject self-intersections, unclosed/degenerate rings, out-of-range coords. Returns (bbox, area_km2, warnings)."""
    errors, warnings = [], []
    pts_all = []
    for ring in _rings(geom):
        if len(ring) < 4 or ring[0] != ring[-1]:
            errors.append("ring must be closed with >=4 positions")
            continue
        for x, y in ring:
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                errors.append(f"coordinate out of range: {x},{y}")
        n = len(ring) - 1
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if _segments_intersect(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                    errors.append("self-intersecting ring")
                    break
            else:
                continue
            break
        pts_all += ring
    if errors:
        raise GateError(sorted(set(errors)))
    xs, ys = [p[0] for p in pts_all], [p[1] for p in pts_all]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    area = sum(_ring_area_km2(r) for r in _rings(geom))
    if area > max_area_km2:
        raise GateError([f"AOI area {area:.0f} km2 exceeds quota {max_area_km2:.0f} km2"])
    pb = PAKISTAN_BBOX
    if bbox[0] < pb[0] or bbox[1] < pb[1] or bbox[2] > pb[2] or bbox[3] > pb[3]:
        warnings.append("AOI extends outside Pakistan envelope: local recalibration required")
    return bbox, area, warnings


def _ring_area_km2(ring):
    """Spherical-excess-free approximation: equirectangular around centroid latitude (adequate for quota checks)."""
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    k = 111.32
    xy = [((x * k * math.cos(lat0)), (y * k)) for x, y in ring]
    a = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def aoi_sha256(geom):
    def rnd(o):
        return [rnd(i) for i in o] if isinstance(o, list) else round(o, 7)
    return hashlib.sha256(json.dumps({"t": geom["type"], "c": rnd(geom["coordinates"])}, sort_keys=True).encode()).hexdigest()


def utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def select_analysis_crs(bbox):
    """UTM EPSG from AOI centroid; warns when the AOI spans zones (Pakistan spans UTM 42N-44N)."""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    z0, z1 = int((bbox[0] + 180) // 6) + 1, int((bbox[2] + 180) // 6) + 1
    warn = [f"AOI crosses UTM zones {z0}-{z1}; distortion grows away from the central meridian"] if z0 != z1 else []
    return utm_epsg(cx, cy), warn


def buffered_bbox(bbox, buffer_m):
    lat = (bbox[1] + bbox[3]) / 2
    dlat = buffer_m / 111320.0
    dlon = buffer_m / (111320.0 * math.cos(math.radians(lat)))
    return (bbox[0] - dlon, bbox[1] - dlat, bbox[2] + dlon, bbox[3] + dlat)


def grid_spec(bbox_m, res_m, epsg):
    """Freeze grid: bbox in metres snapped outward to the cell size (pixel-is-area, north-up)."""
    x0 = math.floor(bbox_m[0] / res_m) * res_m
    y1 = math.ceil(bbox_m[3] / res_m) * res_m
    x1 = math.ceil(bbox_m[2] / res_m) * res_m
    y0 = math.floor(bbox_m[1] / res_m) * res_m
    return {"crs": f"EPSG:{epsg}", "resolution_m": res_m, "transform": (x0, res_m, 0.0, y1, 0.0, -res_m),
            "width": int(round((x1 - x0) / res_m)), "height": int(round((y1 - y0) / res_m)), "nodata": -9999.0,
            "registration": "pixel_is_area"}
