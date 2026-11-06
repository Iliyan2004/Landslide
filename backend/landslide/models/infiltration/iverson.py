"""Transient pressure-head response to rain: the Iverson (2000) solution used by USGS TRIGRS (Baum, Savage and Godt 2002, eq. 2), saturated infinite-depth form.

psi(Z,t) = (Z - d) cos^2(b) + sum_n dI_n * 2 sqrt(D1 (t - t_n)) / Ks * ierfc( Z / (2 sqrt(D1 (t - t_n))) ),   D1 = D0 / cos^2(b)
with the rain as a series of intensity steps (dI_n = change of intensity at t_n, each intensity capped at Ks), d = initial water table depth below the surface, and psi clipped to
[0, Z cos^2(b)] (the head cannot exceed full saturation). Verified against the TRIGRS 2.1.0c program: scripts/compare_trigrs.py (identical failure times on 675 cases).
Limits: a single homogeneous layer, no unsaturated zone above the water table, no surface runoff routing, D0 is a user value (default 100 Ks)."""
from __future__ import annotations
import numpy as np
from scipy.special import erfc


def ierfc(x):
    return np.exp(-x * x) / np.sqrt(np.pi) - x * erfc(x)


class Column:
    """Pressure head at depth z for every cell, advanced step by step. rain_mm_step: depth (mm) per step of dt_s seconds."""

    def __init__(self, rain_mm_step, dt_s, ks, slope_deg, z, water_table_m, d0_over_ks=100.0):
        I = np.minimum(np.asarray(rain_mm_step, float) / 1000.0 / dt_s, ks)      # m/s, capped at Ks (the excess runs off)
        self.dI = np.diff(np.concatenate([[0.0], I])); self.dt = dt_s; self.ks = float(ks)
        self.cb2 = np.cos(np.radians(slope_deg)) ** 2; self.z = z; self.D1 = d0_over_ks * ks / self.cb2
        d = np.maximum(water_table_m, 0.0)
        self.base = (z - d) * self.cb2

    def psi(self, k):
        """Head after step k (0-based): sum over the intensity changes at steps 0..k."""
        out = self.base.copy() if hasattr(self.base, "copy") else np.array(self.base, float)
        for n in range(k + 1):
            if self.dI[n] == 0.0:
                continue
            root = np.sqrt(self.D1 * (k + 1 - n) * self.dt)
            out = out + self.dI[n] * 2.0 * root / self.ks * ierfc(self.z / (2.0 * root))
        return np.clip(out, 0.0, self.z * self.cb2)

    def m(self, k):
        """Saturated fraction in the platform's convention (u = m gamma_w z cos^2 b)."""
        return self.psi(k) / np.maximum(self.z * self.cb2, 1e-9)
