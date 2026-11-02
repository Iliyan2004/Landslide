#!/usr/bin/env python3
"""Two checks that need no new data.
(1) Design-storm backtest: at many points in northern Pakistan fit the Gumbel (L-moments) to the FIRST 30 years of the ERA5-Land 24 h annual maxima and count
    how often the LAST ~15 years exceed the fitted T-year depth. A calibrated T-year level is exceeded 1/T of the time (pooled over points; points are spatially
    correlated, so the pooled count is more variable than a binomial).
(2) AAL stability: with the stored return-period losses of docs/validation/area_demo.json, recompute the average annual loss leaving out each return period in
    turn, and with a log-log (power-law) interpolation in place of the trapezoid, to show how much the figure depends on the integration choices.
Writes docs/validation/design_storm_backtest.json and aal_sensitivity.json."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import design_storm as DS     # noqa: E402
from landslide.engine import aal                  # noqa: E402

rng = np.random.default_rng(4)
pts = [(la, lo) for la, lo in zip(rng.uniform(30.0, 37.0, 140), rng.uniform(69.0, 77.5, 140))]
Ts = [2, 5, 10, 25]; exc = {T: 0 for T in Ts}; tot = 0; used = 0; rows = []
for la, lo in pts:
    try:
        dur, yrs, A, cell = DS.annual_maxima(la, lo)
    except Exception:
        continue
    j = int(np.argmin(np.abs(dur - 24)));
    if len(yrs) < 40:
        continue
    x = A[:, j]; k = len(yrs) - 15; xi, al = DS.gumbel_lmom(x[:k]); test = x[k:]
    for T in Ts:
        exc[T] += int((test > DS.gumbel_quantile(xi, al, T)).sum())
    tot += len(test); used += 1
bt = {"points": used, "train_years": int(k), "test_years": int(len(test)), "test_cells": tot, "by_T": {str(T): {"expected_share": 1.0 / T, "observed_share": exc[T] / tot} for T in Ts},
      "note": "pooled over points; points are correlated, so the sampling error is larger than binomial. ERA5-Land 24 h annual maxima, nearest cell."}
(ROOT / "docs/validation/design_storm_backtest.json").write_text(json.dumps(bt, indent=1)); print(json.dumps(bt["by_T"]))

d = json.load(open(ROOT / "docs/validation/area_demo.json")); out = {}
for key in ("aal_current", "aal_ssp585"):
    sc = d[key]["result"]["scenarios"]; T = np.array([s["T"] for s in sc], float); L = np.array([s["loss_pkr"] for s in sc], float)
    full = aal.eal(T, L)["eal"]; drop = {}
    for i in range(len(T)):
        m = np.ones(len(T), bool); m[i] = False; drop[int(T[i])] = aal.eal(T[m], L[m])["eal"] / full
    # power-law (log-log) interpolation of loss against p between the scenarios, same tails
    p = 1 / T; o = np.argsort(p); p, Lp = p[o], L[o]; g = np.linspace(np.log(p[0]), np.log(p[-1]), 2000)
    Lg = np.exp(np.interp(g, np.log(p), np.log(np.maximum(Lp, 1.0)))); body = float(np.trapezoid(Lg, np.exp(g))); tail_r = Lp[0] * p[0]; tail_f = 0.5 * Lp[-1] * (1 - p[-1])
    out[key] = {"aal_pkr": full, "ratio_leaving_out_each_T": drop, "ratio_loglog_interpolation": (body + tail_r + tail_f) / full,
                "ratio_without_frequent_tail": (full - aal.eal(T, L)["parts"]["frequent_tail"]) / full}
    print(key, {k: round(v, 2) if not isinstance(v, dict) else {a: round(b, 2) for a, b in v.items()} for k, v in out[key].items() if k != "aal_pkr"})
(ROOT / "docs/validation/aal_sensitivity.json").write_text(json.dumps(out, indent=1))
