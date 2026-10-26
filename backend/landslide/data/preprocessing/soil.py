"""SoilGrids integration + texture + pedotransfer PRIORS (§4.3). Never derives c'/phi' from texture as measurements."""
from __future__ import annotations
import numpy as np

SOILGRIDS_LAYERS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100), (100, 200)]   # cm


def integrate_profile(values_by_layer, max_depth_cm):
    """Thickness-weighted mean of layer values down to max_depth_cm (respects layer boundaries)."""
    num = den = 0.0
    for (top, bot), v in zip(SOILGRIDS_LAYERS, values_by_layer):
        t = max(0.0, min(bot, max_depth_cm) - top)
        if t > 0 and np.isfinite(v):
            num += v * t
            den += t
    return num / den if den else np.nan


def usda_texture(sand, silt, clay):
    """USDA texture class (percent inputs summing ~100)."""
    s, si, c = float(sand), float(silt), float(clay)
    if c >= 40 and si >= 40: return "silty clay"
    if c >= 40 and s >= 45: return "sandy clay"
    if c >= 40: return "clay"
    if c >= 35 and s >= 45: return "sandy clay"
    if c >= 27 and s < 20: return "silty clay loam" if si >= 40 else "clay loam"
    if c >= 27: return "clay loam" if s < 45 else "sandy clay loam"
    if c >= 20 and s >= 45 and si < 28: return "sandy clay loam"
    if si >= 80 and c < 12: return "silt"
    if si >= 50 and (c >= 12 or si < 80): return "silt loam"
    if s >= 85 and si + 1.5 * c < 15: return "sand"
    if s >= 70 and si + 1.5 * c >= 15 and si + 2 * c < 30: return "loamy sand"
    if (c < 20 and s >= 52) or (c < 7 and si < 50 and s < 52): return "sandy loam"
    return "loam"


# Rawls et al. (1982)-style class-average Green-Ampt priors: Ks (m/s), psi_f (m), porosity.
# SCENARIO PRIORS with wide uncertainty; replace with local tests (D32). Values are literature class averages.
GA_PRIORS = {
    "sand": (5.8e-5, 0.049, 0.437), "loamy sand": (1.7e-5, 0.061, 0.437), "sandy loam": (7.2e-6, 0.110, 0.453),
    "loam": (3.7e-6, 0.089, 0.463), "silt loam": (1.9e-6, 0.167, 0.501), "sandy clay loam": (1.2e-6, 0.219, 0.398),
    "clay loam": (6.4e-7, 0.209, 0.464), "silty clay loam": (4.2e-7, 0.273, 0.471), "sandy clay": (3.3e-7, 0.239, 0.430),
    "silty clay": (2.5e-7, 0.292, 0.479), "clay": (1.7e-7, 0.316, 0.475), "silt": (1.9e-6, 0.167, 0.501),
}


def hydraulic_priors(texture, uncertainty_factor=10.0):
    """Returns Ks range (log-symmetric x/÷ factor), psi_f, theta_s with explicit 'scenario_prior' provenance."""
    ks, psi, por = GA_PRIORS[texture]
    return {"hydraulic_conductivity": {"min": ks / uncertainty_factor, "max": ks * uncertainty_factor},
            "suction_head": psi, "theta_s": por, "provenance": "scenario_prior_pedotransfer_class_average",
            "measured": False}
