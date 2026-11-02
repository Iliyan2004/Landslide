"""SAILAB-style routes for the landslide platform: area, rainfall, tiers 1-4, runs, monitoring, compare, reports."""
from __future__ import annotations
import hashlib, io, json, os, threading, time, traceback, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from flask import Response, abort, jsonify, request, send_file
from .server import app, ROOT, RUNS, _env_token, JOBS, _run_lock
from . import agents as AG, pipeline, rainfall as RF, runs as RUNS_MOD, render, layers as LY, paths
from ..errors import LandslideError
from ..data.preprocessing import aoi as AOI

STATE = ROOT / "datasets" / "state"
STATE.mkdir(parents=True, exist_ok=True)
_dist_cache = {}
REGIONS = {"gilgit_baltistan": (72.3, 34.4, 77.9, 37.1), "khyber_pakhtunkhwa": (69.2, 31.0, 74.1, 36.9), "punjab": (69.3, 27.7, 75.4, 34.0),
           "sindh": (66.6, 23.6, 71.2, 28.5), "balochistan": (60.8, 24.5, 70.3, 32.2), "azad_kashmir": (73.0, 32.8, 75.2, 36.0)}


def _geom():
    g = (request.get_json(force=True, silent=True) or {}).get("geometry")
    if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
        abort(400, "geometry must be a GeoJSON Polygon")
    if g["type"] == "MultiPolygon":
        g = {"type": "Polygon", "coordinates": max(g["coordinates"], key=lambda p: len(p[0]))}
    return g


def _districts():
    if "d" not in _dist_cache:
        import geopandas as gpd
        f = ROOT / "datasets" / "national" / "districts.geojson"
        _dist_cache["d"] = gpd.read_file(f) if f.exists() else None
    return _dist_cache["d"]


@app.errorhandler(400)
def _bad(e):
    return jsonify({"error": getattr(e, "description", "bad request")}), 400


# ---------------------------------------------------------------- area
@app.post("/area/polygon")
def area_polygon():
    g = _geom()
    try:
        bbox, area, warn = AOI.validate_geojson(g, max_area_km2=pipeline.MAX_AOI_KM2)
    except LandslideError as e:
        return jsonify({"error": str(e), "reasons": getattr(e, "reasons", [])}), 422
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    info = {"area_km2": area, "bbox": bbox, "centroid": [cx, cy], "aoi_id": AOI.aoi_sha256(g)[:16], "warnings": warn}
    d = _districts()
    if d is not None:
        from shapely.geometry import Point
        hit = d[d.contains(Point(cx, cy))]
        if len(hit):
            r = hit.iloc[0]; info["district"] = {"name": r["name"], "province": r["province"]}
    cells30 = area * 1e6 / 900
    info["physics_possible"] = bool(area <= pipeline.MAX_CELLS * pipeline.MAX_PHYSICS_RES_M ** 2 / 1e6)
    info["cells_at_30m"] = int(cells30)
    return jsonify(info)


@app.post("/area/upload")
def area_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    import geopandas as gpd, tempfile
    raw = f.read()
    try:
        if f.filename.lower().endswith(".zip"):
            td = tempfile.mkdtemp(); zipfile.ZipFile(io.BytesIO(raw)).extractall(td)
            shp = next(Path(td).rglob("*.shp"))
            g = gpd.read_file(shp)
        else:
            g = gpd.read_file(io.BytesIO(raw))
        g = g.to_crs(4326)
        geom = g.geometry.union_all()
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda p: p.area)
        return jsonify({"geometry": {"type": "Polygon", "coordinates": [list(map(list, geom.exterior.coords))]}})
    except Exception as e:
        return jsonify({"error": f"could not read the area file: {e}"}), 400


@app.get("/districts/search")
def districts_search():
    d = _districts()
    if d is None:
        return jsonify({"results": [], "error": "run scripts/build_districts.py first"}), 400
    q = request.args.get("q", "").lower()
    metric = request.args.get("metric", "lsm_area_frac_gt_0_7")
    x = d[d["name"].str.lower().str.contains(q)] if q else d
    if metric in x.columns:
        x = x.sort_values(metric, ascending=False)
    out = []
    for i, r in x.head(int(request.args.get("n", 15))).iterrows():
        out.append({"idx": int(i), "name": r["name"], "province": r["province"], "division": r["division"], "population": r.get("population"),
                    "area_km2": round(float(r.geometry.area * 111.32 * 111.32 * np.cos(np.radians(r.geometry.centroid.y))), 0),
                    "metric": r.get(metric), "metric_name": metric, "lsm_coverage": r.get("lsm_coverage")})
    return jsonify({"results": out})


@app.get("/districts/<int:i>")
def district_geom(i):
    d = _districts()
    if d is None or i not in d.index:
        abort(404)
    from shapely.geometry import mapping
    g = d.loc[i].geometry
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    return jsonify({"geometry": mapping(g), "name": d.loc[i]["name"]})


@app.get("/basins/search")
def basins_search():
    f = Path(paths.SHARE) / "Tasks/Reselli_AI/flood/global_data/hydrosheds_basins_pk_index.json"
    if not f.exists():
        return jsonify({"results": [], "error": "HydroSHEDS basin index not on this server"}), 400
    idx = json.loads(f.read_text())
    region = request.args.get("region")
    if region in REGIONS:
        x0, y0, x1, y1 = REGIONS[region]
        idx = [b for b in idx if x0 <= b["centroid_lon"] <= x1 and y0 <= b["centroid_lat"] <= y1]
    idx.sort(key=lambda b: -b["area_km2"])
    return jsonify({"results": idx[:int(request.args.get("n", 15))], "regions_available": sorted(REGIONS)})


@app.get("/basins/<int:hid>")
def basin_geom(hid):
    p = Path(paths.SHARE) / f"Tasks/Reselli_AI/flood/global_data/hydrosheds_basins_pk/hybas_pak_lev08_{hid}.geojson"
    if not p.exists():
        abort(404)
    j = json.loads(p.read_text())
    g = j["features"][0]["geometry"] if j.get("type") == "FeatureCollection" else j.get("geometry", j)
    if g["type"] == "MultiPolygon":
        g = {"type": "Polygon", "coordinates": max(g["coordinates"], key=lambda p: len(p[0]))}
    return jsonify({"geometry": g})


# ---------------------------------------------------------------- rainfall
def _centroid(g):
    b, _, _ = AOI.validate_geojson(g, max_area_km2=pipeline.MAX_AOI_KM2)
    return (b[1] + b[3]) / 2, (b[0] + b[2]) / 2


@app.post("/area/context")
def area_context():
    g = _geom(); lat, lon = _centroid(g)
    out = {"lat": lat, "lon": lon}
    try:
        om = RF.open_meteo(lat, lon, 3, 3)
        out["open_meteo"] = {k: om[k] for k in ("past_mm", "forecast_mm", "peak_mm_h", "source")}
        out["open_meteo"]["times_iso"] = om["times_iso"]; out["open_meteo"]["rate_mm_h"] = om["rate_mm_h"]; out["open_meteo"]["now_hour_index"] = om["now_hour_index"]
        out["id_check_forecast"] = RF.id_check(om["rate_mm_h"][om["now_hour_index"]:] or [0.0])
        out["id_check_recent"] = RF.id_check(om["rate_mm_h"][:om["now_hour_index"]] or [0.0])
        from ..models.infiltration.api_index import antecedent_precip_index
        api = antecedent_precip_index(np.array(om["rate_mm_h"][:om["now_hour_index"]]), k=0.98)
        out["antecedent_precip_index_mm"] = float(np.asarray(api)[-1])
    except Exception as e:
        out["open_meteo_error"] = str(e)[:200]
    try:
        out["era5_wettest_72h"] = RF.era5_wettest_event(lat, lon, (2000, 2025))
    except Exception as e:
        out["era5_error"] = str(e)[:200]
    return jsonify(out)


@app.post("/area/rainfall")
def area_rainfall():
    body = request.get_json(force=True)
    g = _geom(); lat, lon = _centroid(g)
    src = body.get("source", "design")
    try:
        if src == "design":
            fn = RF.triangular if body.get("shape", "triangular") == "triangular" else RF.constant
            t, r = fn(float(body.get("peak_mm_h", 40)), float(body.get("duration_h", 6)))
            ser = RF.series_payload(t, r, f"design storm ({body.get('shape', 'triangular')}, peak {body.get('peak_mm_h', 40)} mm/h, {body.get('duration_h', 6)} h)")
        elif src == "forecast":
            om = RF.open_meteo(lat, lon, 0, int(body.get("days", 3)))
            ser = om
        elif src == "recent":
            om = RF.open_meteo(lat, lon, int(body.get("days", 3)), 1)
            n = om["now_hour_index"]
            ser = RF.series_payload(om["times_h"][:n], om["rate_mm_h"][:n], "Open-Meteo recent observed", om["start_iso"])
        elif src == "era5":
            ser = RF.era5_event(lat, lon, body["start"], body["end"])
        elif src == "era5_wettest":
            ev = RF.era5_wettest_event(lat, lon, (int(body.get("y0", 2000)), int(body.get("y1", 2025))), int(body.get("window_h", 72)))
            ser = RF.era5_event(lat, lon, ev["start"], ev["end"]); ser["event"] = ev
        elif src == "imerg":
            ser = RF.imerg_event(lat, lon, body["start"], body["end"])
        elif src == "chirps":
            ser = RF.chirps_daily(lat, lon, body["start"], body["end"])
        else:
            return jsonify({"error": f"unknown source {src}"}), 400
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400
    ser.pop("times_iso", None)
    ser["id_check"] = RF.id_check(ser["rate_mm_h"])
    if src in ("era5", "era5_wettest", "imerg", "chirps") and body.get("antecedent", True) and ser.get("start_iso"):
        try:                                                       # 30 days of ERA5-Land before the storm -> antecedent wetness in the physics run
            ser["antecedent_daily_mm"] = [round(x, 2) for x in RF.era5_antecedent(lat, lon, ser["start_iso"].rstrip("Z"), 30)]
        except Exception as e:
            ser["antecedent_note"] = f"no antecedent rainfall: {e}"[:160]
    return jsonify(ser)


@app.post("/area/rainfall-csv")
def rainfall_csv():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    try:
        ser = RF.parse_csv(f.read().decode("utf-8-sig"), request.form.get("unit", "mm_per_hour"))
        ser["source"] = f"uploaded CSV ({f.filename})"
        ser["id_check"] = RF.id_check(ser["rate_mm_h"], dt_h=max(0.01, float(np.median(np.diff([0] + ser["times_h"])))))
        return jsonify(ser)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------- tier 1 / 2
@app.post("/area/screening")
def area_screening():
    g = _geom(); body = request.get_json(force=True)
    try:
        r = pipeline.run_aoi(g, body.get("params", {}), run_root=str(RUNS))
    except LandslideError as e:
        return jsonify({"error": str(e), "code": e.code, "reasons": getattr(e, "reasons", getattr(e, "missing", []))}), 422
    return jsonify({"run_id": r["run_id"], "summary": r["summary"], "warnings": r["manifest"]["warnings"], "layers": [k for k in r["out"] if k in render.RAMPS]})


@app.post("/area/instant-library")
def instant_library():
    g = _geom(); body = request.get_json(force=True)
    try:
        return jsonify(RUNS_MOD.instant_library(g, body.get("params", {})))
    except LandslideError as e:
        return jsonify({"error": str(e)}), 422


# ---------------------------------------------------------------- tiers 3/4 physics run
class Cancelled(Exception):
    pass


def _phys_job(jid, geom, params):
    j = JOBS[jid]
    with _run_lock:
        j.update(state="running", stage="starting")

        def prog(stage, frac):
            if j.get("cancel"):
                raise Cancelled()
            j.update(stage=stage, frac=frac)
        try:
            r = AG.run_with_recovery(lambda p: RUNS_MOD.execute(geom, p, str(RUNS), _env_token(), prog), params, note=lambda m: j.update(stage=m))
            j.update(state="done", frac=1.0, result=r, run_id=r["run_id"])
            _history_add(r, geom)
        except Cancelled:
            j.update(state="cancelled")
        except LandslideError as e:
            j.update(state=e.code, error=str(e), reasons=getattr(e, "reasons", getattr(e, "missing", [])))
        except Exception as e:
            traceback.print_exc()
            j.update(state="error", error=f"{type(e).__name__}: {e}")


@app.post("/run")
def run_physics():
    body = request.get_json(force=True)
    g = _geom(); params = body.get("params", {})
    mode = params.get("mode", "rain")
    if mode in ("rain", "both") and not params.get("rain"):
        return jsonify({"error": "choose a rainfall series first (Tier 3 > Storm)"}), 400
    if mode in ("quake", "both") and not params.get("quake"):
        return jsonify({"error": "set an earthquake scenario (magnitude and epicentre) first"}), 400
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"state": "queued", "stage": "queued", "frac": 0.0, "t0": time.time()}
    threading.Thread(target=_phys_job, args=(jid, g, params), daemon=True).start()
    return jsonify({"job": jid})


@app.get("/runs/<jid>/progress.json")
def run_progress(jid):
    if jid not in JOBS:
        abort(404)
    j = dict(JOBS[jid]); j["elapsed_s"] = round(time.time() - j.get("t0", time.time()), 1)
    return jsonify(j)


@app.post("/runs/<jid>/cancel")
def run_cancel(jid):
    if jid in JOBS:
        JOBS[jid]["cancel"] = True
    return jsonify({"ok": True})


@app.get("/runs/<rid>/mapbox3d")
def run_mapbox3d(rid):
    f = RUNS / rid / "mapbox_3d.html"
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="text/html")


@app.get("/runs/<rid>/summary.json")
def run_summary(rid):
    f = RUNS / rid / "summary.json"
    return send_file(f, mimetype="application/json") if f.exists() else abort(404)


@app.get("/runs/<rid>/overlay/<layer>.png")
def run_overlay(rid, layer):
    try:
        png, corners = RUNS_MOD.overlay(rid, layer, str(RUNS))
    except (KeyError, FileNotFoundError):
        abort(404)
    return Response(png, mimetype="image/png", headers={"X-Coordinates": json.dumps(corners), "Access-Control-Expose-Headers": "X-Coordinates"})


def _history_add(r, geom):
    f = STATE / "history.json"
    h = json.loads(f.read_text()) if f.exists() else []
    s = r["summary"]
    h = [x for x in h if x["run_id"] != r["run_id"]]
    h.insert(0, {"run_id": r["run_id"], "t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": s.get("mode"), "outcome": r.get("outcome"),
                 "area_km2": s.get("area_km2"), "released_m3": (s.get("flow") or {}).get("released_volume_m3"),
                 "impacted_km2": (s.get("flow") or {}).get("impacted_area_km2"), "loss_pkr": (s.get("exposure") or {}).get("direct_loss_pkr"),
                 "centroid": [float(np.mean([p[0] for p in geom["coordinates"][0]])), float(np.mean([p[1] for p in geom["coordinates"][0]]))]})
    f.write_text(json.dumps(h[:200]))


@app.get("/runs")
def runs_list():
    f = STATE / "history.json"
    return jsonify(json.loads(f.read_text()) if f.exists() else [])


# ---------------------------------------------------------------- earthquake helpers
@app.get("/faults")
def faults():
    import geopandas as gpd
    b = tuple(float(x) for x in request.args.get("bbox", "60,23,78,38").split(","))
    g = gpd.read_file(paths.get("FAULTS_SHP"), bbox=b).to_crs(4326)
    g["geometry"] = g.geometry.simplify(0.005)
    return Response(g[["geometry"]].to_json(), mimetype="application/geo+json")


@app.get("/quake/preview")
def quake_preview():
    mag, lon, lat = float(request.args["mag"]), float(request.args["lon"]), float(request.args["lat"])
    from ..engine import trigger as TR
    d = np.array([0, 5, 10, 20, 40, 80, 150])
    return jsonify({"rupture_km": TR.rupture_length_km(mag), "pga_g": [round(float(x), 4) for x in TR.bssa14_pga_g(mag, d, 760.0)], "pga_g_soft_soil_vs30_300": [round(float(x), 4) for x in TR.bssa14_pga_g(mag, d, 300.0)],
                    "pga_g_jb81": [round(float(x), 4) for x in TR.jb81_pga_g(mag, d)], "dist_km": d.tolist(),
                    "model": "Boore et al. (2014) NGA-West2 median PGA on rock (Vs30 760) and on soft soil (300); Joyner & Boore (1981) shown for comparison"})


# ---------------------------------------------------------------- compare runs & reports
def _load_arr(rid):
    f = RUNS / rid / "arrays.npz"
    return np.load(f) if f.exists() else None


@app.post("/compare-runs")
def compare_runs():
    b = request.get_json(force=True); a_id, b_id = b["a"], b["b"]
    A, B = _load_arr(a_id), _load_arr(b_id)
    if A is None or B is None or A["hmax"].shape != B["hmax"].shape:
        return jsonify({"error": "both runs need physics results on the same area and grid (same polygon and resolution)"}), 400
    ha, hb = np.nan_to_num(A["hmax"]), np.nan_to_num(B["hmax"])
    cell = float(json.loads((RUNS / a_id / "manifest.json").read_text())["grid"]["resolution_m"]) ** 2 / 1e6
    wa, wb = ha > 0.3, hb > 0.3
    sa, sb_ = json.loads((RUNS / a_id / "summary.json").read_text()), json.loads((RUNS / b_id / "summary.json").read_text())
    return jsonify({"a": a_id, "b": b_id, "area_a_km2": float(wa.sum() * cell), "area_b_km2": float(wb.sum() * cell),
                    "only_a_km2": float((wa & ~wb).sum() * cell), "only_b_km2": float((wb & ~wa).sum() * cell), "both_km2": float((wa & wb).sum() * cell),
                    "max_depth_a": float(ha.max()), "max_depth_b": float(hb.max()), "mean_depth_change_m": float((hb - ha)[wa | wb].mean()) if (wa | wb).any() else 0.0,
                    "loss_a_pkr": (sa["summary"].get("exposure") or {}).get("direct_loss_pkr"), "loss_b_pkr": (sb_["summary"].get("exposure") or {}).get("direct_loss_pkr")})


def _report_html(rid):
    """SAILAB-format run report (app/report.py)."""
    from . import report as REP
    return REP.build_html(rid, RUNS)


@app.get("/runs/<rid>/report.html")
def report_html(rid):
    if not (RUNS / rid / "summary.json").exists():
        abort(404)
    return Response(_report_html(rid), mimetype="text/html")


@app.get("/runs/<rid>/report.pdf")
def report_pdf(rid):
    if not (RUNS / rid / "summary.json").exists():
        abort(404)
    import weasyprint
    return Response(weasyprint.HTML(string=_report_html(rid)).write_pdf(), mimetype="application/pdf", headers={"Content-Disposition": f"inline; filename={rid}.pdf"})


# ---------------------------------------------------------------- live monitoring (rain watch -> auto physics run)
WATCH_F = STATE / "watches.json"
_wlock = threading.Lock()


def _watches():
    return json.loads(WATCH_F.read_text()) if WATCH_F.exists() else {}


def _save_watches(w):
    WATCH_F.write_text(json.dumps(w, indent=1))


def _check_watch(wid):
    with _wlock:
        w = _watches()[wid]
    lat, lon = w["lat"], w["lon"]
    res = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        om = RF.open_meteo(lat, lon, 1, 3)
        raw = om["rate_mm_h"][om["now_hour_index"]:]
        if not om.get("stale_cache"):
            AG.record_forecast(lat, lon, om["times_iso"], raw, om["now_hour_index"])               # forecast-audit agent: scored later against what was observed
        fut = [x * AG.correction(i // 24) for i, x in enumerate(raw)]                               # bias correction per lead day (1.0 until audited)
        res.update(forecast_peak_raw_mm_h=float(max(raw) if raw else 0), bias_corrected=any(abs(AG.correction(d) - 1) > 1e-6 for d in range(3)),
                   stale_cache=bool(om.get("stale_cache")), data_age_h=om.get("data_age_h"))
        peak = float(max(fut) if fut else 0)
        idc = RF.id_check(fut or [0.0])
        res.update(forecast_peak_mm_h=peak, forecast_total_mm=float(sum(fut)), id_exceeded=idc["exceeded"], status="experimental_unvalidated")
        crossed = peak >= w["threshold_mm_h"]
        res["crossed"] = crossed
        if crossed and not w.get("last_crossed"):
            ser = RF.series_payload(om["times_h"][om["now_hour_index"]:], fut, "Open-Meteo forecast (monitor)", None)
            ser["times_h"] = [round(t - om["times_h"][om["now_hour_index"]] + 1, 3) for t in ser["times_h"]]
            jid = uuid.uuid4().hex[:12]
            JOBS[jid] = {"state": "queued", "stage": "queued", "frac": 0.0, "t0": time.time()}
            threading.Thread(target=_phys_job, args=(jid, w["geometry"], {"mode": "rain", "rain": ser, "strength_quantile": w.get("strength_quantile", 0.3)}), daemon=True).start()
            res["auto_run_job"] = jid
            if w.get("webhook"):
                import requests
                try:
                    requests.post(w["webhook"], json={"text": f"Landslide watch '{w['name']}': forecast {peak:.1f} mm/h crosses {w['threshold_mm_h']} mm/h. Physics run started: job {jid}."}, timeout=10)
                except Exception as e:
                    res["webhook_error"] = str(e)[:100]
        res_crossed = crossed
    except Exception as e:
        res["error"] = str(e)[:200]; res_crossed = w.get("last_crossed", False)
    with _wlock:
        ws = _watches(); ws[wid]["last"] = res; ws[wid]["last_crossed"] = res_crossed; _save_watches(ws)
    return res


def _watch_loop():
    while True:
        time.sleep(60)
        try:
            for wid, w in list(_watches().items()):
                last = w.get("last", {}).get("t")
                due = (not last) or (time.time() - datetime.fromisoformat(last).timestamp() >= w["every_h"] * 3600)
                if due:
                    _check_watch(wid)
        except Exception:
            traceback.print_exc()


threading.Thread(target=_watch_loop, daemon=True).start()


@app.get("/api/agents/status")
def agents_status():
    return jsonify(AG.status())


@app.post("/api/agents/audit")
def agents_audit():
    return jsonify(AG.audit())


AG.start()


@app.post("/monitor/watch")
def monitor_watch():
    b = request.get_json(force=True); g = _geom(); lat, lon = _centroid(g)
    wid = uuid.uuid4().hex[:8]
    with _wlock:
        ws = _watches()
        ws[wid] = {"name": b.get("name") or f"Area {wid}", "geometry": g, "lat": lat, "lon": lon, "threshold_mm_h": float(b.get("threshold_mm_h", 10)),
                   "every_h": float(b.get("every_h", 3)), "webhook": b.get("webhook") or None, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _save_watches(ws)
    return jsonify({"id": wid, "first_check": _check_watch(wid)})


@app.get("/monitor/list")
def monitor_list():
    return jsonify([{**{k: v for k, v in w.items() if k != "geometry"}, "id": i} for i, w in _watches().items()])


@app.delete("/monitor/<wid>")
def monitor_delete(wid):
    with _wlock:
        ws = _watches(); ws.pop(wid, None); _save_watches(ws)
    return jsonify({"ok": True})


@app.post("/monitor/<wid>/check-now")
def monitor_check(wid):
    if wid not in _watches():
        abort(404)
    return jsonify(_check_watch(wid))


@app.get("/api/hw")
def hw():
    try:
        import torch
        g = f"GPU {torch.cuda.get_device_name(0)} (first)" if torch.cuda.is_available() else "CPU only"
    except Exception:
        g = "CPU only"
    return jsonify({"text": g + " · RAM · CPU fallback"})


# ---------------------------------------------------------------- video export (same approach as SAILAB's /export-video)
@app.post("/export-video")
def export_video():
    """The 3D viewer records its canvas client-side (WebM via MediaRecorder); transcode to MP4 with the bundled static ffmpeg."""
    import subprocess, tempfile
    f = request.files.get("video")
    if not f:
        return jsonify({"error": "no video uploaded"}), 400
    td = tempfile.mkdtemp()
    src, dst = os.path.join(td, "in.webm"), os.path.join(td, "out.mp4")
    f.save(src)
    try:
        import imageio_ffmpeg
        p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", src, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], capture_output=True, text=True, timeout=180)
        if p.returncode != 0 or not os.path.exists(dst):
            return jsonify({"error": f"ffmpeg failed: {p.stderr[-800:]}"}), 500
        data = open(dst, "rb").read()
        return Response(data, mimetype="video/mp4", headers={"Content-Disposition": "attachment; filename=landslide_animation.mp4"})
    finally:
        for x in (src, dst):
            try:
                os.remove(x)
            except OSError:
                pass
        try:
            os.rmdir(td)
        except OSError:
            pass


from . import routes_extra  # noqa: E402,F401  (design storms, mitigation, AAL, hotspots, dams, observed, batch)
