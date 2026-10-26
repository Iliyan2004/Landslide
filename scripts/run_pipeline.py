#!/usr/bin/env python3
"""End-to-end demo on a SYNTHETIC DEM (no network): terrain -> M01 screening -> M08 stability -> manifest.

Usage:  cd backend && PYTHONPATH=. python ../scripts/run_pipeline.py [--out ../runs]
Replace `synthetic_dem()` with a real prepared COG window (rasterio) for actual studies.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from landslide.api import service as S                       # noqa: E402
from landslide.data.preprocessing import terrain as T        # noqa: E402
from landslide.models.susceptibility import legacy as L      # noqa: E402

AOI = {"type": "Polygon", "coordinates": [[[74.0, 35.0], [74.2, 35.0], [74.2, 35.2], [74.0, 35.2], [74.0, 35.0]]]}


def synthetic_dem(n=80, dx=30.0, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n]
    return 2500 + 18 * np.hypot(x - n / 2, y - n / 2) + 12 * np.sin(x / 6) * np.cos(y / 7) + rng.normal(0, 0.3, (n, n))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "runs")); a = ap.parse_args()
    aoi = S.validate_aoi(AOI); print("AOI:", aoi["analysis_crs"], f"{aoi['area_km2']:.0f} km2", aoi["warnings"])
    dem = synthetic_dem(); d = T.derive_all(dem, 30, 30)
    cfg = L.load_config(ROOT / "configs" / "legacy_susceptibility.yaml")
    lith = np.full(dem.shape, 3.0)                     # placeholder uniform lithology rank (no GLiM in demo)
    cls, _ = L.score(d["slope_pct"], lith, cfg)
    print("M01 class counts (Low..Very high):", [int((cls == k).sum()) for k in range(4)], "(demo: uniform lithology)")
    rain = [0.0] * 6 + [8.0] * 24 + [0.0] * 12
    spec = {"soil_depth": {"min": 1, "max": 3}, "effective_cohesion": {"min": 2000, "max": 8000}, "friction_angle": {"min": 28, "max": 38},
            "hydraulic_conductivity": {"min": 1e-6, "max": 1e-4}, "water_table": {"min": 2, "max": 6}}
    r = S.run_stability({"aoi_sha256": aoi["aoi_sha256"], "slope_deg": d["slope_deg"].tolist(), "rain_mm_step": rain, "params": spec,
                         "n": 30, "grid": {"crs": aoi["analysis_crs"], "resolution_m": 30}}, run_root=Path(a.out))
    print("run_id:", r["run_id"], "| validation:", r["manifest"]["validation_status"], "| warnings:", r["manifest"]["warnings"])
    print(json.dumps(r["summary"]["min_fs_p50_stats"]))


if __name__ == "__main__":
    main()
