#!/usr/bin/env python3
"""Forecast validation for the monitoring agents: Open-Meteo precipitation forecasts archived at lead 0, 1 and 2 days (previous-runs API) against the Open-Meteo archive
(ERA5-based reanalysis rain) for the 2026 monsoon, at random points in northern Pakistan. 'Observed' here is a reanalysis, not a gauge, so this scores the forecast against
the best available gridded truth, and both smooth convective bursts. Daily totals; hit/false-alarm for a 20 mm/day watch level. Writes docs/validation/forecast_audit.json and
stores the per-lead bias factors as the prior of the bias-correction agent (datasets/state/agents/forecast_bias.json)."""
import json, sys, time
from pathlib import Path
import numpy as np, requests
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import agents as AG      # noqa: E402

START, END = "2026-06-15", "2026-09-30"
rng = np.random.default_rng(8); pts = list(zip(rng.uniform(30.5, 36.8, 40), rng.uniform(69.5, 77.0, 40)))
rows = []; used = 0
for la, lo in pts:
    try:
        a = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=dict(latitude=la, longitude=lo, start_date=START, end_date=END, timezone="UTC",
             hourly="precipitation,precipitation_previous_day1,precipitation_previous_day2"), timeout=60).json()["hourly"]
        o = requests.get("https://archive-api.open-meteo.com/v1/archive", params=dict(latitude=la, longitude=lo, start_date=START, end_date=END, timezone="UTC", hourly="precipitation"), timeout=60).json()["hourly"]
    except Exception as e:
        print("skip", la, lo, str(e)[:60]); continue
    ob = np.nan_to_num(np.array(o["precipitation"], float))
    for lead, key in enumerate(("precipitation", "precipitation_previous_day1", "precipitation_previous_day2")):
        f = np.array([np.nan if v is None else v for v in a[key]], float)
        n = min(len(f), len(ob)) // 24
        for d in range(n):
            fs, os_ = f[d * 24:(d + 1) * 24], ob[d * 24:(d + 1) * 24]
            if np.isnan(fs).any():
                continue
            fm, om = float(fs.sum()), float(os_.sum())
            rows.append({"lead_day": lead, "fcst_mm": fm, "obs_mm": om, "hit": fm >= 20 and om >= 20, "false_alarm": fm >= 20 and om < 20, "miss": fm < 20 and om >= 20})
    used += 1; time.sleep(0.3)
out = {"points": used, "period": [START, END], "truth": "Open-Meteo archive (ERA5-based reanalysis), not gauges", "by_lead_day": {}}
for lead in (0, 1, 2):
    r = [x for x in rows if x["lead_day"] == lead]; f = np.array([x["fcst_mm"] for x in r]); o = np.array([x["obs_mm"] for x in r])
    hit, fa, miss = sum(x["hit"] for x in r), sum(x["false_alarm"] for x in r), sum(x["miss"] for x in r)
    out["by_lead_day"][str(lead)] = {"days": len(r), "mean_fcst_mm": float(f.mean()), "mean_obs_mm": float(o.mean()), "bias_ratio": float(f.sum() / max(o.sum(), 1e-9)), "mae_mm": float(np.abs(f - o).mean()),
        "corr": float(np.corrcoef(f, o)[0, 1]), "hits": hit, "false_alarms": fa, "misses": miss, "POD": hit / max(hit + miss, 1), "FAR": fa / max(hit + fa, 1), "CSI": hit / max(hit + fa + miss, 1)}
fac = AG.bias_from_scores(rows, prior_n=200.0)
out["bias_factors_applied"] = {k: v["factor"] for k, v in fac.items()}
(ROOT / "docs/validation/forecast_audit.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out["by_lead_day"], indent=0)[:1500]); print(out["bias_factors_applied"])
b = AG.BIAS; cur = json.loads(b.read_text()) if b.exists() else {}
cur["prior"] = {k: {"n": v["n"], "factor": v["factor"], "source": "back-test " + START + ".." + END} for k, v in fac.items()}; b.write_text(json.dumps(cur, indent=1))
