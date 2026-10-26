#!/usr/bin/env python3
"""Calibrate the physical parameters (cohesion, friction, root cohesion, soil depth, water table, Ks) against the report inventory.   *** COMPUTE HEAVY: run only on request ***

Samples: day-resolved rain-triggered reports whose location accuracy is <= 10 km (events) and, per event, matched same-place same-season control days.
For each sample: 14 days of ERA5-Land hourly rain, K=256 random cells in the accuracy disc (30 m slope raster). Score = instability (lower p10 FS).
Optimiser: differential evolution maximising AUC on TRAINING blocks (1 degree spatial blocks, 5 folds); reported AUC is on the held-out block, averaged over folds.
Default parameters are scored on the same held-out folds. If calibration does not beat the defaults held-out, the defaults stay (written to the JSON either way).
Writes docs/validation/physics_calibration.json."""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd, torch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D, rain_features as RFt, spatial as SP, stats as ST, physcal as PC     # noqa: E402
from landslide.app import pipeline as P                                                                              # noqa: E402
from scipy.optimize import differential_evolution                                                                      # noqa: E402

K, DAYS, N_CTL = 256, 34, 10          # 31 days before the storm window + the 3-day storm window (PC.STORM_H)
# DEFAULT = the scenario values the platform shipped with, with NO antecedent effect (api_wet = 1e9 switches it off).
DEFAULT = {"c": 3000.0, "phi": 30.0, "cr": 1000.0, "z": 1.5, "wt": 4.0, "ks": 3.7e-6, "api_wet": 1e9, "k": 0.90, "s_dry": 0.25, "s_wet": 0.90, "f_wt": 0.5}
# Fitted. The antecedent constants (k, api_wet, s_dry, s_wet, f_wt) are the new physics (engine/antecedent.py); the rest are the strength/hydraulic scenario values.
BOUNDS = {"c": (500.0, 15000.0), "phi": (18.0, 42.0), "cr": (0.0, 8000.0), "z": (0.5, 4.0), "wt": (1.0, 10.0), "ks": (1e-7, 1e-4),
          "api_wet": (30.0, 400.0), "k": (0.80, 0.97), "s_dry": (0.10, 0.60), "s_wet": (0.60, 1.00), "f_wt": (0.0, 0.8)}
ANTE = ("api_wet", "k", "s_dry", "s_wet", "f_wt")
ANTE_DEFAULT_ON = {"api_wet": 120.0, "k": 0.90, "s_dry": 0.25, "s_wet": 0.90, "f_wt": 0.5}


def build_samples():
    df = D.load(); ev = df[(df.trigger == "rain") & df.date.notna() & (df.radius_km <= 10) & (df.date >= "1981-01-01") & (df.date <= "2026-04-30")].reset_index(drop=True)
    st = SP.Stack(layers=["slope"], with_ml=False)
    ctl = RFt.controls(ev, n_per=N_CTL, seed=11)
    rows = [{"kind": 1, "lon": r.lon, "lat": r.lat, "date": r.date, "rad": r.radius_km, "grp": i} for i, r in ev.iterrows()] + \
           [{"kind": 0, "lon": r.lon, "lat": r.lat, "date": r.date, "rad": r.radius_km, "grp": int(r.event_idx)} for _, r in ctl.iterrows()]
    S = pd.DataFrame(rows)
    rng = np.random.default_rng(5); slopes = np.full((len(S), K), np.nan, "float32"); rain = np.zeros((len(S), DAYS * 24), "float32")
    for i, r in S.iterrows():
        lo, la = SP.disc_points(r.lon, r.lat, r.rad, K, rng); sm = st.sample(lo, la, ["slope"])
        slopes[i] = np.where(sm["_inside"], sm.get("slope30", sm["slope"]), np.nan)
        _, v = RFt.series(r.lat, r.lon, r.date, back_days=DAYS - 1); rain[i, -len(v):] = v[-DAYS * 24:]
        if len(v) < DAYS * 24 - 24:
            rain[i] = np.nan                                          # incomplete history: drop this sample (never zero-fill rainfall)
    S["block"] = SP.blocks(S.lon.values, S.lat.values, 1.0)
    return S, slopes, rain


def main():
    t0 = time.time(); dev = PC.device(); print("device", dev, flush=True)
    S, slopes, rain = build_samples(); print("samples", len(S), "events", int(S.kind.sum()), round(time.time() - t0), "s", flush=True)
    sl = torch.as_tensor(np.nan_to_num(slopes, nan=0.0), device=dev); rn = torch.as_tensor(rain, device=dev)
    tex = P.SOIL.GA_PRIORS["sandy loam"]; ks0, psi, por = tex; dth = por - 0.25
    y = S.kind.values
    good = np.isfinite(rain).all(1) & (np.isfinite(slopes).sum(1) > 20); rn = torch.nan_to_num(rn)
    def scores(theta):
        s = PC.score_params({**DEFAULT, **theta}, rn, sl, (ks0, psi, dth), None).cpu().numpy(); return np.where(good, s, np.nan)
    blocks = S.block.values; ub = np.unique(blocks); rng = np.random.default_rng(1); perm = rng.permutation(len(ub)); fold = {g: i % 5 for g, i in zip(ub[perm], range(len(ub)))}; f = S.block.map(fold).values
    names = list(BOUNDS); b = [BOUNDS[k] for k in names]
    res = {"n_samples": int(len(S)), "n_events": int(y.sum()), "folds": []}
    for k in range(5):
        tr, te = f != k, f == k
        if y[te].sum() < 3: continue
        def loss(x):
            th = dict(zip(names, x)); s = scores(th); m = tr & np.isfinite(s); return -ST.auc(y[m], s[m])
        r = differential_evolution(loss, b, seed=k, maxiter=40, popsize=12, tol=1e-4, polish=False)
        th = dict(zip(names, r.x)); s_c = scores(th); s_d = scores(DEFAULT); s_a = scores(ANTE_DEFAULT_ON); m = te & np.isfinite(s_c)
        res["folds"].append({"fold": k, "auc_calibrated": ST.auc(y[m], s_c[m]), "auc_default": ST.auc(y[m], s_d[m]), "auc_default_with_antecedent": ST.auc(y[m], s_a[m]),
                             "params": th, "train_auc": -r.fun, "n_test_events": int(y[te].sum())})
        print(k, round(res["folds"][-1]["auc_default"], 3), "->", round(res["folds"][-1]["auc_calibrated"], 3), flush=True)
    res["default"] = {"auc": float(np.mean([x["auc_default"] for x in res["folds"]])), "params": DEFAULT}
    res["default_with_antecedent"] = {"auc": float(np.mean([x["auc_default_with_antecedent"] for x in res["folds"]])), "params": ANTE_DEFAULT_ON}
    res["calibrated"] = {"auc": float(np.mean([x["auc_calibrated"] for x in res["folds"]]))}
    allp = {k: float(np.median([x["params"][k] for x in res["folds"]])) for k in names}
    res["calibrated"]["params"] = allp; res["calibrated"]["params_text"] = ", ".join(f"{k}={v:.3g}" for k, v in allp.items())
    res["adopt_calibrated"] = bool(res["calibrated"]["auc"] > res["default"]["auc"] + 0.02)
    res["note"] = "held-out spatial blocks; calibrated parameters are adopted only if they beat the defaults by > 0.02 AUC"
    (ROOT / "docs/validation/physics_calibration.json").write_text(json.dumps(res, indent=1)); print(json.dumps({k: res[k] for k in ("default", "default_with_antecedent", "calibrated", "adopt_calibrated")}, indent=1)[:1400])


if __name__ == "__main__":
    main()
