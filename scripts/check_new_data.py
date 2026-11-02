#!/usr/bin/env python3
"""What the added borehole / soil / groundwater data (Datadownload/) can and cannot test.
 A. WoSIS measured clay and sand (Pakistan profiles, 5-60 cm) against the SoilGrids values the ground model reads at the same points.
 B. CSIRO borelogs and the depth-to-bedrock map: how deep the holes go versus the mapped depth to bedrock.
 C. BGS groundwater levels: depth to water table (m below ground) and its pre- to post-monsoon rise, against the water-table prior (2-10 m) and the fitted
    antecedent water-table response f_wt.
Writes docs/validation/new_data_checks.json."""
import json, zipfile
from pathlib import Path
import numpy as np, pandas as pd, rasterio
ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "Datadownload"; EXT = ROOT / "datasets/external/soilgrids"
out = {}
# ---- A
prof = pd.read_csv(D / "Pakistan_Subsurface_Data/pakistan_wosis_profiles.csv"); lay = pd.read_csv(D / "Pakistan_Subsurface_Data/pakistan_wosis_layers.csv")
z = zipfile.ZipFile(D / "Pakistan_Subsurface_Data/WoSIS_2023_December.zip"); ids = set(prof.profile_id); rows = {}
for prop in ("clay", "sand"):
    parts = []
    with z.open(f"WoSIS_2023_December/wosis_202312_{prop}.tsv") as f:
        for ch in pd.read_csv(f, sep="\t", chunksize=200000, low_memory=False):
            ch = ch[ch.profile_id.isin(ids)]
            if len(ch):
                parts.append(ch)
    rows[prop] = pd.concat(parts) if parts else pd.DataFrame()
val = {}
for prop in ("clay", "sand"):
    r = rows[prop]
    if r.empty:
        continue
    col = "value_avg"; r[col] = pd.to_numeric(r[col], errors="coerce"); r["upper_depth"] = pd.to_numeric(r.upper_depth, errors="coerce"); r["lower_depth"] = pd.to_numeric(r.lower_depth, errors="coerce"); r = r.drop(columns=[c for c in ("longitude", "latitude") if c in r.columns]).merge(prof[["profile_id", "longitude", "latitude"]], on="profile_id"); r = r[(r.upper_depth < 60) & (r.lower_depth > 5)]
    r = r.dropna(subset=[col]); g = r.groupby("profile_id").agg(v=(col, "mean"), lon=("longitude", "first"), lat=("latitude", "first")).reset_index()
    sg = []
    for d in ("5-15cm", "15-30cm", "30-60cm"):
        with rasterio.open(EXT / f"{prop}_{d}.tif") as s:
            vals = np.array([x[0] for x in s.sample(list(zip(g.lon, g.lat)))], float); vals[vals == s.nodata] = np.nan; sg.append(vals * 0.1)
    g["sg"] = np.nanmean(np.stack(sg), 0); g = g.dropna(subset=["sg", "v"]); e = g.sg - g.v
    val[prop] = {"profiles": int(len(g)), "bias_pct_points": float(e.mean()), "mae_pct_points": float(e.abs().mean()), "corr": float(np.corrcoef(g.sg, g.v)[0, 1]) if len(g) > 3 else None}
out["A_wosis_vs_soilgrids"] = {"profiles_in_pakistan": int(len(prof)), "north_of_31_5N": int((prof.latitude >= 31.5).sum()), **val}
# ---- B
b = pd.read_csv(D / "Pakistan_Open_Datasets/CSIRO_Indus_Borelogs/CSIRO-SDIP_Indus_Borelog_Database_v2__borelog_database.csv", low_memory=False)
h = b.groupby("CSIRO_bore_ID").agg(lon=("Lon", "first"), lat=("Lat", "first"), depth=("Depth_m", "max")).reset_index().dropna()
with rasterio.open(EXT / "bdticm_cm.tif") as s:
    v = np.array([x[0] for x in s.sample(list(zip(h.lon, h.lat)))], float); v[v == s.nodata] = np.nan
h["mapped_bedrock_m"] = v / 100.0; hh = h.dropna(subset=["mapped_bedrock_m"])
out["B_borelogs_vs_bedrock_map"] = {"holes": int(len(h)), "lat_range": [float(h.lat.min()), float(h.lat.max())], "median_hole_depth_m": float(h.depth.median()), "max_hole_depth_m": float(h.depth.max()),
    "median_mapped_depth_to_bedrock_m": float(hh.mapped_bedrock_m.median()), "share_holes_deeper_than_mapped_bedrock": float((hh.depth > hh.mapped_bedrock_m).mean()), "holes_north_of_33N": int((h.lat >= 33).sum())}
# ---- C
w = pd.read_csv(D / "Pakistan_Open_Datasets/BGS_Groundwater_Levels/India_Pakistan_WL_NGDC__Full_dataset.csv", low_memory=False)
w["wl"] = pd.to_numeric(w.WL_MBGL, errors="coerce"); w["date"] = pd.to_datetime(w.DATE, errors="coerce", dayfirst=False); w = w.dropna(subset=["wl", "date"])
w = w[(w.LONG > 60) & (w.LONG < 77.5) & (w.LAT > 23.5) & (w.LAT < 37) & (w.wl >= 0) & (w.wl < 100)]
recent = w[w.date >= "1990-01-01"]
out["C_groundwater"] = {"stations_in_pakistan": int(w.OW_ID.nunique()), "readings": int(len(w)), "months_present": sorted(int(m) for m in w.date.dt.month.unique()), "north_of_33N_stations": int(w[w.LAT >= 33].OW_ID.nunique()),
    "depth_to_water_m_quantiles_since_1990": {k: float(recent.wl.quantile(q)) for k, q in (("p10", .1), ("p50", .5), ("p90", .9))},
    "share_between_2_and_10m": float(((recent.wl >= 2) & (recent.wl <= 10)).mean()), "note": "every reading is the annual 1 October (post-monsoon) value: no pre-monsoon readings exist, so the seasonal water-table rise cannot be measured"}
# ---- D: depth of the northern WoSIS profiles and their lithic contacts
lay2 = lay.merge(prof[["profile_id", "latitude"]], on="profile_id"); g = lay2.groupby("profile_id").agg(depth=("lower_depth", "max"), lat=("latitude", "first"), names=("layer_name", lambda x: ",".join(map(str, x)))).reset_index()
g["lithic"] = g.names.str.contains(r"(?:^|,)(?:R|Cr|CR|2R|IIR|Rk)", regex=True); n = g[g.lat >= 31.5]
out["D_wosis_profile_depth"] = {"profiles_north_of_31_5N": int(len(n)), "median_described_depth_cm": float(n.depth.median()), "p90_described_depth_cm": float(n.depth.quantile(.9)),
    "profiles_with_a_rock_or_Cr_contact": int(n.lithic.sum()), "contact_depths_cm": sorted(float(x) for x in n[n.lithic].depth), "note": "profiles are described to the sampling depth (1-2 m), not to bedrock; only the few with a lithic contact bound the soil depth"}
(ROOT / "docs/validation/new_data_checks.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
