"""Infinite-slope stability (methodology §5.2). Units: SI; angles in DEGREES at the API, radians inside.

FS = [c' + c_r + (gamma z cos^2 b - u) tan(phi')] / [gamma z sin b cos b],  u = m gamma_w z cos^2 b
Invalid cases (z<=0, gamma<=0) return NaN, never FS=0 (§6.2). Flat slopes -> +inf (non-failure) flagged.
"""
from __future__ import annotations
import numpy as np
from ...units import GAMMA_W

MIN_SLOPE_DEG = 0.5   # below this the driving stress is ~0: treat as non-failure, not noise


def pore_pressure_from_m(m, z, slope_deg, gamma_w=GAMMA_W):
    cb = np.cos(np.deg2rad(slope_deg))
    return np.clip(m, 0.0, 1.0) * gamma_w * z * cb**2


def factor_of_safety(slope_deg, z, c_eff, phi_deg, gamma, m=0.0, c_root=0.0, u=None, gamma_w=GAMMA_W):
    """Vectorised FS. Provide `m` (saturated fraction) OR explicit pore pressure `u` (Pa).

    Negative effective normal stress is clipped to 0 (cohesionless soil cannot carry tension).
    """
    b = np.deg2rad(np.asarray(slope_deg, dtype="float64"))
    z = np.asarray(z, dtype="float64")
    gamma = np.asarray(gamma, dtype="float64")
    cb, sb = np.cos(b), np.sin(b)
    sigma_n = gamma * z * cb**2
    if u is None:
        u = pore_pressure_from_m(m, z, slope_deg, gamma_w)
    sigma_eff = np.maximum(sigma_n - u, 0.0)
    resist = np.asarray(c_eff) + np.asarray(c_root) + sigma_eff * np.tan(np.deg2rad(phi_deg))
    drive = gamma * z * sb * cb
    with np.errstate(divide="ignore", invalid="ignore"):
        fs = resist / drive
    invalid = (z <= 0) | (gamma <= 0)
    flat = (np.rad2deg(b) < MIN_SLOPE_DEG) & ~invalid
    fs = np.where(invalid | (~np.isfinite(fs) & ~flat), np.nan, fs)
    fs = np.where(flat, np.inf, fs)
    return fs


def unsaturated_shear_strength(c_eff, sigma_n, u_a, u_w, phi_deg, phi_b_deg):
    """Fredlund et al. (1978): tau_f = c' + (sigma_n-u_a)tan(phi') + (u_a-u_w)tan(phi_b).

    Only valid with soil-water-retention data and suction >= 0 (u_a - u_w >= 0). Raises otherwise.
    """
    suction = np.asarray(u_a) - np.asarray(u_w)
    if np.any(suction < 0):
        raise ValueError("unsaturated formula must not be extrapolated to positive pore pressure (suction<0)")
    return c_eff + (np.asarray(sigma_n) - u_a) * np.tan(np.deg2rad(phi_deg)) + suction * np.tan(np.deg2rad(phi_b_deg))


def critical_m(slope_deg, z, c_eff, phi_deg, gamma, c_root=0.0, gamma_w=GAMMA_W):
    """Saturation ratio m at which FS = 1 (>1 means stable even fully saturated; <0 means already unstable dry)."""
    b = np.deg2rad(slope_deg)
    cb, sb = np.cos(b), np.sin(b)
    tphi = np.tan(np.deg2rad(phi_deg))
    num = (c_eff + c_root) / (gamma * z * cb**2) + tphi - np.tan(b)
    return num * gamma / (gamma_w * tphi)
