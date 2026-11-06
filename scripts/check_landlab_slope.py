#!/usr/bin/env python3
"""Cross-check the platform's infinite-slope factor of safety against Landlab's LandslideProbability (an independent implementation, SINMAP form of Pack et al. 1998).
Run with an interpreter that has landlab (e.g. ~/qa-env/bin/python).

Same inputs, same sampling: for 300 random cells (slope, soil depth, cohesion, friction, wetness) Landlab runs its Monte Carlo (triangular distributions on cohesion, friction,
thickness, conductivity). The platform's factor_of_safety() is then evaluated on Landlab's OWN samples (landlab keeps the last draw only, so the distributions are re-drawn here with the
same rules and a fixed seed) and the failure probabilities are compared. Two known differences are reported separately:
  (1) Landlab fixes water/soil unit weight = 0.5 and puts cohesion as C/(h rho g)/sin(b); the standard form divides by sin(b) cos(b) (SINMAP simplification);
  (2) Landlab caps relative wetness at 1.
The platform form is evaluated with gamma = 2 gamma_w so both use the same 0.5 ratio.
Writes docs/validation/landlab_check.json."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landlab import RasterModelGrid                                           # noqa: E402
from landlab.components import LandslideProbability                           # noqa: E402
from landslide.models.stability.infinite_slope import factor_of_safety        # noqa: E402
from landslide.units import GAMMA_W                                           # noqa: E402


def main(n_cells=300, n_iter=2000, seed=7):
    rng = np.random.default_rng(seed)
    slope_deg = rng.uniform(15, 50, n_cells); tan_b = np.tan(np.radians(slope_deg))
    hs = rng.uniform(0.5, 3.0, n_cells); phi = rng.uniform(25, 40, n_cells); cmode = rng.uniform(1000, 12000, n_cells)
    ksat = rng.uniform(1e-5, 1e-4, n_cells); area = rng.uniform(5, 150, n_cells); rho = 2000.0
    R = 0.012                                                                    # recharge, m/day (Landlab takes mm/day: R*1000)
    ksat = ksat * 86400.0
    g = RasterModelGrid((1 + n_cells + 1, 3), xy_spacing=10.0)                  # a column of core nodes in the middle
    core = g.core_nodes
    def put(name, v):
        a = np.zeros(g.number_of_nodes); a[core] = v; g.add_field(name, a, at="node", clobber=True)
    put("topographic__slope", tan_b); put("topographic__specific_contributing_area", area); put("soil__thickness", hs)
    put("soil__internal_friction_angle", phi); put("soil__mode_total_cohesion", cmode); put("soil__minimum_total_cohesion", cmode * 0.7); put("soil__maximum_total_cohesion", cmode * 1.3)
    put("soil__density", np.full(n_cells, rho)); put("soil__transmissivity", ksat * hs); put("soil__saturated_hydraulic_conductivity", ksat)
    np.random.seed(seed)
    ls = LandslideProbability(g, number_of_iterations=n_iter, groundwater__recharge_distribution="uniform", groundwater__recharge_min_value=R * 500.0,
                              groundwater__recharge_max_value=R * 1500.0, seed=seed)
    ls.calculate_landslide_probability()
    p_ll = g.at_node["landslide__probability_of_failure"][core]
    # Platform: same Monte Carlo rules and the same wetness, evaluated with the platform's FS function (gamma = 2 gamma_w gives water/soil ratio 0.5).
    rs = np.random.default_rng(seed + 1); gam = 2.0 * GAMMA_W
    def tri(lo, mode, hi): return rs.triangular(lo, mode, hi, size=(n_iter,) + lo.shape)
    C = tri(cmode * 0.7, cmode, cmode * 1.3); PH = tri(phi * 0.82, phi, phi * 1.32); H = np.maximum(tri(hs * 0.7, hs, hs * 1.1), 0.005)
    K = tri(ksat * 0.7, ksat, ksat * 1.1); Re = np.broadcast_to(rs.uniform(R * 0.5, R * 1.5, size=(n_iter, 1)), (n_iter, n_cells))   # Landlab draws one recharge series (mm) shared by all cells
    W = np.minimum(Re / (K * H) * area / np.sin(np.arctan(tan_b)), 1.0)
    b = np.degrees(np.arctan(tan_b))
    fs_std = factor_of_safety(b, H, C, PH, gam, m=W)                              # standard form, platform code
    # SINMAP form (cohesion term without 1/cos b), as Landlab writes it, evaluated with the same samples:
    sb, cb = np.sin(np.radians(b)), np.cos(np.radians(b))
    fs_sinmap = (C / (H * rho * 9.81)) / sb + cb * np.tan(np.radians(PH)) * (1 - 0.5 * W) / sb
    p_std = (fs_std <= 1).mean(0); p_sin = (fs_sinmap <= 1).mean(0)
    def cmp(a, b_): return {"max_abs_diff": float(np.abs(a - b_).max()), "mean_abs_diff": float(np.abs(a - b_).mean()), "correlation": float(np.corrcoef(a, b_)[0, 1])}
    out = {"cells": n_cells, "iterations": n_iter, "seed": seed, "mean_p_landlab": float(p_ll.mean()), "mean_p_platform_standard": float(p_std.mean()), "mean_p_sinmap_form_same_samples": float(p_sin.mean()),
           "landlab_vs_sinmap_form_same_samples": cmp(p_ll, p_sin), "landlab_vs_platform_standard_form": cmp(p_ll, p_std),
           "note": "Row 1 differs only by random draws (Monte Carlo noise); row 2 adds the cos(b) in the cohesion term and the exact unit-weight treatment, so it is the real difference between the two formulas."}
    (ROOT / "docs/validation/landlab_check.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
