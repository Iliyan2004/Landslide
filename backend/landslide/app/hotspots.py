"""National rainfall hotspots from the per-cell indices cube (ERA5-Land 1980-2025): the highest individually recorded cells for a metric,
never averaged over an area, each with its district. A discovery aid for where landslide-triggering rain has been extreme."""
from __future__ import annotations
import numpy as np
from . import design_storm as DS, paths

METRICS = {"rx1day": "max 1-day rain (mm)", "rx5day": "max 5-day rain (mm)", "r95p": "very-wet-day total (mm)", "r99p": "extremely-wet-day total (mm)",
           "peakhr": "peak hourly rain (mm/h)", "sdii": "mean wet-day intensity (mm/day)", "r20mm": "days with >= 20 mm", "prcptot": "wet-day total (mm)", "trend": "trend of RX1day (mm per decade)"}
SEASONS = ("all", "monsoon", "pre", "post")


def top_cells(metric="rx1day", season="monsoon", n=15):
    import xarray as xr
    with xr.open_dataset(DS.ERA) as d:
        mask = d.country_mask.values > 0
        if metric == "trend":
            v = d[f"rx1day_{season}_slope"].values * 10.0
        else:
            s = list(d.season.values).index(season)
            A = d[metric].isel(season=s).values
            yrs = d.year.values
            A = A[yrs < 2026]
            v = np.nanmax(A, axis=0) if metric not in ("sdii", "prcptot", "r20mm") else np.nanmean(A, axis=0)
        lat, lon = d.latitude.values, d.longitude.values
    v = np.where(mask, v, np.nan)
    flat = np.argsort(-np.nan_to_num(v, nan=-1e9).ravel())[: n * 3]
    out, seen = [], []
    for i in flat:
        r, c = divmod(int(i), v.shape[1])
        if not np.isfinite(v[r, c]):
            continue
        if any(abs(r - r2) < 2 and abs(c - c2) < 2 for r2, c2 in seen):          # one hit per neighbourhood
            continue
        seen.append((r, c))
        out.append({"lat": float(lat[r]), "lon": float(lon[c]), "value": float(v[r, c])})
        if len(out) >= n:
            break
    names = _districts_for([(o["lon"], o["lat"]) for o in out])
    for o, nm in zip(out, names):
        o.update(nm)
    return {"metric": metric, "label": METRICS[metric], "season": season, "results": out,
            "note": "ERA5-Land 0.1 degree smooths convective bursts: values are lower bounds for short durations"}


def _districts_for(pts):
    try:
        import geopandas as gpd
        from shapely.geometry import Point
        g = gpd.read_file(paths.get("DISTRICTS_SHP"))[["name", "province", "geometry"]]
        res = []
        for lon, lat in pts:
            h = g[g.contains(Point(lon, lat))]
            res.append({"district": h.iloc[0]["name"], "province": h.iloc[0]["province"]} if len(h) else {"district": None, "province": None})
        return res
    except Exception:
        return [{"district": None, "province": None}] * len(pts)
