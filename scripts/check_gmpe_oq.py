#!/usr/bin/env python3
"""Cross-check the hand-coded ground-motion models (engine/trigger.py) against GEM OpenQuake hazardlib.
Run with an interpreter that has openquake.hazardlib (e.g. ~/oq-env/bin/python). OpenQuake is AGPL: it is used HERE ONLY, as a validation oracle, and is never imported by the shipped backend.
Compares median PGA (g) for BSSA14 (Boore et al. 2014; strike-slip, because OpenQuake has no 'unspecified' option - the platform default 'U' term differs by e1-e0 = +0.0383 ln units, 3.9 %) and the BC Hydro intraslab model (Abrahamson et al. 2016, forearc, no regional adjustment)
over a grid of magnitude, distance, Vs30 (and depth for the slab model). Writes docs/validation/gmpe_oq_check.json."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.engine import trigger as TR                                  # noqa: E402
from openquake.hazardlib import contexts, valid                             # noqa: E402
from openquake.hazardlib.imt import PGA                                     # noqa: E402


def oq_mean_pga(gsim_name, mag, dists, vs30, depth=None, kind="crust", **extra):
    gsim = valid.gsim(gsim_name)
    cm = contexts.simple_cmaker([gsim], ["PGA"])
    n = len(dists); d = np.asarray(dists, float)
    ctx = contexts.RuptureContext()
    ctx.sids = np.arange(n); ctx.mag = mag; ctx.rake = 0.0; ctx.dip = 90.0 if kind == "crust" else 45.0
    ctx.vs30 = np.full(n, float(vs30)); ctx.vs30measured = np.zeros(n, bool); ctx.z1pt0 = np.full(n, np.nan); ctx.z2pt5 = np.full(n, np.nan)
    if kind == "crust":
        ctx.rjb = d; ctx.rrup = np.sqrt(d ** 2 + 36.0) if False else d; ctx.rx = d; ctx.ry0 = np.zeros(n); ctx.ztor = 0.0; ctx.hypo_depth = 10.0; ctx.width = 10.0
    else:
        h = float(depth); ctx.hypo_depth = h; ctx.rhypo = np.sqrt(d ** 2 + h ** 2); ctx.rrup = ctx.rhypo; ctx.rjb = d; ctx.rvolc = np.zeros(n); ctx.backarc = np.zeros(n, bool); ctx.ztor = h; ctx.width = 1.0
    ctx.occurrence_rate = 1e-3
    for k, v in extra.items():
        setattr(ctx, k, v)
    mean = np.asarray(cm.get_mean_stds([ctx])[0]).reshape(-1, n)[0]         # ln(g) of the first IMT, one value per site
    return np.exp(mean)


def stats(a, b):
    r = np.log(a) - np.log(b)
    return {"n": int(r.size), "mean_ln_diff": float(r.mean()), "max_abs_ln_diff": float(np.abs(r).max()), "max_abs_pct": float(100 * np.abs(np.exp(r) - 1).max())}


def main():
    out = {"note": "ln(platform) - ln(OpenQuake); 0 means identical", "bssa14": {}, "bchydro_slab": {}}
    D = np.array([1, 3, 5, 10, 20, 40, 80, 150, 250, 350], float)
    for vs in (200, 400, 760, 1000):
        mine, oq = [], []
        for M in (5.5, 6.0, 6.5, 7.0, 7.5, 8.0):
            mine.append(TR.bssa14_pga_g(M, D, vs, mech="SS")); oq.append(oq_mean_pga("BooreEtAl2014", M, D, vs, kind="crust", rake=0.0))
        out["bssa14"][f"vs30_{vs}"] = stats(np.concatenate(mine), np.concatenate(oq))
    Ds = np.array([60, 100, 150, 200, 300, 400], float)
    for depth in (60, 120, 200):
        for vs in (400, 760):
            mine, oq = [], []
            for M in (6.0, 6.5, 7.0, 7.5, 8.0):
                mine.append(TR.bchydro_slab_pga_g(M, Ds, depth, vs))
                oq.append(oq_mean_pga("AbrahamsonEtAl2015SSlab", M, Ds, vs, depth=depth, kind="slab"))
            out["bchydro_slab"][f"depth_{depth}_vs30_{vs}"] = stats(np.concatenate(mine), np.concatenate(oq))
    (ROOT / "docs/validation/gmpe_oq_check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
