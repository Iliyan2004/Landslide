#!/usr/bin/env python3
"""Check the modelled failure depth against the landslide area-volume scaling V = alpha A^gamma (Larsen, Montgomery & Korup 2010, Nature Geoscience 3, 247-251,
doi:10.1038/ngeo776; soil landslides alpha = 0.146, gamma = 1.332 with A in m2 and V in m3, as cited; I could not re-read the paper when writing this, so
confirm the coefficients before quoting). For every connected cluster of failing cells in saved runs: area A, volume V = sum(cell area x soil depth z), and the depth
the relation implies for that area, alpha A^(gamma-1). Ratio = modelled depth / implied depth; the relation itself scatters by about a factor of 2-3.
Usage: check_volume_area.py <run_id> [<run_id> ...]   Writes docs/validation/volume_area.json."""
import json, sys
from pathlib import Path
import numpy as np
from scipy import ndimage
ROOT = Path(__file__).resolve().parents[1]
ALPHA, GAMMA = 0.146, 1.332
rows = []
for rid in sys.argv[1:]:
    z = np.load(ROOT / "runs" / rid / "arrays.npz"); man = json.load(open(ROOT / "runs" / rid / "manifest.json")); res = man["grid"]["resolution_m"]
    fail = np.isfinite(z["t_fail_h"]); lab, n = ndimage.label(fail, structure=np.ones((3, 3)))
    if n == 0:
        continue
    idx = np.arange(1, n + 1); cells = ndimage.sum(fail, lab, idx); depth = ndimage.mean(np.nan_to_num(z["z"]), lab, idx)
    for c, d in zip(cells, depth):
        A = c * res * res; V = A * d
        rows.append({"run": rid, "area_m2": float(A), "mean_depth_m": float(d), "volume_m3": float(V), "implied_depth_m": float(ALPHA * A ** (GAMMA - 1)), "ratio": float(d / (ALPHA * A ** (GAMMA - 1)))})
r = np.array([x["ratio"] for x in rows]); A = np.array([x["area_m2"] for x in rows])
out = {"relation": "V = 0.146 A^1.332 (Larsen et al. 2010, soil landslides)", "clusters": len(rows), "median_ratio": float(np.median(r)), "p10_ratio": float(np.percentile(r, 10)), "p90_ratio": float(np.percentile(r, 90)),
       "by_area": {lab: {"n": int(m.sum()), "median_ratio": float(np.median(r[m]))} for lab, m in (("<2,000 m2", A < 2000), ("2,000-20,000 m2", (A >= 2000) & (A < 20000)), (">20,000 m2", A >= 20000)) if m.sum() > 0},
       "total_volume_modelled_m3": float(sum(x["volume_m3"] for x in rows)), "total_volume_implied_m3": float(sum(x["area_m2"] * x["implied_depth_m"] for x in rows))}
(ROOT / "docs/validation/volume_area.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
