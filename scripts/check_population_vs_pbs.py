#!/usr/bin/env python3
"""Compare the population raster (WorldPop 2025, constrained, 90 m) with the 2023 census district totals (PBS) for the districts the raster covers.
Only districts whose polygon lies wholly inside the raster's footprint (and has a census row) are used; the raster ends near 31 N, so the south is not covered.
Ratio = raster sum / census total. The raster is a 2025 projection and the census is 2023, so a ratio near 1.05 is expected from growth alone.
Writes docs/validation/population_vs_pbs.json."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.mask import mask
from shapely.geometry import box
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.app import paths      # noqa: E402

D = ROOT / "datasets/external/pbs"
pbs = pd.read_csv(D / "district_population.csv"); pbs["key"] = pbs.name.str.lower().str.strip()
g = gpd.read_file(D / "district_shp/District_Boundary.shp"); g["key"] = g.name.str.lower().str.strip()
src = rasterio.open(paths.get("POPULATION")); g = g.to_crs(src.crs); foot = box(*src.bounds)
valid = src.read(1, masked=False); fraction_with_data = None
rows = []
for _, r in g.iterrows():
    if r.key not in set(pbs.key):
        continue
    try:
        a, _t = mask(src, [r.geometry], crop=True, nodata=np.nan, filled=True); a = a[0]; tot = float(np.nansum(np.where(a > 0, a, 0))); covered = float(np.isfinite(a).mean())
    except Exception:
        continue
    rows.append({"district": r["name"], "province": r["province"], "raster": tot, "census": float(pbs[pbs.key == r.key].Pop_2023_Total.iloc[0]), "inside_footprint": bool(foot.contains(r.geometry))})
d = pd.DataFrame(rows); d["ratio"] = d.raster / d.census; full = d[d.inside_footprint & (d.raster > 0)]
out = {"districts_with_census": int(len(pbs)), "districts_checked": int(len(full)), "raster_total_M": float(full.raster.sum() / 1e6), "census_total_M": float(full.census.sum() / 1e6),
       "ratio_total": float(full.raster.sum() / full.census.sum()), "ratio_median": float(full.ratio.median()), "ratio_p25_p75": [float(full.ratio.quantile(.25)), float(full.ratio.quantile(.75))],
       "share_within_20pct": float(((full.ratio > 0.8) & (full.ratio < 1.2)).mean()), "worst": full.assign(dev=np.abs(np.log(full.ratio))).sort_values("dev", ascending=False).head(6)[["district", "raster", "census", "ratio"]].to_dict("records"),
       "not_covered_by_raster": int((~d.inside_footprint).sum())}
(ROOT / "docs/validation/population_vs_pbs.json").write_text(json.dumps(out, indent=1, default=float)); print(json.dumps(out, indent=1, default=float))
