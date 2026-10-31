"""Topographic control on the starting water table (a TOPMODEL-style stand-in for lateral flow and perched water).

Water converges into hollows and on valley floors and drains off spurs, so the same rain starts a hollow wetter than a ridge. The topographic wetness index
TWI = ln(a / tan b) (a = specific upslope area, Ch. 4) is standardised over the area, and the depth to the starting water table varies with it:
    water_table(cell) = water_table0 x exp( -beta x (TWI - mean) / sd ),    clipped to 0.3 .. 25 m
beta = 0 gives the old uniform water table (the default until calibrated). Limits: the upslope area is counted only inside the analysis area (a cell at the
edge misses what drains in from outside), there is no time dynamics of the saturated zone, and a larger beta only moves the starting state, not the rain."""
from __future__ import annotations
import numpy as np
from ..data.preprocessing import terrain

PARAMS = {"beta": 0.0}       # neutral until scripts/calibrate_ground.py fits it (configs/ground_classes.yaml: wetness.beta)


def twi_field(dem, valid, res):
    """TWI on the analysis grid (NaN outside valid). NaN cells in the DEM stay NaN so they act as outlets."""
    z = np.where(valid | np.isfinite(dem), dem, np.nan).astype(float)
    filled = terrain.fill_pits(z)
    d8 = terrain.d8_flow(filled, res, res)
    sl = terrain.slope_aspect(np.where(np.isfinite(z), z, np.nanmedian(z)), res, res)["slope_deg"]
    t = terrain.hydrology_indices(sl, d8["flow_accum_cells"], res, res)["TWI"]
    return np.where(valid, t, np.nan).astype("float32")


def apply(sp, twi, valid, beta=None):
    """Copy of the scenario point with a per-cell water table depth. beta = 0 (or no TWI) leaves it unchanged."""
    beta = PARAMS["beta"] if beta is None else float(beta)
    if beta == 0.0 or twi is None:
        return sp, {"beta": 0.0}
    t = np.where(valid & np.isfinite(twi), twi, np.nan); mu, sd = np.nanmean(t), max(float(np.nanstd(t)), 1e-6)
    zs = np.nan_to_num((twi - mu) / sd, nan=0.0)
    sp2 = dict(sp); sp2["water_table"] = np.clip(float(sp["water_table"]) * np.exp(-beta * zs), 0.3, 25.0).astype("float32")
    return sp2, {"beta": beta, "water_table_median_m": float(np.nanmedian(sp2["water_table"][valid])), "twi_mean": float(mu), "twi_sd": sd}
