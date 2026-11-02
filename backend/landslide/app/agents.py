"""Autonomous monitoring agents: rule-based services that keep the platform's data feeds and jobs healthy and audit its own forecasts. No language model is involved;
each agent is a small deterministic procedure with a log, so its behaviour can be tested and explained.

 1. Data-interruption agent  note_source / cache_*: every live fetch reports success or failure; Open-Meteo calls retry, then fall back to the last good response
                              (under 6 h old) flagged as stale. health() adds staleness of the ERA5 store, presence of the key rasters, GPU, disk and run-folder size.
 2. Workflow-diagnostics agent  classify() / run_with_recovery(): a failed physics job is classified (user input, GPU memory or driver, network, other); GPU and
                              transient failures are retried once with the fallback (CPU solver, or a pause for the network) and the retry is recorded on the result.
 3. Forecast-audit agent     record_forecast() stores each monitored forecast; audit() later scores it against what Open-Meteo reports as observed for the same hours
                              (bias, error, hit/false alarm of the watch threshold) and keeps a shrunk multiplicative bias factor per lead day that the watch applies
                              (correction()). scripts/validate_forecasts.py back-fills the same scores from archived forecasts (previous-runs API).
Everything is stored under datasets/state/agents/ and exposed at /api/agents/status."""
from __future__ import annotations
import json, os, shutil, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "datasets" / "state" / "agents"; DIR.mkdir(parents=True, exist_ok=True)
EVENTS = DIR / "events.jsonl"; FORECASTS = DIR / "forecasts.jsonl"; BIAS = DIR / "forecast_bias.json"
_lock = threading.RLock(); _cache = {}; _sources = {}
MAX_EVENTS = 2000


def log(kind, **kw):
    rec = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, **kw}
    with _lock:
        with open(EVENTS, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        try:
            if EVENTS.stat().st_size > 2_000_000:
                L = EVENTS.read_text().splitlines()[-MAX_EVENTS:]; EVENTS.write_text("\n".join(L) + "\n")
        except Exception:
            pass
    return rec


def recent_events(n=50):
    if not EVENTS.exists():
        return []
    return [json.loads(x) for x in EVENTS.read_text().splitlines()[-n:]]


# ------------------------------------------------------------------ 1. data-interruption agent
def cache_put(key, data):
    with _lock:
        _cache[key] = (time.time(), data)


def cache_get(key, max_age_h):
    with _lock:
        v = _cache.get(key)
    if v is None or (time.time() - v[0]) / 3600.0 > max_age_h:
        return None
    return v[1], (time.time() - v[0]) / 3600.0


def note_source(name, ok, detail=""):
    with _lock:
        s = _sources.setdefault(name, {"ok": 0, "fail": 0, "consecutive_fail": 0, "last_ok": None, "last_fail": None, "detail": ""})
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if ok:
            if s["consecutive_fail"] >= 1:
                log("source_recovered", source=name, after_failures=s["consecutive_fail"])
            s.update(ok=s["ok"] + 1, consecutive_fail=0, last_ok=now)
        else:
            s.update(fail=s["fail"] + 1, consecutive_fail=s["consecutive_fail"] + 1, last_fail=now, detail=detail)
            if s["consecutive_fail"] in (1, 3, 10):
                log("source_down", source=name, consecutive_failures=s["consecutive_fail"], detail=detail)


def era5_staleness():
    try:
        import xarray as xr
        from . import rainfall as RF
        d = xr.open_zarr(RF.ERA5_TP); last = str(d.time.values[-1])[:10]
        return {"last_time": last, "age_days": (datetime.now(timezone.utc).date() - datetime.fromisoformat(last).date()).days}
    except Exception as e:
        return {"error": str(e)[:100]}


def gpu_state():
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        free, total = torch.cuda.mem_get_info(); torch.zeros(1, device="cuda")
        return {"available": True, "free_gb": round(free / 1e9, 2), "total_gb": round(total / 1e9, 2)}
    except Exception as e:
        return {"available": False, "error": str(e)[:100]}


def health():
    """One snapshot: data files, store freshness, live feeds, GPU, disk. status = ok | degraded | down for the components that matter to a run."""
    from . import paths
    files = {c["name"]: c["exists"] for c in paths.check() if c["required"]}
    gpu = gpu_state(); era = era5_staleness(); du = shutil.disk_usage(ROOT)
    with _lock:
        feeds = {k: dict(v) for k, v in _sources.items()}
    problems = []
    if not all(files.values()):
        problems.append("required data missing: " + ", ".join(k for k, v in files.items() if not v))
    if any(v["consecutive_fail"] >= 3 for v in feeds.values()):
        problems.append("live feed down: " + ", ".join(k for k, v in feeds.items() if v["consecutive_fail"] >= 3))
    if not gpu.get("available"):
        problems.append("GPU unavailable: runs use the CPU solver")
    elif gpu.get("free_gb", 99) < 1.5:
        problems.append(f"GPU memory low ({gpu['free_gb']} GB free): large runs fall back to CPU")
    if du.free / du.total < 0.05:
        problems.append("disk almost full")
    if era.get("age_days", 0) > 90:
        problems.append(f"ERA5 archive is {era['age_days']} days behind: hindcasts of recent events are unavailable")
    status = "down" if (not all(files.values())) else ("degraded" if problems else "ok")
    return {"status": status, "problems": problems, "required_data": files, "gpu": gpu, "era5": era, "live_feeds": feeds, "disk_free_gb": round(du.free / 1e9)}


# ------------------------------------------------------------------ 2. workflow-diagnostics agent
def classify(exc):
    from ..errors import LandslideError
    name, msg = type(exc).__name__, str(exc).lower()
    if isinstance(exc, LandslideError):
        return "user_input"
    if "out of memory" in msg or "cuda" in msg or "cudnn" in msg or "acceleratorerror" in name.lower():
        return "gpu"
    if any(k in name for k in ("ConnectionError", "Timeout", "HTTPError")) or "timed out" in msg or "connection" in msg:
        return "network"
    return "other"


def run_with_recovery(fn, params, note=lambda m: None):
    """fn(params) -> result. GPU failure: retry once on the CPU solver. Network failure: retry once after a pause. User-input errors and unknown errors are not retried
    (a repeat would fail the same way). Adds result['recovery'] describing what happened."""
    try:
        return fn(params)
    except Exception as e:
        kind = classify(e)
        log("job_error", error_class=kind, error=f"{type(e).__name__}: {str(e)[:160]}")
        if kind == "gpu":
            note("GPU failed, retrying on the CPU solver")
            try:
                import torch; torch.cuda.empty_cache()
            except Exception:
                pass
            r = fn({**params, "backend": "numba"}); action = "retried on the CPU solver after a GPU failure"
        elif kind == "network":
            note("network error, retrying once"); time.sleep(5); r = fn(params); action = "retried once after a network error"
        else:
            raise
        log("job_recovered", error_class=kind, action=action)
        if isinstance(r, dict):
            r["recovery"] = {"error_class": kind, "action": action}
            (r.get("warnings") if isinstance(r.get("warnings"), list) else r.setdefault("warnings", [])).append("Recovered automatically: " + action + ".")
        return r


# ------------------------------------------------------------------ 3. forecast-audit agent
def record_forecast(lat, lon, times_iso, fut_mm_h, issue_idx):
    rec = {"lat": round(lat, 3), "lon": round(lon, 3), "issued": times_iso[issue_idx], "times": times_iso[issue_idx:issue_idx + len(fut_mm_h)], "fcst": [round(float(x), 3) for x in fut_mm_h]}
    with _lock:
        with open(FORECASTS, "a") as f:
            f.write(json.dumps(rec) + "\n")


def score_pair(fcst, obs, thr_mm_day=20.0):
    """Daily comparison of a hourly forecast and observation over the same hours (lead days 0, 1, 2, ...). Returns per-lead-day sums and the exceedance outcome."""
    f = np.asarray(fcst, float); o = np.asarray(obs, float); n = min(len(f), len(o)) // 24
    out = []
    for d in range(n):
        a, b = float(f[d * 24:(d + 1) * 24].sum()), float(o[d * 24:(d + 1) * 24].sum())
        out.append({"lead_day": d, "fcst_mm": a, "obs_mm": b, "hit": a >= thr_mm_day and b >= thr_mm_day, "false_alarm": a >= thr_mm_day and b < thr_mm_day, "miss": a < thr_mm_day and b >= thr_mm_day})
    return out


def bias_from_scores(rows, prior_n=10.0):
    """Multiplicative bias factor per lead day = sum(obs)/sum(fcst), shrunk toward 1 with weight n/(n+prior_n) and clipped to 0.5 ... 2."""
    out = {}
    for d in sorted({r["lead_day"] for r in rows}):
        r = [x for x in rows if x["lead_day"] == d]; sf = sum(x["fcst_mm"] for x in r); so = sum(x["obs_mm"] for x in r); n = len(r)
        raw = so / sf if sf > 1.0 else 1.0; w = n / (n + prior_n)
        out[str(d)] = {"n": n, "raw_ratio": raw, "factor": float(np.clip(1.0 + w * (raw - 1.0), 0.5, 2.0))}
    return out


def audit(now=None):
    """Score stored forecasts whose horizon has passed against Open-Meteo's observed values; update the bias file. Returns what was scored."""
    from . import rainfall as RF
    if not FORECASTS.exists():
        return {"scored": 0}
    now = now or datetime.now(timezone.utc); rows, keep = [], []
    for line in FORECASTS.read_text().splitlines():
        r = json.loads(line)
        end = datetime.fromisoformat(r["times"][-1]).replace(tzinfo=timezone.utc)
        if end + timedelta(hours=6) > now or len(r["times"]) < 24:
            keep.append(line); continue
        try:
            om = RF._open_meteo_raw(r["lat"], r["lon"], past_days=min(14, max(1, (now - datetime.fromisoformat(r["times"][0]).replace(tzinfo=timezone.utc)).days + 1)), forecast_days=1)
            idx = {t: i for i, t in enumerate(om["times_iso"])}; ob = [om["rate_mm_h"][idx[t]] for t in r["times"] if t in idx]
            rows += score_pair(r["fcst"][:len(ob)], ob)
        except Exception as e:
            log("audit_failed", detail=str(e)[:100]); keep.append(line)
    with _lock:
        FORECASTS.write_text("\n".join(keep) + ("\n" if keep else ""))
    if rows:
        old = json.loads(BIAS.read_text()) if BIAS.exists() else {"scores": []}
        scores = (old.get("scores", []) + rows)[-5000:]
        BIAS.write_text(json.dumps({"scores": scores, "factors": bias_from_scores(scores), "updated": now.isoformat(timespec="seconds"), "prior": old.get("prior")}, indent=1))
        log("forecast_audit", scored=len(rows))
    return {"scored": len(rows), "pending": len(keep)}


def correction(lead_day):
    """Bias factor for a lead day, from the live audit combined with the back-test prior (state/agents/forecast_bias.json 'prior'). 1.0 when nothing is known."""
    if not BIAS.exists():
        return 1.0
    try:
        d = json.loads(BIAS.read_text()); f = (d.get("factors") or {}).get(str(lead_day)); pr = (d.get("prior") or {}).get(str(lead_day))
        return float((f or pr or {}).get("factor", 1.0))
    except Exception:
        return 1.0


def status():
    h = health()
    return {"health": h, "recent_events": recent_events(30), "forecast_bias": (json.loads(BIAS.read_text()) if BIAS.exists() else None)}


# ------------------------------------------------------------------ background loop
def _loop():
    while True:
        try:
            h = health()
            if h["status"] != "ok":
                log("health", status=h["status"], problems=h["problems"])
            audit()
        except Exception as e:
            log("agent_loop_error", detail=str(e)[:120])
        time.sleep(1800)


_started = False


def start():
    global _started
    if not _started:
        _started = True; threading.Thread(target=_loop, daemon=True).start()
