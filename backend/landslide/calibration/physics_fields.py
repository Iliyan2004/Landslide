"""Physically based instability index per DEM cell for validation (no rainfall): how much saturation m is needed for FS = 1.

m_crit = [ (c + c_r)/(gamma z cos^2 b) + tan(phi) - tan(b) ] * gamma / (gamma_w tan(phi))      (infinite slope, parallel seepage)
index = 1 - clip(m_crit, 0, 1) for soil-bearing slopes (<= max_soil_slope) that are stable when dry, 1.0 if already unstable dry within the
soil-bearing range is treated separately (not a storm failure), 0 for bare rock / flat.  A higher index = less rain needed."""
from __future__ import annotations
import numpy as np
from ..units import GAMMA_W


def instability_index(slope_deg, c=3000.0, phi=30.0, z=1.5, gamma=18000.0, c_root=1000.0, max_soil_slope=45.0, min_slope=5.0):
    b = np.deg2rad(np.asarray(slope_deg, float))
    cb, sb = np.cos(b), np.sin(b)
    tphi = np.tan(np.deg2rad(phi))
    with np.errstate(all="ignore"):
        mc = ((c + c_root) / (gamma * z * cb ** 2) + tphi - np.tan(b)) * gamma / (GAMMA_W * tphi)
    idx = 1.0 - np.clip(mc, 0.0, 1.0)
    idx = np.where(mc <= 0.0, 1.0, idx)                          # unstable even when dry: maximally unstable (kept; flagged by caller if needed)
    idx = np.where((np.asarray(slope_deg) > max_soil_slope) | (np.asarray(slope_deg) < min_slope), 0.0, idx)
    return idx
