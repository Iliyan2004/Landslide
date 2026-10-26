"""Tier D (M17-M20): RUSLE, Shields, Meyer-Peter & Muller, suspended load, sediment budget, blockage screening.

Keep distinct: gross hillslope erosion (RUSLE) != channel capacity (MPM) != measured SSC != delivered sediment.
"""
from __future__ import annotations
import numpy as np
from ...units import G, RHO_W

# C factors by ESA WorldCover class — EDITABLE SCENARIO TABLE, to be replaced with literature/local values.
C_FACTOR_SCENARIO = {10: 0.003, 20: 0.05, 30: 0.05, 40: 0.2, 50: 0.01, 60: 0.5, 70: 0.0, 80: 0.0, 90: 0.0, 95: 0.0, 100: 0.05}
P_UNKNOWN = 1.0   # = "unknown conservation practice" — an ASSUMPTION; labelled in output


def rusle(R, K, LS, C, P=P_UNKNOWN):
    """A = R K LS C P  (t/ha/yr when factors in compatible units). Annual long-term screening only."""
    A = R * K * LS * C * P
    return {"A_t_ha_yr": A, "assumptions": (["P=1 (unknown practice)"] if np.all(np.asarray(P) == 1.0) else []),
            "meaning": "gross hillslope sheet/rill potential, NOT landslide or debris-flow sediment"}


def c_from_worldcover(landcover, table=C_FACTOR_SCENARIO):
    out = np.full(np.asarray(landcover).shape, np.nan)
    for k, v in table.items():
        out[np.asarray(landcover) == k] = v
    return out


def bed_shear_uniform(h, S_f):
    """tau_b = rho_w g R_h S_f; for wide channels R_h ~ h."""
    return RHO_W * G * np.asarray(h) * np.asarray(S_f)


def bed_shear_manning(n, V, h):
    """tau_b = rho_w g n^2 V^2 / h^(1/3) (valid on wet cells only: h>0)."""
    h = np.asarray(h, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        tau = RHO_W * G * np.asarray(n) ** 2 * np.asarray(V) ** 2 / h ** (1 / 3)
    return np.where(h > 0, tau, np.nan)


def shields(tau_b, d50, rho_s=2650.0):
    return np.asarray(tau_b) / ((rho_s - RHO_W) * G * np.asarray(d50))


def mpm_bedload_per_width(tau_b, d50, rho_s=2650.0, theta_c=0.047):
    """q_b = 8 (theta-theta_c)^1.5 sqrt((s-1) g d50^3)  [m^2/s, volumetric per unit width]. theta<=theta_c -> 0."""
    s = rho_s / RHO_W
    theta = shields(tau_b, d50, rho_s)
    q = 8.0 * np.maximum(theta - theta_c, 0.0) ** 1.5 * np.sqrt((s - 1) * G * np.asarray(d50) ** 3)
    return np.where(np.isfinite(theta), q, np.nan)


def total_bedload(q_b, active_width_m):
    """Q_b = q_b B  [m^3/s]. REQUIRES width; per-width values must never be reported as volumes."""
    if active_width_m is None:
        raise ValueError("active width required to convert per-width capacity to discharge")
    return np.asarray(q_b) * active_width_m


def suspended_load(Q, a=None, b=None, ssc_kg_m3=None):
    """Qs = Q * Cs (kg/s). Cs observed, or a Q^b rating (site-calibrated ONLY; no national defaults)."""
    if ssc_kg_m3 is None:
        if a is None or b is None:
            raise ValueError("provide observed SSC or a site-calibrated rating (a,b)")
        ssc_kg_m3 = a * np.asarray(Q) ** b
    return np.asarray(Q) * ssc_kg_m3


def sediment_budget(inputs_from_slides, hillslope, bank, exported, deposition):
    """dS = in_slides + hillslope + bank - exported - deposition (consistent mass units). Returns dS and closure inputs."""
    dS = inputs_from_slides + hillslope + bank - exported - deposition
    return {"delta_storage": dS, "terms": dict(slides=inputs_from_slides, hillslope=hillslope, bank=bank,
                                               exported=exported, deposition=deposition)}


def exner_step(zb, q_s_div, dt, porosity=0.4):
    """(1-lambda_p) dz/dt + div(q_s) = 0. Disabled in the basic tier (methodology §5.5): requires coupling tests."""
    raise NotImplementedError("Dynamic bed update disabled until coupled stability tests are implemented")


def blockage_screen(runout_mask, channel_mask, cell_size_m, channel_width_m, deposit_thickness_m=None):
    """Candidate landslide-dam cells: runout ∩ channel. A POSSIBLE blockage, not a breach-hydrograph prediction."""
    hit = runout_mask & channel_mask
    n = int(hit.sum())
    return {"candidate_cells": hit, "n_cells": n,
            "affected_channel_length_m": n * cell_size_m,
            "width_fraction_blocked_proxy": (min(1.0, n * cell_size_m / channel_width_m) if channel_width_m else None),
            "status": "screening_not_breach_simulation"}
