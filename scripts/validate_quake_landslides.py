#!/usr/bin/env python3
"""Do shaking and Newmark displacement separate earthquake-triggered landslide REPORTS from other places in the same shaking field?

Events: inventory reports with trigger = quake and a day-resolved date, matched to the USGS ShakeMap of an earthquake within +-1 day whose grid
contains the point (largest magnitude if several). Controls: 10 random points per event inside the same ShakeMap grid and the northern study mask, with
the event's location-accuracy radius. Each point is scored over 100 random cells in its disc:
    pga_mean / pga_p90   ShakeMap PGA (the USGS product, includes its own site amplification)
    slope_mean / slope_p90
    newmark_p90          Jibson (2007) displacement from the dry yield coefficient of default slope strength and the ShakeMap PGA, 90th percentile
    newmark_bssa_p90     the same with the platform's model PGA (BSSA14 / BC Hydro with USGS Vs30) for the matched quake
AUC with a bootstrap over earthquakes. Reports are mostly from a few earthquakes (2015 Hindu Kush, 2016 Chitral, 2005 Kashmir), so n is small and the
interval wide. Writes docs/validation/quake_landslides.json."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, rasterio
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D, spatial as SP, stats as ST        # noqa: E402
from landslide.engine import trigger as TR, site as SITE                          # noqa: E402
from landslide.models.seismic import newmark as NM                                # noqa: E402

K, N_C = 100, 10
rng = np.random.default_rng(3)
idx = pd.read_csv(ROOT / "datasets/external/shakemap_index.csv", parse_dates=["date"])
import requests
ev_meta = {e["id"]: e for e in requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query", params=dict(format="geojson", minmagnitude=5.5, starttime="1973-01-01", producttype="shakemap", limit=2000, minlongitude=57, maxlongitude=81, minlatitude=20, maxlatitude=41), timeout=120).json()["features"]}
df = D.load(); df = df[(df.trigger == "quake") & df.date.notna()].reset_index(drop=True)
st = SP.Stack(layers=["slope"], with_ml=False); vs = rasterio.open(SITE.VS30)


def shake(eid):
    z = np.load(ROOT / f"datasets/external/shakemap/{eid}.npz"); p = z["pga"].astype("float32") / 100.0
    return z, p


def sample_pga(z, p, lon, lat):
    c = np.round((lon - z["lon0"]) / z["dlon"]).astype(int); r = np.round((lat - z["lat0"]) / z["dlat"]).astype(int)
    ok = (r >= 0) & (r < p.shape[0]) & (c >= 0) & (c < p.shape[1]); v = np.full(lon.shape, np.nan, "float32"); v[ok] = p[r[ok], c[ok]]; return v


rows = []
for qi, e in df.iterrows():
    cand = idx[(idx.date - e.date).abs() <= pd.Timedelta(days=1)].sort_values("mag", ascending=False)
    pick = None
    for _, c in cand.iterrows():
        if c.lon_min <= e.lon <= c.lon_max and c.lat_min <= e.lat <= c.lat_max:
            pick = c; break
    if pick is None:
        continue
    z, p = shake(pick.event_id); m = ev_meta[pick.event_id]; lo, la, dep = m["geometry"]["coordinates"]; mag = m["properties"]["mag"]
    clon, clat, _ = SP.random_controls(st, 400, np.array([e.radius_km]), rng)
    inb = (clon >= pick.lon_min) & (clon <= pick.lon_max) & (clat >= pick.lat_min) & (clat <= pick.lat_max)
    clon, clat = clon[inb][:N_C], clat[inb][:N_C]
    pts = [(e.lon, e.lat, 1)] + [(a, b, 0) for a, b in zip(clon, clat)]
    for lon0, lat0, y in pts:
        lo_, la_ = SP.disc_points(lon0, lat0, e.radius_km, K, rng); S = st.sample(lo_, la_, ["slope"]); sl = S.get("slope30", S["slope"])
        ok = S["_inside"] & np.isfinite(sl)
        if ok.sum() < 30:
            continue
        pga = sample_pga(z, p, lo_, la_); v = np.array([x[0] for x in vs.sample(list(zip(lo_, la_)))], "float32"); v = np.where(np.isfinite(v), v, 760.0)
        d_epi = np.hypot((lo_ - lo) * 111.32 * np.cos(np.radians(la)), (la_ - la) * 110.57)
        pga_m = TR.pga_model(mag, d_epi if dep > TR.SLAB_DEPTH_KM else np.maximum(d_epi - 0.5 * TR.rupture_length_km(mag), 0.0), v, "auto", dep)
        ky = NM.yield_coefficient(sl, 1.5, 3000.0, 30.0, 18000.0, m=0.0, c_root=1000.0)
        dn = NM.jibson2007_displacement_cm(ky, pga); dm = NM.jibson2007_displacement_cm(ky, pga_m)
        f = lambda a, q: float(np.nanpercentile(np.where(ok, a, np.nan), q))
        rows.append({"quake": e.name if False else pick.event_id, "y": y, "pga_mean": float(np.nanmean(np.where(ok, pga, np.nan))), "pga_p90": f(pga, 90), "slope_mean": float(np.nanmean(sl[ok])),
                     "slope_p90": f(sl, 90), "newmark_p90": f(np.nan_to_num(dn), 90), "newmark_bssa_p90": f(np.nan_to_num(dm), 90), "mag": mag})
X = pd.DataFrame(rows); y = X.y.values
res = {"n_events": int(y.sum()), "n_controls": int((1 - y).sum()), "earthquakes": int(X[X.y == 1].quake.nunique()), "events_per_quake": X[X.y == 1].quake.value_counts().to_dict(), "auc": {}}
for c in ("pga_mean", "pga_p90", "slope_mean", "slope_p90", "newmark_p90", "newmark_bssa_p90"):
    m = np.isfinite(X[c]); a, lo_, hi_ = ST.auc_ci(y[m], X[c].values[m], n_boot=500, group=X.quake.values[m]); res["auc"][c] = {"auc": a, "ci95": [lo_, hi_]}
res["note"] = "controls come from the SAME shaking field, so shaking only wins if reports sit where shaking is strongest; reports cluster at roads and villages (report-aware)"
(ROOT / "docs/validation/quake_landslides.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1)[:1800])
