"""Flask app: Mapbox GL front end + national XYZ tiles + AOI jobs. Run: python landslide_app.py  (port 5070)."""
from __future__ import annotations
import io, json, os, threading, time, traceback, uuid
from pathlib import Path
import numpy as np
import rasterio
from flask import Flask, Response, abort, jsonify, request, send_file
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from . import paths, pipeline, render
from ..errors import LandslideError

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "runs"
STATIC = Path(__file__).parent / "static"
app = Flask(__name__)
JOBS: dict = {}
RESULTS: dict = {}               # run_id -> {"out","grid"} (in memory; arrays.npz is the durable copy)
_run_lock = threading.Lock()     # one heavy job at a time: the server is shared


def _env_token():
    t = os.environ.get("MAPBOX_TOKEN")
    if t:
        return t
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("MAPBOX_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""


def national_products():
    d = ROOT / "datasets" / "national"
    return sorted(p for p in d.glob("stability_*.tif")) if d.exists() else []


# ---- national tile layers: name -> (path getter, band, ramp, scale)
def _layer(name):
    if name == "lsm":
        return paths.get("LSM_PROB"), 1, "lsm_prob", 1.0, True
    if name == "risk":
        return paths.get("RISK_INDEX"), 1, "risk_index", 1.0, False
    if name in ("frac", "fs", "slope"):
        prods = national_products()
        if not prods:
            return None
        band, ramp, sc = {"frac": (1, "frac_lt1", 0.01), "fs": (2, "min_fs_p50", 0.02), "slope": (3, "slope_deg", 1.0)}[name]
        return str(prods[-1]), band, ramp, sc, False
    return None


_vrt_cache: dict = {}
_vrt_lock = threading.Lock()


def _tile_bounds(z, x, y):
    n = 2.0 ** z
    R = 20037508.342789244
    w = -R + x * 2 * R / n; e = w + 2 * R / n
    nn = R - y * 2 * R / n; s = nn - 2 * R / n
    return w, s, e, nn


@app.get("/tiles/<name>/<int:z>/<int:x>/<int:y>.png")
def tile(name, z, x, y):
    spec = _layer(name)
    if spec is None:
        abort(404)
    path, band, ramp, scale, nodata_neg = spec
    w, s, e, n = _tile_bounds(z, x, y)
    try:
        with _vrt_lock:                                   # rasterio datasets are not thread-safe
            with rasterio.open(path) as src:
                nd = src.nodata
                with WarpedVRT(src, crs="EPSG:3857", transform=from_bounds(w, s, e, n, 256, 256), width=256, height=256,
                               resampling=Resampling.nearest if "stability" in path else Resampling.bilinear,
                               nodata=nd if nd is not None else np.nan) as v:
                    a = v.read(band).astype("float32")
    except Exception:
        a = np.full((256, 256), np.nan, "float32"); nd = None
    if nd is not None and np.isfinite(nd):
        a[a == nd] = np.nan
    if nodata_neg:
        a[a < 0] = np.nan
    a[a < -1e30] = np.nan
    a = a * scale
    return Response(render.to_png(render.colorize(a, ramp)), mimetype="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/layers")
def layers():
    out = [{"id": "lsm", "label": "National susceptibility (CNN/DNN ensemble, 90 m)", "ramp": "lsm_prob"},
           {"id": "risk", "label": "National risk index", "ramp": "risk_index"}]
    if national_products():
        p = national_products()[-1]
        with rasterio.open(p) as s:
            tags = s.tags()
        out += [{"id": "frac", "label": f"Physics: share of members FS<1 ({tags.get('rain_mm_h')} mm/h x {tags.get('hours')} h)", "ramp": "frac_lt1", "product": p.name},
                {"id": "fs", "label": "Physics: median minimum FS", "ramp": "min_fs_p50", "product": p.name},
                {"id": "slope", "label": "Slope (90 m)", "ramp": "slope_deg", "product": p.name}]
    return jsonify({"layers": out, "ramps": {k: {"stops": v[0], "label": v[1]} for k, v in render.RAMPS.items()}})


@app.get("/api/data-status")
def data_status():
    return jsonify(paths.check())


@app.get("/api/boundary")
def boundary():
    import geopandas as gpd
    g = gpd.read_file(paths.get("BOUNDARY_SHP"))
    geom = g.geometry.union_all().simplify(0.01)
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda p: p.area)
    return jsonify({"type": "Polygon", "coordinates": [list(map(list, geom.exterior.coords))]})


@app.get("/api/districts")
def districts():
    f = ROOT / "datasets" / "national" / "districts.geojson"
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="application/geo+json")


@app.get("/api/presets")
def presets():
    return jsonify({"textures": pipeline.TEXTURES, "strength": pipeline.STRENGTH_PRESETS, "max_aoi_km2": pipeline.MAX_AOI_KM2,
                    "max_cells": pipeline.MAX_CELLS})


def _job(jid, geom, params):
    j = JOBS[jid]
    with _run_lock:
        j["state"] = "running"
        try:
            r = pipeline.run_aoi(geom, params, progress=lambda s, f: j.update(stage=s, frac=f), run_root=str(RUNS))
            j.update(state="done", frac=1.0, run_id=r["run_id"], summary=r["summary"], warnings=r["manifest"]["warnings"],
                     layers=[k for k in r["out"] if k in render.RAMPS])
        except LandslideError as e:
            j.update(state=e.code, error=str(e), reasons=getattr(e, "reasons", getattr(e, "missing", [])))
        except Exception as e:
            traceback.print_exc()
            j.update(state="error", error=f"{type(e).__name__}: {e}")


@app.post("/api/run")
def run():
    body = request.get_json(force=True)
    geom = body.get("geometry")
    if not geom or geom.get("type") != "Polygon":
        return jsonify({"error": "geometry must be a GeoJSON Polygon"}), 400
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"state": "queued", "stage": "queued", "frac": 0.0, "t0": time.time()}
    threading.Thread(target=_job, args=(jid, geom, body.get("params", {})), daemon=True).start()
    return jsonify({"job": jid})


@app.get("/api/job/<jid>")
def job(jid):
    if jid not in JOBS:
        abort(404)
    return jsonify(JOBS[jid])


def _result(run_id):
    if run_id in RESULTS:
        return RESULTS[run_id]
    f = RUNS / run_id / "arrays.npz"
    m = RUNS / run_id / "manifest.json"
    if not f.exists() or not m.exists():
        abort(404)
    from affine import Affine
    z = np.load(f); man = json.loads(m.read_text()); g = man["grid"]; t = g["transform"]
    grid = {**g, "affine": Affine(t[1], 0, t[0], 0, t[5], t[3])}
    RESULTS[run_id] = {"out": {k: z[k] for k in z.files}, "grid": grid}
    return RESULTS[run_id]


@app.get("/api/run/<run_id>/overlay/<layer>")
def overlay(run_id, layer):
    if layer not in render.RAMPS:
        abort(404)
    r = _result(run_id)
    if layer not in r["out"]:
        abort(404)
    png, corners = render.overlay_png(r["out"][layer], r["grid"], layer)
    return Response(png, mimetype="image/png", headers={"X-Coordinates": json.dumps(corners), "Access-Control-Expose-Headers": "X-Coordinates"})


@app.get("/api/run/<run_id>/manifest")
def manifest(run_id):
    f = RUNS / run_id / "manifest.json"
    return send_file(f) if f.exists() else abort(404)


@app.get("/")
def index():
    return Response((STATIC / "app.html").read_text().replace("__MAPBOX_TOKEN__", _env_token()), mimetype="text/html")


@app.get("/legacy")
def legacy():
    return Response((STATIC / "index.html").read_text().replace("__MAPBOX_TOKEN__", _env_token()), mimetype="text/html")


# ---- access control and rate limiting. LANDLAB_TOKEN set -> every write (POST/DELETE) needs it (Authorization: Bearer <t>, X-Token, or ?token=).
# Reads stay open on the network (same as SAILAB). A per-IP limit applies to POST (LANDLAB_RATE per minute, default 40).
_hits: dict = {}


@app.before_request
def _guard():
    if request.method in ("POST", "DELETE", "PUT"):
        tok = os.environ.get("LANDLAB_TOKEN")
        if tok:
            got = (request.headers.get("Authorization", "").removeprefix("Bearer ") or request.headers.get("X-Token") or request.args.get("token") or "")
            if got != tok:
                return jsonify({"error": "this server requires a token for runs (LANDLAB_TOKEN)"}), 401
        lim = int(os.environ.get("LANDLAB_RATE", 40)); now = time.time(); ip = request.remote_addr
        q = [t for t in _hits.get(ip, []) if now - t < 60]; q.append(now); _hits[ip] = q
        if len(q) > lim:
            return jsonify({"error": f"rate limit: {lim} requests per minute"}), 429


from . import routes  # noqa: E402,F401  (registers the SAILAB-style routes on `app`)


def main():
    port = int(os.environ.get("PORT", 5070))
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=port, threaded=True, debug=False)
