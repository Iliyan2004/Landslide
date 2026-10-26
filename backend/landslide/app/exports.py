"""GIS exports of a finished run: GeoTIFF rasters (analysis CRS), GeoJSON (failure area, damaged buildings, blocked roads), CSV of buildings; zipped."""
from __future__ import annotations
import csv, gzip, io, json, zipfile
from pathlib import Path
import numpy as np
import rasterio
from affine import Affine
from rasterio.features import shapes
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_t, unary_union

RASTERS = ("dem", "slope", "hmax", "vmax", "deposit", "scour", "t_fail_h", "fs_min", "pga_g", "reach_frac", "emax_kj", "hmax_m", "z")


def _tif(arr, g, t):
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32", crs=g["crs"], transform=t, nodata=-9999.0, compress="deflate")
    mem = rasterio.MemoryFile()
    with mem.open(**prof) as d:
        d.write(np.where(np.isfinite(arr), arr, -9999.0).astype("float32"), 1)
    return mem.read()


def build_zip(rdir):
    rdir = Path(rdir); man = json.loads((rdir / "manifest.json").read_text()); g = man["grid"]; tt = g["transform"]; t = Affine(tt[1], 0, tt[0], 0, tt[5], tt[3])
    z = np.load(rdir / "arrays.npz"); buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for k in RASTERS:
            if k in z.files:
                zf.writestr(f"rasters/{k}.tif", _tif(z[k], g, t))
        zf.writestr("manifest.json", json.dumps(man, indent=1))
        zf.writestr("README.txt", "LANDLAB export. Rasters are in the analysis CRS %s (cell %.0f m), nodata -9999. Screening-grade; see manifest.json for parameters and warnings.\n" % (g["crs"], g["resolution_m"]))
        tr = Transformer.from_crs(g["crs"], 4326, always_xy=True)
        # failure / impact extent polygons
        for key, thr, nm in (("hmax", 0.3, "debris_extent"), ("reach_frac", 0.01, "rock_reach")):
            if key in z.files:
                m = (np.nan_to_num(z[key]) >= thr).astype("uint8")
                polys = [shape(s) for s, v in shapes(m, mask=m.astype(bool), transform=t) if v == 1]
                if polys:
                    u = shp_t(tr.transform, unary_union(polys).simplify(g["resolution_m"] * 0.4))
                    zf.writestr(f"vector/{nm}.geojson", json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"threshold": thr}, "geometry": mapping(u)}]}))
        if "t_fail_h" in z.files:
            m = np.isfinite(z["t_fail_h"]).astype("uint8")
            polys = [shape(s) for s, v in shapes(m, mask=m.astype(bool), transform=t) if v == 1]
            if polys:
                u = shp_t(tr.transform, unary_union(polys).simplify(g["resolution_m"] * 0.4))
                zf.writestr("vector/failure_zones.geojson", json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(u)}]}))
        for fn, kind in (("impacts.json.gz", "debris"), ("impacts_rock.json.gz", "rock")):
            p = rdir / fn
            if not p.exists():
                continue
            d = json.load(gzip.open(p, "rt")); feats, rows = [], []
            for b in d["buildings"]:
                coords = b.get("c")
                dmg, ds, loss = b.get("dmg"), b.get("ds"), b.get("loss")
                cls = b.get("cls"); em = b.get("emax")
                props = {"area_m2": b.get("a"), "damage_ratio": dmg, "damage_state": ds, "loss_pkr": loss, "rock_energy_class": cls, "rock_emax_kj": em}
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [coords]}})
                rows.append({**props, "lon": b.get("cx"), "lat": b.get("cy")})
            zf.writestr(f"vector/buildings_{kind}.geojson", json.dumps({"type": "FeatureCollection", "features": feats}))
            sio = io.StringIO(); w = csv.DictWriter(sio, fieldnames=list(rows[0].keys()) if rows else ["lon", "lat"]); w.writeheader(); [w.writerow(r) for r in rows]
            zf.writestr(f"tables/buildings_{kind}.csv", sio.getvalue())
            rf = [{"type": "Feature", "properties": {"blocked": r.get("blocked"), "rock_class": r.get("cls")}, "geometry": {"type": "LineString", "coordinates": r["c"]}} for r in d["roads"] if r.get("blocked") or (r.get("cls") is not None and r.get("cls") >= 0)]
            zf.writestr(f"vector/roads_affected_{kind}.geojson", json.dumps({"type": "FeatureCollection", "features": rf}))
        s = (rdir / "summary.json").read_text()
        zf.writestr("summary.json", s)
    return buf.getvalue()
