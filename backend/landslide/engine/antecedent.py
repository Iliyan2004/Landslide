"""Antecedent wetness: the soil does not start every storm at the same moisture.
Antecedent precipitation index  API = sum_i P_i k^i  over the daily totals before the storm (i = 1 is the day before; k = 0.90, i.e. a ~10-day memory).
w = clip(API / API_wet, 0, 1) is the wetness state (0 dry, 1 wet). It sets the initial moisture content and lifts the baseline water table:
    theta_i = theta_r + (theta_s - theta_r) (S_dry + (S_wet - S_dry) w)           water_table = water_table0 (1 - f_wt w)
Constants are the values fitted by scripts/calibrate_physics.py (PARAMS)."""
from __future__ import annotations
import numpy as np

# Fitted by scripts/calibrate_physics.py (docs/validation/physics_calibration.json: held-out AUC 0.593 -> 0.683 together with the strength set; 144 events + matched controls).
PARAMS = {"k": 0.955, "api_wet_mm": 54.9, "s_dry": 0.318, "s_wet": 0.955, "f_wt": 0.202, "theta_r": 0.05}


def api(prior_daily_mm, k=None):
    """prior_daily_mm: daily totals in time order, the LAST entry being the day immediately before the storm."""
    p = np.maximum(np.asarray(prior_daily_mm, float), 0.0)[::-1]
    return float(np.sum(p * (k or PARAMS["k"]) ** np.arange(1, len(p) + 1)))


def wetness(api_mm, prm=None):
    prm = prm or PARAMS
    return float(np.clip(api_mm / prm["api_wet_mm"], 0.0, 1.0))


def apply(sp, api_mm, prm=None):
    """Copy of the scenario point with moisture and water table set from the antecedent state. Returns (sp2, report)."""
    prm = {**PARAMS, **(prm or {})}; w = wetness(api_mm, prm); sp2 = dict(sp)
    se = prm["s_dry"] + (prm["s_wet"] - prm["s_dry"]) * w
    sp2["theta_i"] = float(min(prm["theta_r"] + (sp["theta_s"] - prm["theta_r"]) * se, sp["theta_s"] - 0.02))
    sp2["water_table"] = float(sp["water_table"] * (1.0 - prm["f_wt"] * w))
    return sp2, {"api_mm": float(api_mm), "wetness": w, "theta_i": sp2["theta_i"], "water_table_m": sp2["water_table"]}
