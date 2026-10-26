#!/usr/bin/env python3
"""Experiment B - TEMPORAL skill of rainfall for landslide occurrence in Pakistan (ERA5-Land hourly vs the reported-event inventory).

Design: every day-resolved, rain-triggered report is an EVENT. For each event, N controls are the SAME location on other days of the SAME season
(+-30 days of day-of-year, 1981-2025), at least 7 days from any report within 25 km. Features are identical for events and controls
(rain ending 23:00 UTC of the day; intensity = max over end times within the day). Skill: ROC AUC per feature (bootstrap CI), a logistic
model with leave-one-year-out cross-validation, and the global thresholds of Caine (1980) and Guzzetti et al. (2008) as published.
Writes docs/validation/rain_threshold.json.  Caveat: controls are 'no report', not 'confirmed no landslide'."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D, rain_features as R, stats as ST   # noqa: E402
from landslide.app import rainfall as RF   # noqa: E402

N_PER = 20
df = D.load()
ev = df[(df.trigger == "rain") & df.date.notna() & (df.date >= "1981-01-01") & (df.date <= "2026-04-30")].reset_index(drop=True)
ctl = R.controls(ev, n_per=N_PER, seed=1)
rows = []
for kind, tab in (("event", ev.assign(event_idx=ev.index)), ("control", ctl)):
    for _, r in tab.iterrows():
        f = R.features(r.lat, r.lon, r.date)
        if f:
            rows.append({"kind": kind, "event_idx": int(r.event_idx), "year": int(r.date.year), "lat": r.lat, "lon": r.lon, "date": str(r.date.date()), **f})
X = pd.DataFrame(rows)
X["y"] = (X.kind == "event").astype(int)
print("events", int(X.y.sum()), "controls", int((1 - X.y).sum()), flush=True)
feats = ["I1", "I3", "I6", "I12", "I24", "I48", "I72", "I168", "day_mm", "A3", "A7", "A14", "A30", "API"]
res = {"n_events": int(X.y.sum()), "n_controls": int((1 - X.y).sum()), "controls_per_event": N_PER, "design": __doc__.split("\n\n")[0], "feature_auc": {}}
for f in feats:
    a, lo, hi = ST.auc_ci(X.y.values, X[f].values, n_boot=500, group=X.event_idx.values)
    res["feature_auc"][f] = {"auc": a, "ci95": [lo, hi]}
# the same, restricted to events whose stated location accuracy is <= 10 km (ERA5-Land cells are ~9 km: a 25-50 km report cannot be matched to a cell)
X["radius_km"] = X.event_idx.map(ev.radius_km)
Xs = X[X.radius_km <= 10]
res["radius_le_10km"] = {"n_events": int(Xs.y.sum()), "n_controls": int((1 - Xs.y).sum()), "feature_auc": {}}
for f in feats:
    a, lo, hi = ST.auc_ci(Xs.y.values, Xs[f].values, n_boot=500, group=Xs.event_idx.values)
    res["radius_le_10km"]["feature_auc"][f] = {"auc": a, "ci95": [lo, hi]}
res["inventory_note"] = "events from the merged inventory (NASA COOLR, GLC, local inventories) plus the Pakistan records of the Unified Global Landslide Catalogue (Global Fatal Landslide Database, COOLR)"
# logistic models with leave-one-year-out CV (events and their controls share the year of the event for grouping)
ev_year = X[X.kind == "event"].set_index("event_idx").year
X["group_year"] = X.event_idx.map(ev_year)
def logit_cv(cols):
    Z = np.log1p(X[cols].clip(lower=0).values)
    p = ST.cv_logistic(Z, X.y.values, X.group_year.values, C=1.0)
    a, lo, hi = ST.auc_ci(X.y.values, p, n_boot=500, group=X.event_idx.values)
    return {"cols": cols, "auc_loyo": a, "ci95": [lo, hi], "brier_cal": ST.brier(X.y.values, ST.isotonic_cv(p, X.y.values, X.group_year.values))}
res["models"] = {"I24": logit_cv(["I24"]), "I1+I24": logit_cv(["I1", "I24"]), "I3+I24+A7": logit_cv(["I3", "I24", "A7"]),
                 "I1+I6+I24+A7+A30": logit_cv(["I1", "I6", "I24", "A7", "A30"]), "I24+API": logit_cv(["I24", "API"])}
# global thresholds as published
thr = {}
for name, (a, b) in {"guzzetti_2008": (2.20, -0.44), "caine_1980": (14.82, -0.39)}.items():
    exc = np.zeros(len(X), bool)
    for D_ in (1, 3, 6, 12, 24, 48, 72):
        exc |= X[f"I{D_}"].values >= a * D_ ** b
    pod = exc[X.y == 1].mean(); pofd = exc[X.y == 0].mean()
    thr[name] = {"pod": float(pod), "false_alarm_rate_vs_controls": float(pofd), "tss": float(pod - pofd), "note": "any duration 1-72 h at/above the published curve"}
res["global_thresholds"] = thr
# a Pakistan I-D curve fitted on the training years: best log-linear curve I = a D^b on the 24 h and 3 h pair via logistic discriminant
best = ST.fit_id_threshold(X, feats_dur=[1, 3, 6, 12, 24, 48, 72])
res["fitted_id_threshold"] = best
res["data_notes"] = ["ERA5-Land ~9 km hourly smooths convective bursts: local intensities are underestimated for events and controls alike",
                     "report-based inventory: reporting depends on population and roads, so absolute probabilities are not identifiable",
                     "day-resolved, rain-triggered reports only; 'unknown'-trigger reports are excluded here"]
Path(ROOT / "docs/validation/rain_threshold.json").write_text(json.dumps(res, indent=1))
X.to_csv(ROOT / "docs/validation/rain_threshold_samples.csv", index=False)
print(json.dumps({k: res[k] for k in ("models", "global_thresholds", "fitted_id_threshold")}, indent=1)[:2500])
print({k: round(v["auc"], 3) for k, v in res["feature_auc"].items()})
