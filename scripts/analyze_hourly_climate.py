"""Hourly rainfall-intensity / antecedent-wetness / snowmelt skill against Pakistan landslide reports (ERA5-Land, 752 windows).
Events = reports, controls = same place and season in other years. Writes docs/hourly_climate_results.json."""
import json, numpy as np, geopandas as gpd, pandas as pd
from pathlib import Path
ROOT = Path(r"D:\Downloads\CMIP6"); OUT = ROOT / "landslide-platform/docs/hourly_climate_results.json"
z = np.load(r"D:\Downloads\datasets\raw\gilgit\hourly_climate.npz"); X, rec, kind = z["X"], z["rec"], z["kind"]
g = gpd.read_file(ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/landslide_inventory/landslide_inventory.gpkg")
g["t"] = pd.to_datetime(g.event_date, unit="ms"); g = g[(g.t >= "1981-01-01") & (g.t <= pd.Timestamp.today() - pd.Timedelta(days=10))].reset_index(drop=True)
trig = g.landslide_trigger.values[rec]
P = X[:, :, 0] * 1000                                  # mm per hour (ERA5-Land hourly values are accumulations since 00 UTC; difference them)
Pm = np.diff(np.concatenate([np.zeros((P.shape[0], 1)), P], 1), axis=1)
h = np.arange(P.shape[1]) % 24
Ph = np.where(h[None] == 0, P, Pm).clip(0)             # de-accumulated hourly rain, mm
def roll_max(a, n): c = np.cumsum(np.pad(a, ((0, 0), (1, 0))), 1); return (c[:, n:] - c[:, :-n]).max(1)
feat = {}
for n in (1, 3, 6, 12, 24, 48, 72): feat[f"max {n} h rain (mm)"] = roll_max(Ph, n)
feat["rain 7 days (mm)"] = Ph[:, -168:].sum(1); feat["rain 30 days (mm)"] = Ph.sum(1)
feat["soil water, top layer"] = X[:, -24:, 2].mean(1); feat["soil water, 7-28 cm"] = X[:, -24:, 3].mean(1)
sm = (X[:, :, 1] * -1000); Sm = np.where(h[None] == 0, sm, np.diff(np.concatenate([np.zeros((sm.shape[0], 1)), sm], 1), axis=1)).clip(0)
feat["snowmelt 3 days (mm)"] = Sm[:, -72:].sum(1); feat["snowmelt 10 days (mm)"] = Sm[:, -240:].sum(1)
feat["air temperature, last day (C)"] = X[:, -24:, 4].mean(1) - 273.15
def auc(pos, neg):
    neg = np.sort(neg); lo = np.searchsorted(neg, pos, "left"); hi = np.searchsorted(neg, pos, "right"); return float(np.mean((lo + .5 * (hi - lo)) / len(neg)))
def tss_thr(pos, neg):
    cand = np.unique(np.concatenate([pos, neg])); best = (-9, 0)
    for c in cand: best = max(best, (np.mean(pos >= c) - np.mean(neg >= c), c))
    return best
groups = {"all reports": np.ones(len(rec), bool), "rain-type triggers": np.isin(trig, ["rain", "downpour", "continuous_rain", "monsoon", "tropical_cyclone"])}
res = dict(n_windows=int(len(rec)), n_reports=int((kind == 1).sum()), n_controls=int((kind == 0).sum()), groups={})
for gn, gm in groups.items():
    rows = []
    for fn, v in feat.items():
        pos, neg = v[(kind == 1) & gm], v[(kind == 0) & gm]
        a = auc(pos, neg); t, c = tss_thr(pos, neg)
        rows.append(dict(feature=fn, auc=round(a, 3), tss=round(float(t), 3), threshold=round(float(c), 2), pod=round(float(np.mean(pos >= c)), 3), pofd=round(float(np.mean(neg >= c)), 3)))
    res["groups"][gn] = dict(n_pos=int(((kind == 1) & gm).sum()), rows=sorted(rows, key=lambda r: -r["auc"]))
# combined logistic model with cross-validated AUC (events vs controls)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
def cv(names, gm):
    M = np.column_stack([np.log1p(feat[n].clip(0)) if "rain" in n or "snowmelt" in n else feat[n] for n in names]); y = kind
    idx = np.where(gm)[0]; pr = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(idx, groups=rec[idx]):
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(M[idx[tr]], y[idx[tr]]); pr[idx[te]] = m.predict_proba(M[idx[te]])[:, 1]
    ok = idx; return auc(pr[ok][y[ok] == 1], pr[ok][y[ok] == 0]), make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(M[idx], y[idx])
sets = {"daily rain only (24 h, 72 h)": ["max 24 h rain (mm)", "max 72 h rain (mm)"],
        "hourly intensity (1, 3, 6 h)": ["max 1 h rain (mm)", "max 3 h rain (mm)", "max 6 h rain (mm)"],
        "intensity + antecedent rain": ["max 1 h rain (mm)", "max 6 h rain (mm)", "max 24 h rain (mm)", "rain 7 days (mm)", "rain 30 days (mm)"],
        "intensity + antecedent + soil water": ["max 1 h rain (mm)", "max 6 h rain (mm)", "max 24 h rain (mm)", "rain 7 days (mm)", "rain 30 days (mm)", "soil water, top layer", "soil water, 7-28 cm"],
        "all + snowmelt + temperature": list(feat)}
res["models"] = {}
for gn, gm in groups.items():
    res["models"][gn] = {k: round(cv(v, gm)[0], 3) for k, v in sets.items()}
OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
for gn in res["groups"]:
    print(gn, res["groups"][gn]["n_pos"]); [print("  ", r) for r in res["groups"][gn]["rows"][:6]]
print(json.dumps(res["models"], indent=1))
