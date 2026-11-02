"""Additional landslide routes: design storms and climate, mitigation (nature-based and grey), average annual loss, hotspots, dam screening,
observed-extent scoring, batch report. Heavy ones are background jobs polled through /runs/<job>/progress.json (same as physics runs).
Nothing here touches flooding."""
from __future__ import annotations
import io, json, threading, time, traceback, uuid
from pathlib import Path
import numpy as np
from flask import Response, abort, jsonify, request
from .server import app, ROOT, RUNS, _env_token, JOBS, _run_lock
from .routes import _geom, _centroid, Cancelled, _history_add
from . import design_storm as DS, runs as RUNS_MOD, rainfall as RF, hotspots as HS, observed as OB
from ..engine import aal as AAL, dam as DAM, interventions as IV, optimize as OPT, run as ENG
from ..errors import LandslideError


def _job(fn, *a, **kw):
    """Run fn(progress, *a) in a thread under the one-heavy-job lock; the result dict goes to JOBS[id]['result']."""
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"state": "queued", "stage": "queued", "frac": 0.0, "t0": time.time()}
    def go():
        j = JOBS[jid]
        with _run_lock:
            j.update(state="running", stage="starting")
            def prog(s, f):
                if j.get("cancel"):
                    raise Cancelled()
                j.update(stage=s, frac=f)
            try:
                j.update(state="done", frac=1.0, result=fn(prog, *a, **kw))
            except Cancelled:
                j.update(state="cancelled")
            except LandslideError as e:
                j.update(state=e.code, error=str(e), reasons=getattr(e, "reasons", getattr(e, "missing", [])))
            except Exception as e:
                traceback.print_exc(); j.update(state="error", error=f"{type(e).__name__}: {e}")
    threading.Thread(target=go, daemon=True).start()
    return jid


def _summ(d):
    s = d["summary"]; ex = s.get("exposure") or {}; fl = s.get("flow") or {}; tr = s.get("trigger") or {}
    return {"run_id": d["run_id"], "outcome": d.get("outcome"), "loss_pkr": ex.get("direct_loss_pkr") or 0.0, "road_blocked_km": ex.get("road_blocked_km") or 0.0,
            "impacted_km2": fl.get("impacted_area_km2") or 0.0, "failing_km2": tr.get("failing_area_km2") or 0.0, "released_m3": fl.get("released_volume_m3") or 0.0,
            "buildings_ds3": ex.get("buildings_ds_ge3") or 0}


# ------------------------------------------------------------------ design storms and climate
@app.post("/area/idf")
def area_idf():
    g = _geom(); lat, lon = _centroid(g)
    if not DS.available():
        return jsonify({"error": "the rainfall indices cube is not on this server"}), 400
    try:
        return jsonify(DS.return_period_table(lat, lon, n_boot=int((request.get_json(force=True) or {}).get("n_boot", 100))))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/area/design-storm")
def area_design_storm():
    b = request.get_json(force=True); g = _geom(); lat, lon = _centroid(g)
    T = int(b.get("T", 50)); D = float(b.get("duration_h", 6)); cf = float(b.get("climate_factor", 1.0))
    try:
        tab = DS.return_period_table(lat, lon, n_boot=60)
        if T not in tab["periods"]:
            return jsonify({"error": f"return period must be one of {tab['periods']}"}), 400
        h = DS.design_hyetograph(tab, T, D, 15, lat, lon, b.get("short", "imerg"), cf)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    h["id_check"] = RF.id_check(h["rate_mm_h"], dt_h=0.25)
    k = tab["periods"].index(T)
    h["idf_row"] = {"durations_h": tab["durations_h"], "depth_mm": tab["depth_mm"][k], "p05": tab["depth_p05"][k], "p95": tab["depth_p95"][k]}
    return jsonify(h)


@app.post("/area/climate-factor")
def area_climate_factor():
    b = request.get_json(force=True); g = _geom(); lat, lon = _centroid(g)
    jid = _job(lambda prog: DS.climate_factor(lat, lon, b.get("scenario", "ssp585"), tuple(b.get("period", (2036, 2065))), int(b.get("T", 50)), cap=int(b.get("models", 8))))
    return jsonify({"job": jid, "warning": "reads many 30 MB yearly CMIP6 files: takes minutes"})


# ------------------------------------------------------------------ mitigation: nature-based and grey
def _run_with(geom, params, prog, tag):
    prog(tag, 0.0)
    return RUNS_MOD.execute(geom, params, str(RUNS), _env_token(), lambda s, f: None)


@app.post("/area/mitigation")
def area_mitigation():
    """Baseline (unmitigated) run and the mitigated run, with the change in failing area, impacted area and loss."""
    b = request.get_json(force=True); g = _geom(); p = dict(b.get("params", {})); iv = b.get("interventions") or {}
    if not (iv.get("nbs") or iv.get("protection")):
        return jsonify({"error": "choose at least one nature-based lever or draw a barrier"}), 400
    def fn(prog):
        base_p = {k: v for k, v in p.items() if k != "interventions"}
        prog("baseline run", 0.05); base = RUNS_MOD.execute(g, base_p, str(RUNS), _env_token(), lambda s, f: prog("baseline: " + s, 0.05 + 0.4 * f))
        prog("mitigated run", 0.5); mit = RUNS_MOD.execute(g, {**p, "interventions": iv}, str(RUNS), _env_token(), lambda s, f: prog("mitigated: " + s, 0.5 + 0.45 * f))
        _history_add(base, g); _history_add(mit, g)
        a, c = _summ(base), _summ(mit)
        d = {k: a[k] - c[k] for k in ("loss_pkr", "impacted_km2", "failing_km2", "released_m3", "road_blocked_km", "buildings_ds3")}
        return {"baseline": a, "mitigated": c, "reduction": d, "interventions": iv,
                "note": "benefit is the change against the unmitigated run under the same storm and strength scenario; effect sizes are user scenario inputs"}
    return jsonify({"job": _job(fn)})


@app.post("/area/nbs-recommend")
def area_nbs_recommend():
    """Rank the 7 combinations of planting, regrading and drainage by the failing area they remove (stability-only, no flow)."""
    b = request.get_json(force=True); g = _geom(); p = b.get("params", {})
    if not p.get("rain"):
        return jsonify({"error": "load a rainfall series first"}), 400
    def fn(prog):
        prog("terrain", 0.05); ctx = ENG.stability_context(g, p)
        n = [0]
        def ev(spec):
            n[0] += 1; prog(f"evaluating combination {n[0]}/8", 0.1 + 0.85 * n[0] / 8); return ENG.failing_area(ctx, spec)
        return IV.rank_nbs(ev, defaults=b.get("effects"))
    return jsonify({"job": _job(fn)})


@app.post("/protect/optimize")
def protect_optimize():
    b = request.get_json(force=True); g = _geom(); p = dict(b.get("params", {}))
    nb, me = int(b.get("n_barriers", 2)), int(b.get("max_evals", 30))
    if me > 120:
        return jsonify({"error": "max_evals is limited to 120 (each is a full simulation)"}), 400
    def fn(prog):
        base_p = {k: v for k, v in p.items() if k != "interventions"}
        prog("baseline run", 0.02)
        base = RUNS_MOD.execute(g, base_p, str(RUNS), _env_token(), lambda s, f: None)
        if base.get("outcome") != "failure_and_runout":
            raise LandslideError("the baseline run has no runout to protect against")
        z = np.load(RUNS / base["run_id"] / "arrays.npz"); man = json.loads((RUNS / base["run_id"] / "manifest.json").read_text())
        gr = man["grid"]; t = gr["transform"]
        from affine import Affine
        aff = Affine(t[1], 0, t[0], 0, t[5], t[3]); epsg = int(gr["crs"].split(":")[1]); dx = gr["resolution_m"]
        fail_rc = list(zip(*np.where(np.isfinite(z["t_fail_h"]))))
        path = OPT.flow_corridor(z["dem"], np.nan_to_num(z["hmax"]), fail_rc, dx)
        def evaluate(bars):
            r = RUNS_MOD.execute(g, {**base_p, "interventions": {"protection": bars}}, str(RUNS), _env_token(), lambda s, f: None)
            return _summ(r)
        res = OPT.optimise(evaluate, path, aff, epsg, dx, nb, me, float(b.get("wall_cost_pkr_per_m2", 0.0)), float(b.get("road_penalty_pkr_per_km", 0.0)), progress=lambda s, f: prog(s, 0.05 + 0.9 * f))
        best = res["best"]
        final = RUNS_MOD.execute(g, {**base_p, "interventions": {"protection": best["barriers"]}}, str(RUNS), _env_token(), lambda s, f: None)
        _history_add(final, g)
        return {"baseline": _summ(base), "optimised": _summ(final), "barriers": best["barriers"], "evaluations": res["evaluations"], "note": res["note"],
                "history": [{"objective": h["objective"], "loss_pkr": h["loss_pkr"]} for h in res["history"]]}
    return jsonify({"job": _job(fn)})


# ------------------------------------------------------------------ average annual loss
@app.post("/area/compute-aal")
def compute_aal():
    b = request.get_json(force=True); g = _geom(); lat, lon = _centroid(g); p = dict(b.get("params", {}))
    Ts = [int(t) for t in b.get("periods", [2, 5, 10, 25, 50, 100])]; D = float(b.get("duration_h", 6)); cf = float(b.get("climate_factor", 1.0))
    def fn(prog):
        tab = DS.return_period_table(lat, lon, n_boot=30)
        def run_T(T):
            h = DS.design_hyetograph(tab, T, D, 15, lat, lon, "imerg", cf)
            r = RUNS_MOD.execute(g, {**{k: v for k, v in p.items() if k != "rain"}, "mode": "rain", "rain": {k: h[k] for k in ("times_h", "rate_mm_h", "source")}}, str(RUNS), _env_token(), lambda s, f: None)
            s = _summ(r); s["depth_mm"] = h["total_mm"]; _history_add(r, g); return s
        out = AAL.compute(run_T, Ts, prog)
        out.update(duration_h=D, climate_factor=cf, idf_cell=tab["cell"])
        return out
    return jsonify({"job": _job(fn)})


# ------------------------------------------------------------------ hotspots, dams, observed, batch
@app.get("/rainfall-hotspots")
def rainfall_hotspots():
    m = request.args.get("metric", "rx1day"); s = request.args.get("season", "monsoon")
    if m not in HS.METRICS or s not in HS.SEASONS:
        return jsonify({"error": "unknown metric or season", "metrics": HS.METRICS}), 400
    try:
        return jsonify(HS.top_cells(m, s, min(max(int(request.args.get("n", 15)), 1), 50)))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _arrays(rid):
    f = RUNS / rid / "arrays.npz"
    if not f.exists():
        abort(404)
    return np.load(f), json.loads((RUNS / rid / "manifest.json").read_text())


@app.get("/runs/<rid>/dams")
def run_dams(rid):
    z, man = _arrays(rid)
    if "deposit" not in z.files:
        return jsonify({"error": "this run has no runout (nothing was deposited)"}), 400
    dem = z["dem"]; valid = np.isfinite(dem); dx = float(man["grid"]["resolution_m"])
    res = DAM.assess(dem, np.nan_to_num(z["deposit"]), valid, dx, float(request.args.get("min_drainage_km2", 0.5)), float(request.args.get("min_dam_m", 2.0)))
    from affine import Affine
    from pyproj import Transformer
    t = man["grid"]["transform"]; aff = Affine(t[1], 0, t[0], 0, t[5], t[3]); tr = Transformer.from_crs(int(man["grid"]["crs"].split(":")[1]), 4326, always_xy=True)
    for d in res["dams"]:
        x, y = aff * (d["centroid_rc"][1] + 0.5, d["centroid_rc"][0] + 0.5); d["lon"], d["lat"] = tr.transform(x, y)
    return jsonify(res)


@app.post("/runs/<rid>/validate-observed")
def run_validate_observed(rid):
    z, man = _arrays(rid)
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "upload observed polygons (.geojson or zipped shapefile) or a 0/1 GeoTIFF"}), 400
    from affine import Affine
    t = man["grid"]["transform"]; grid = {**man["grid"], "affine": Affine(t[1], 0, t[0], 0, t[5], t[3])}
    thr = float(request.form.get("depth_m", 0.3))
    try:
        obs = OB.observed_mask(f.read(), f.filename, grid)
    except Exception as e:
        return jsonify({"error": f"could not read the observed extent: {e}"}), 400
    model = np.nan_to_num(z["hmax"]) >= thr
    valid = np.isfinite(z["dem"])
    return jsonify({"depth_threshold_m": thr, **OB.score(model, obs, valid),
                    "note": "scored on the run's grid inside the analysed area; observed extent must cover the same event"})


def _batch_html(ids):
    rows = ""
    for rid in ids:
        f = RUNS / rid / "summary.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text()); s = d["summary"]; ex = s.get("exposure") or {}; fl = s.get("flow") or {}; tr = s.get("trigger") or {}
        rows += (f"<tr><td>{rid[:8]}</td><td>{s.get('mode')}</td><td>{(s.get('rain') or {}).get('total_mm', 0):,.0f}</td><td>{tr.get('failing_area_km2', 0):,.2f}</td>"
                 f"<td>{fl.get('released_volume_m3', 0):,.0f}</td><td>{fl.get('impacted_area_km2', 0):,.2f}</td><td>{fl.get('max_depth_m', 0):,.1f}</td>"
                 f"<td>{ex.get('buildings_ds_ge3', 0):,}</td><td>{(ex.get('direct_loss_pkr') or 0) / 1e6:,.0f}</td></tr>")
    return ("<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;margin:28px;color:#1f2326}table{border-collapse:collapse;font-size:12px}"
            "td,th{padding:4px 9px;border-bottom:1px solid #ddd;text-align:right}th{background:#7a4a12;color:#fff}.n{font-size:11px;color:#a33}</style></head><body>"
            "<h1 style='font-size:18px'>LANDLAB batch summary</h1><p class='n'>Screening grade; scenario strengths and friction; losses use assumed unit costs.</p>"
            "<table><tr><th>Run</th><th>Mode</th><th>Rain mm</th><th>Failing km2</th><th>Released m3</th><th>Impacted km2</th><th>Max depth m</th><th>Buildings DS3+</th><th>Loss M PKR</th></tr>"
            + rows + "</table></body></html>")


@app.get("/batch-report.html")
def batch_html():
    ids = [x for x in request.args.get("ids", "").split(",") if x]
    return Response(_batch_html(ids), mimetype="text/html")


@app.get("/batch-report.pdf")
def batch_pdf():
    import weasyprint
    ids = [x for x in request.args.get("ids", "").split(",") if x]
    return Response(weasyprint.HTML(string=_batch_html(ids)).write_pdf(), mimetype="application/pdf", headers={"Content-Disposition": "inline; filename=landlab_batch.pdf"})


# ------------------------------------------------------------------ GIS export, run management
@app.get("/runs/<rid>/export.zip")
def run_export(rid):
    from . import exports
    if not (RUNS / rid / "manifest.json").exists():
        abort(404)
    return Response(exports.build_zip(RUNS / rid), mimetype="application/zip", headers={"Content-Disposition": f"attachment; filename=landlab_{rid[:8]}.zip"})


@app.delete("/runs/<rid>")
def run_delete(rid):
    import shutil
    d = RUNS / rid
    if not d.exists() or not rid.isalnum():
        abort(404)
    shutil.rmtree(d)
    f = ROOT / "datasets" / "state" / "history.json"
    if f.exists():
        h = [x for x in json.loads(f.read_text()) if x["run_id"] != rid]; f.write_text(json.dumps(h))
    return jsonify({"ok": True})


@app.post("/runs/cleanup")
def runs_cleanup():
    """Delete runs older than N days that are not in the 30 most recent history entries (disk hygiene). dry_run by default."""
    import shutil, time as _t
    b = request.get_json(force=True, silent=True) or {}
    days, dry = float(b.get("older_than_days", 14)), bool(b.get("dry_run", True))
    f = ROOT / "datasets" / "state" / "history.json"
    keep = {x["run_id"] for x in (json.loads(f.read_text())[:30] if f.exists() else [])}
    out = []
    for d in RUNS.iterdir():
        if d.is_dir() and d.name not in keep and (_t.time() - d.stat().st_mtime) > days * 86400:
            sz = sum(p.stat().st_size for p in d.rglob("*") if p.is_file()); out.append({"run_id": d.name, "mb": round(sz / 1e6, 1)})
            if not dry:
                shutil.rmtree(d)
    return jsonify({"dry_run": dry, "runs": out, "total_mb": round(sum(x["mb"] for x in out), 1)})


@app.get("/api/queue")
def api_queue():
    q = [{"job": k, "state": v["state"], "stage": v.get("stage"), "age_s": round(time.time() - v.get("t0", time.time()))} for k, v in JOBS.items() if v["state"] in ("queued", "running")]
    return jsonify({"active": q, "position_note": "one heavy job runs at a time; queued jobs start in order of arrival"})
