#!/usr/bin/env python3
"""Compare the platform's Green-Ampt wetting-front pore-pressure proxy with the Iverson (2000) transient pressure-head solution that TRIGRS uses
(Baum, Savage and Godt 2002, eq. 2, infinite-depth saturated form, constant rain, initial water table at, or d_off below, the slip surface). A water table far below the slip surface gives no failure in the saturated Iverson solution (psi stays negative), so the case is not informative.

This is NOT a run of the TRIGRS program: the program could not be compiled here (downloaded source; the build was not permitted), so the published analytic solution is implemented
directly and the two are evaluated on the same single soil column. Same inputs, same infinite-slope FS formula:
   Iverson:      psi(Z,t) = (Z - d) beta + 2 I (D1 t)^1/2 / Ks * ierfc( Z / (2 (D1 t)^1/2) ),  beta = cos^2(delta)  [d = water table depth, deep]
                 FS = tan(phi)/tan(delta) + (c - psi gamma_w tan(phi)) / (gamma_s Z sin(delta) cos(delta)),  psi >= 0 only
   Platform:     m = Zf / z (Green-Ampt front depth over slip depth), u = m gamma_w z cos^2(delta), same FS.
Reported: the time to FS <= 1 in each, and the failure/no-failure agreement, over a grid of slope, depth, conductivity and rain intensity. Writes docs/validation/iverson_vs_greenampt.json."""
import itertools, json, sys
from pathlib import Path
import numpy as np
from scipy.special import erfc
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.models.infiltration import green_ampt as GA                    # noqa: E402
from landslide.models.stability.infinite_slope import factor_of_safety        # noqa: E402
from landslide.units import GAMMA_W                                           # noqa: E402

GS = 19000.0; C = 4000.0; PHI = 34.0; PSIF = 0.11; THS = 0.45; THI = 0.25; D0_FACTOR = 100.0      # D0 = 100 Ks (a common first guess; TRIGRS needs the user's value)


def ierfc(x):
    return np.exp(-x * x) / np.sqrt(np.pi) - x * erfc(x)


def run_case(slope, z, ks, rain_mm_h, d_off, hours=48, dt=300.0):
    t = np.arange(1, int(hours * 3600 / dt) + 1) * dt; cb = np.cos(np.radians(slope)); I = min(rain_mm_h / 3.6e6, ks)
    D1 = D0_FACTOR * ks / cb ** 2; d = z + d_off                                                             # initial water table depth: at the slip surface (d_off 0) or d_off m below it
    root = np.sqrt(D1 * t)
    psi = np.clip((z - d) * cb ** 2 + 2.0 * I * root / ks * ierfc(z / (2.0 * root)), 0.0, z * cb ** 2)     # TRIGRS caps the head at full saturation (water table at the ground surface)
    fs_iv = factor_of_safety(slope, z, C, PHI, GS, u=psi * GAMMA_W)
    ga = GA.run(np.full(t.size, rain_mm_h * dt / 3600.0), dt, np.array([ks]), np.array([PSIF]), np.array([THS]), np.array([THI]), np.array([z]))
    fs_ga = factor_of_safety(slope, z, C, PHI, GS, m=ga["m"][:, 0])
    def first(fs):
        i = np.where(fs <= 1.0)[0]; return float(t[i[0]] / 3600.0) if i.size else None
    return first(fs_iv), first(fs_ga), float(fs_iv.min()), float(fs_ga.min())


def main():
    rows = []
    for d_off, slope, z, ks, rain in itertools.product((0.0, 0.5, 1.0), (25, 30, 35, 40, 45), (1.0, 2.0, 3.0), (1e-6, 1e-5, 1e-4), (5, 10, 25, 50, 100)):
        ti, tg, fi, fg = run_case(slope, z, ks, rain, d_off)
        rows.append({"water_table_below_slip_m": d_off, "slope": slope, "z": z, "ks": ks, "rain_mm_h": rain, "t_fail_iverson_h": ti, "t_fail_greenampt_h": tg, "min_fs_iverson": fi, "min_fs_greenampt": fg})
    both = [r for r in rows if r["t_fail_iverson_h"] is not None and r["t_fail_greenampt_h"] is not None]
    only_iv = [r for r in rows if r["t_fail_iverson_h"] is not None and r["t_fail_greenampt_h"] is None]
    only_ga = [r for r in rows if r["t_fail_iverson_h"] is None and r["t_fail_greenampt_h"] is not None]
    neither = len(rows) - len(both) - len(only_iv) - len(only_ga)
    by_wt = {str(w): {"cases": sum(r["water_table_below_slip_m"] == w for r in rows), "iverson_fails": sum(r["water_table_below_slip_m"] == w and r["t_fail_iverson_h"] is not None for r in rows),
                      "greenampt_fails": sum(r["water_table_below_slip_m"] == w and r["t_fail_greenampt_h"] is not None for r in rows)} for w in (0.0, 0.5, 1.0)}
    ratio = np.array([r["t_fail_greenampt_h"] / r["t_fail_iverson_h"] for r in both]) if both else np.array([])
    out = {"cases": len(rows), "both_fail": len(both), "only_iverson_fails": len(only_iv), "only_greenampt_fails": len(only_ga), "neither_fails": neither,
           "by_water_table_depth_below_slip": by_wt, "failure_agreement_pct": 100.0 * (len(both) + neither) / len(rows),
           "time_ratio_greenampt_over_iverson": ({"median": float(np.median(ratio)), "p10": float(np.percentile(ratio, 10)), "p90": float(np.percentile(ratio, 90))} if ratio.size else None),
           "inputs": {"unit_weight": GS, "cohesion_pa": C, "phi_deg": PHI, "psi_f_m": PSIF, "theta_s": THS, "theta_i": THI, "D0_over_Ks": D0_FACTOR, "hours": 48},
           "examples_only_iverson": only_iv[:6], "examples_only_greenampt": only_ga[:6], "rows": rows}
    (ROOT / "docs/validation/iverson_vs_greenampt.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
