"""Earthquake-triggered failure (methodology §5.2, M13): pseudostatic FS, yield acceleration, Newmark displacement.

Infinite-slope pseudostatic derivation (horizontal coefficient kh acting outward/downslope):
  sigma = gamma z cos b (cos b - kh sin b),  tau = gamma z cos b (sin b + kh cos b)
  FS_ps = [c + (sigma - u) tan phi] / tau
Exact yield coefficient (FS_ps = 1):
  ky = [c + (gamma z cos^2 b - u) tan phi - gamma z sin b cos b] / [gamma z (cos^2 b + sin b cos b tan phi)]
The methodology's simplified a_y ~ (FS-1) g sin b is also provided for comparison only.
"""
from __future__ import annotations
import numpy as np
from ...units import G, GAMMA_W


def pseudostatic_fs(slope_deg, z, c_eff, phi_deg, gamma, kh, m=0.0, c_root=0.0):
    b = np.deg2rad(slope_deg)
    cb, sb = np.cos(b), np.sin(b)
    u = np.clip(m, 0, 1) * GAMMA_W * z * cb**2
    sigma = np.maximum(gamma * z * cb * (cb - kh * sb) - u, 0.0)
    tau = gamma * z * cb * (sb + kh * cb)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (c_eff + c_root + sigma * np.tan(np.deg2rad(phi_deg))) / tau


def yield_coefficient(slope_deg, z, c_eff, phi_deg, gamma, m=0.0, c_root=0.0):
    """ky (dimensionless). ky<=0 => statically unstable already (yield acceleration clipped to 0)."""
    b = np.deg2rad(slope_deg)
    cb, sb = np.cos(b), np.sin(b)
    t = np.tan(np.deg2rad(phi_deg))
    u = np.clip(m, 0, 1) * GAMMA_W * z * cb**2
    num = c_eff + c_root + (gamma * z * cb**2 - u) * t - gamma * z * sb * cb
    den = gamma * z * (cb**2 + sb * cb * t)
    return num / den


def yield_acceleration(slope_deg, z, c_eff, phi_deg, gamma, m=0.0, c_root=0.0):
    """a_y in m/s^2 (>=0)."""
    return np.maximum(yield_coefficient(slope_deg, z, c_eff, phi_deg, gamma, m, c_root), 0.0) * G


def yield_acceleration_simplified(fs_static, slope_deg):
    """Methodology screening form a_y ~ (FS-1) g sin b (comparison only)."""
    return np.maximum(fs_static - 1.0, 0.0) * G * np.sin(np.deg2rad(slope_deg))


def newmark_displacement(accel_ms2, dt, a_y):
    """One-directional (downslope-positive) rigid-block integration.

    v_{n+1} = max(0, v_n + (a_n - a_y) dt); D += 0.5 (v_n + v_{n+1}) dt  (trapezoid: exact for piecewise-constant a).
    `accel_ms2`: ground acceleration component along the slope in m/s^2 (sign = downslope positive).
    No yield exceedance -> exactly 0 displacement. Returns displacement (m), peak velocity (m/s).
    """
    a = np.asarray(accel_ms2, float)
    if a_y < 0:
        raise ValueError("a_y must be >=0")
    v = 0.0
    d = 0.0
    vmax = 0.0
    for an in a:
        vn = max(0.0, v + (an - a_y) * dt)
        d += 0.5 * (v + vn) * dt
        v = vn
        vmax = max(vmax, v)
    return d, vmax


def arias_intensity(accel_ms2, dt):
    """Ia = pi/(2g) * integral a^2 dt  (m/s)."""
    a = np.asarray(accel_ms2, float)
    return np.pi / (2 * G) * np.trapz(a**2, dx=dt) if hasattr(np, "trapz") else np.pi / (2 * G) * np.trapezoid(a**2, dx=dt)


def jibson2007_displacement_cm(a_y_g, pga_g):
    """Jibson (2007) regression (PGA form): log10 Dn[cm] = 0.215 + log10[(1-ac/amax)^2.341 (ac/amax)^-1.438].

    Regional screening ONLY (model sigma ~0.51 log units). Not measured ground movement. Verify against the
    published paper before production (methodology §12). Returns 0 where a_y >= PGA.
    """
    r = np.asarray(a_y_g, float) / np.maximum(np.asarray(pga_g, float), 1e-9)
    with np.errstate(invalid="ignore", divide="ignore"):
        logd = 0.215 + np.log10((1 - r) ** 2.341 * r ** (-1.438))
    d = np.where(r >= 1.0, 0.0, 10.0 ** logd)
    return np.where(r <= 0, np.nan, d)   # r<=0 => statically unstable: Newmark not applicable
