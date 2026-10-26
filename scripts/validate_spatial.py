#!/usr/bin/env python3
"""Experiment A - SPATIAL skill of landslide susceptibility predictors against the report inventory, under a strict protocol.

Events: unique inventory reports (rain / unknown / quake triggers; GLOF, snow, anthropogenic excluded) inside the northern study area.
Controls: uniformly random points over the valid mask, 10 per event, scored over discs of the SAME radius distribution as events.
Score per point = aggregate over 160 random cells inside the disc of the stated location-accuracy radius.
Models are cross-validated with SPATIAL BLOCKS (1 deg x 1 deg tiles held out whole), repeated 5x; AUC with a block-bootstrap 95% CI.
The published national ML map is shown for reference but is optimistic here (trained on these reports; flat-ground negatives).
Writes docs/validation/spatial_skill.json."""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D, spatial as SP, stats as ST, physics_fields as PF   # noqa: E402

rng = np.random.default_rng(7)
df = D.load(); df = df[df.trigger.isin(["rain", "unknown", "quake"])].reset_index(drop=True)
st = SP.Stack()
S0 = st.sample(df.lon.values, df.lat.values, ["slope"])
df = df[S0["_inside"]].reset_index(drop=True)
print("events inside study area:", len(df), flush=True)
N_C = 10
clon, clat, crad = SP.random_controls(st, len(df) * N_C, df.radius_km.values, rng)
lon = np.r_[df.lon.values, clon]; lat = np.r_[df.lat.values, clat]; rad = np.r_[df.radius_km.values, crad]
y = np.r_[np.ones(len(df)), np.zeros(len(clon))].astype(int)
phys = lambda s, S: PF.instability_index(s)
# ground layers downloaded for this project (SoilGrids texture, bedrock depth, USGS Vs30, GLiM lithology): added as extra predictors
from landslide.engine import ground as GR
EXT = ROOT / "datasets/external"
extra = SP.PointRasters({"clay": str(EXT / "soilgrids/clay_15-30cm.tif"), "sand": str(EXT / "soilgrids/sand_15-30cm.tif"), "cfvo": str(EXT / "soilgrids/cfvo_15-30cm.tif"),
                         "bdticm": str(EXT / "soilgrids/bdticm_cm.tif"), "vs30": str(EXT / "vs30/vs30_pk.tif"), "glim": str(EXT / "glim/glim_pk.tif")})
if "glim" in extra.arr:
    cls = json.load(open(EXT / "glim/glim_classes.json"))
    extra.set_lithology_groups(GR.GROUP_NAMES, {int(k): GR.GROUP_NAMES.index(GR.GROUPS[v["code"]]) for k, v in cls.items() if v["code"] in GR.GROUPS})
t = time.time(); F, _ = SP.disc_features(st, lon, lat, rad, k=160, seed=3, physics_fn=phys, extra=extra); print("features", round(time.time() - t), "s", flush=True)
X = pd.DataFrame(F); X["y"] = y; X["radius_km"] = rad; X["block"] = SP.blocks(lon, lat, 1.0)
X.to_csv(ROOT / "docs/validation/spatial_samples.csv", index=False)
ok = X.frac_inside > 0.5
X = X[ok].reset_index(drop=True); y = X.y.values
print("usable", len(X), "events", int(y.sum()), flush=True)
cluster = np.where(y == 1, np.arange(len(X)), -1 - np.arange(len(X)))     # bootstrap by individual point (events/controls are independent draws)

def rep(name, s, **kw):
    a, lo, hi = ST.auc_ci(y, s, n_boot=300, group=X.block.values)
    r = {"auc": a, "ci95": [lo, hi]}; r.update(kw); return r

res = {"n_events": int(y.sum()), "n_controls": int((1 - y).sum()), "controls_per_event": N_C, "block_deg": 1.0,
       "radius_km_quartiles_events": [float(np.percentile(df.radius_km, q)) for q in (25, 50, 75)], "single_predictors": {}, "models": {}, "by_radius": {}}
# single predictors (no fitting at all)
for n in ["slope_mean", "slope_p90", "slope_max", "slope_frac_15_45", "phys_mean", "phys_p90", "phys_frac_unstable", "twi_mean", "spi_mean", "rainfall_mean",
          "dist_faults_mean", "dist_rivers_mean", "elevation_mean", "ml_prob_mean", "ml_prob_max"]:
    if n in X: res["single_predictors"][n] = rep(n, X[n].fillna(X[n].median()).values)
# cross-validated models
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
geo_cols = [c for c in X if c.startswith("geology_") or c.startswith("lulc_")]
terrain = ["slope_mean", "slope_p90", "slope_frac_15_45", "elevation_mean", "curvature_mean", "profile_curv_mean", "plan_curv_mean", "relief_mean", "roughness_mean"]
hydro = ["twi_mean", "spi_mean", "dist_drainage_mean", "dist_rivers_mean"]
env = ["rainfall_mean", "dist_faults_mean"]
human = ["dist_roads_mean", "dist_cities_mean"]
ground = [c for c in X if c.startswith("lith_") or c in ("clay_mean", "sand_mean", "cfvo_mean", "bdticm_mean", "vs30_mean")]
physc = ["phys_mean", "phys_p90", "phys_frac_unstable"]
sets = {"slope_only": ["slope_mean", "slope_p90"], "physics_infinite_slope": physc, "terrain": terrain,
        "terrain+hydro+geology+landcover+rain (hazard-only GBM)": terrain + hydro + geo_cols + env,
        "hazard-only + physics": terrain + hydro + geo_cols + env + physc,
        "hazard-only + new ground layers (GLiM, texture, bedrock depth, Vs30)": terrain + hydro + geo_cols + env + ground,
        "hazard-only + physics + new ground layers": terrain + hydro + geo_cols + env + physc + ground,
        "hazard + human-access variables (report-aware)": terrain + hydro + geo_cols + env + human,
        "report-aware + physics": terrain + hydro + geo_cols + env + human + physc}
def cv_scores(cols, kind="gbm", reps=5):
    Z = X[cols].astype(float); Z = Z.fillna(Z.median()).values
    acc = np.zeros(len(X)); cnt = np.zeros(len(X))
    for rp in range(reps):
        ug = np.unique(X.block.values); rr = np.random.default_rng(100 + rp); perm = rr.permutation(len(ug)); fold = {g: i % 5 for g, i in zip(ug[perm], range(len(ug)))}
        f = X.block.map(fold).values
        for k in range(5):
            tr, te = f != k, f == k
            if y[tr].sum() < 10 or y[te].sum() < 1: continue
            if kind == "gbm":
                m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=1.0, min_samples_leaf=20, class_weight="balanced", random_state=rp).fit(Z[tr], y[tr])
                p = m.predict_proba(Z[te])[:, 1]
            else:
                sc = StandardScaler().fit(Z[tr]); m = LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000).fit(sc.transform(Z[tr]), y[tr]); p = m.predict_proba(sc.transform(Z[te]))[:, 1]
            from scipy.stats import rankdata
            acc[te] += rankdata(p) / te.sum(); cnt[te] += 1                 # fold-wise ranks averaged over repeats
    return np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
for name, cols in sets.items():
    kind = "logit" if name in ("slope_only", "physics_infinite_slope") else "gbm"
    s = cv_scores([c for c in cols if c in X], kind)
    res["models"][name] = {**rep(name, s), "cv": "5-fold spatial blocks x5", "learner": "logistic" if kind == "logit" else "gradient boosting (depth 3)", "n_features": len(cols)}
    print(name, round(res["models"][name]["auc"], 3), flush=True)
# stratify skill by location accuracy (single predictor + best model)
best = max(res["models"], key=lambda k: res["models"][k]["auc"]); res["best_model"] = best
sbest = cv_scores([c for c in sets[best] if c in X], "gbm")
for lab, lo_, hi_ in (("<=1 km", 0, 1), ("1-5 km", 1.01, 5), (">5 km", 5.01, 1000)):
    m = (X.radius_km >= lo_) & (X.radius_km <= hi_)
    if m.sum() > 20 and y[m].sum() >= 5:
        a, l, h = ST.auc_ci(y[m], sbest[m], n_boot=300, group=X.block.values[m]); res["by_radius"][lab] = {"auc": a, "ci95": [l, h], "events": int(y[m].sum()), "controls": int((1 - y[m]).sum())}
# the published ML map, for reference, and on the strict protocol
res["reference_published_ml_note"] = "national CNN-DNN ensemble: reported test AUC 0.88-0.90 (random split, half the negatives on flat ground); trained on these reports, so the AUC above is optimistic"
Path(ROOT / "docs/validation/spatial_skill.json").write_text(json.dumps(res, indent=1))
print(json.dumps({"single": {k: round(v["auc"], 3) for k, v in res["single_predictors"].items()}, "models": {k: [round(v["auc"], 3), [round(x, 3) for x in v["ci95"]]] for k, v in res["models"].items()}, "by_radius": res["by_radius"]}, indent=1))
