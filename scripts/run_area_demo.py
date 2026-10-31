#!/usr/bin/env python3
"""Run the heavy area tools once on a real Gilgit area through the live server: CMIP6 climate factor, average annual loss (current and SSP5-8.5 climate),
nature-based ranking, a paired mitigation run and the barrier optimiser. Writes docs/validation/area_demo.json.   *** needs the server on :5070 ***"""
import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; BASE = "http://127.0.0.1:5070"
G = {"type": "Polygon", "coordinates": [[[74.26, 35.88], [74.34, 35.88], [74.34, 35.95], [74.26, 35.95], [74.26, 35.88]]]}
P = {"mode": "rain", "strength_preset": "calibrated_reports", "texture": "sandy loam", "strength_quantile": 0.5, "backend": "auto"}
t = [i * 0.25 for i in range(1, 49)]; rate = [60.0 * (1 - abs(x - 6) / 6) for x in t]; STORM = {"times_h": t, "rate_mm_h": rate, "source": "design triangular 60 mm/h, 12 h"}
def call(path, body=None):
    r = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None, {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r, timeout=900))
def job(path, body):
    j = call(path, body)["job"]; t0 = time.time()
    while True:
        try:
            p = call(f"/runs/{j}/progress.json")
        except Exception:
            time.sleep(10); continue                   # the server is busy with the job; keep polling
        if p["state"] in ("done", "error", "failed", "cancelled"):
            return p
        time.sleep(5)
out_f = ROOT / "docs/validation/area_demo.json"
out = json.loads(out_f.read_text()) if out_f.exists() else {}
out.update(area=G, storm=STORM["source"], strength="calibrated_reports, quantile 0.5")   # resumable: finished steps are kept
def save(): out_f.write_text(json.dumps(out, indent=1, default=str))
for step, (path, body) in {
    "climate_ssp585_T50": ("/area/climate-factor", {"geometry": G, "scenario": "ssp585", "period": [2036, 2065], "T": 50, "models": 8}),
}.items():
    if (out.get(step) or {}).get("state") == "done":
        print(step, "kept", flush=True); continue
    t0 = time.time(); r = job(path, body); out[step] = {"state": r["state"], "elapsed_s": round(time.time() - t0), "result": r.get("result"), "error": r.get("error")}; save(); print(step, r["state"], flush=True)
cf = ((out["climate_ssp585_T50"].get("result") or {}).get("factor")) or 1.0
for step, (path, body) in {
    "aal_current": ("/area/compute-aal", {"geometry": G, "params": P, "periods": [2, 5, 10, 25, 50, 100], "duration_h": 6, "climate_factor": 1.0}),
    "aal_ssp585": ("/area/compute-aal", {"geometry": G, "params": P, "periods": [2, 5, 10, 25, 50, 100], "duration_h": 6, "climate_factor": cf}),
    "nbs_rank": ("/area/nbs-recommend", {"geometry": G, "params": {**P, "rain": STORM}}),
    "optimise_barriers": ("/protect/optimize", {"geometry": G, "params": {**P, "rain": STORM}, "n_barriers": 2, "max_evals": 16}),
}.items():
    if (out.get(step) or {}).get("state") == "done":
        print(step, "kept", flush=True); continue
    t0 = time.time(); r = job(path, body); out[step] = {"state": r["state"], "elapsed_s": round(time.time() - t0), "result": r.get("result"), "error": r.get("error")}; save(); print(step, r["state"], flush=True)
