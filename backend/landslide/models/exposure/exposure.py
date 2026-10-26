"""Tier X exposure & consequence indicators (§5.6, M21). No damage without hazard-specific fragility (never flood curves)."""
from __future__ import annotations
import numpy as np
from ...errors import InsufficientData


def population_exposed(pop_grid, impact_mask, overlap_fraction=None):
    """N = sum(pop_i * overlap_i). Reports reference caveat; unmapped assets are NOT 'zero risk'."""
    ov = np.where(impact_mask, 1.0, 0.0) if overlap_fraction is None else overlap_fraction * impact_mask
    return float(np.nansum(pop_grid * ov))


def points_in_mask(xs, ys, mask, transform):
    """transform = (x0, dx, y0, dy) with dy<0 for north-up. Returns boolean per point."""
    x0, dx, y0, dy = transform
    c = np.floor((np.asarray(xs) - x0) / dx).astype(int)
    r = np.floor((np.asarray(ys) - y0) / dy).astype(int)
    ok = (r >= 0) & (r < mask.shape[0]) & (c >= 0) & (c < mask.shape[1])
    out = np.zeros(len(c), bool)
    out[ok] = mask[r[ok], c[ok]]
    return out


def dynamic_pressure(rho_mix, v):
    """p_dyn ~ rho v^2 (Pa); convention factor must be documented with outputs."""
    return np.asarray(rho_mix) * np.asarray(v) ** 2


def impact_classes(depth_m, v_ms, rho_mix=1800.0, thresholds_kpa=(1, 5, 30)):
    p = dynamic_pressure(rho_mix, v_ms) / 1e3
    return np.digitize(p, thresholds_kpa), p


def damage(intensity, fragility):
    if fragility is None:
        raise InsufficientData(["hazard-specific fragility functions"], "M21 damage")
    return fragility(intensity)


def expected_annual_loss(probabilities, losses):
    """EAL = ∫ L(p) dp via trapezoid; only with a credible frequency model (caller asserts)."""
    p, l = np.asarray(probabilities, float), np.asarray(losses, float)
    o = np.argsort(p)
    return float(np.trapezoid(l[o], p[o]) if hasattr(np, "trapezoid") else np.trapz(l[o], p[o]))


def percentile_summary(samples):
    s = np.asarray(samples, float)
    return {"p05": float(np.nanpercentile(s, 5)), "p50": float(np.nanpercentile(s, 50)), "p95": float(np.nanpercentile(s, 95))}
