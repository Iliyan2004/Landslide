"""Landslide inventory -> a standardised event table with an explicit location-uncertainty radius, trigger class and event time.

Source: MERGED LANDSLIDE LAYERS/Landslide_inventories/Landslides_All.shp (392 points: NASA COOLR reports, the GLC rainfall catalogue and
the AJK/GB/KP local inventories). Positions are reports, mostly accurate to 1-50 km; there are no deposit polygons and almost no volumes.
Nothing here is invented: where a field is missing it is left missing and the record is excluded from analyses that need it."""
from __future__ import annotations
import os, re
import numpy as np
import pandas as pd
from ..app import paths

INV = os.path.join(paths.SHARE, "MERGED LANDSLIDE LAYERS", "Landslide_inventories", "Landslides_All.shp")
RAIN_WORDS = ("rain", "downpour", "monsoon", "cloudburst", "storm")
RADIUS_FROM_TEXT = [(r"verified", 0.5), (r"~?\s*1\s*km|approximate \(~1km\)", 1.0), (r"2\s*km", 2.0), (r"\b5\s*km", 5.0), (r"\b10\s*km", 10.0),
                    (r"\b25\s*km", 25.0), (r"\b50\s*km", 50.0), (r"\b100\s*km", 100.0), (r"coarse|unverified|regional|unknown|not reported|approximate", 25.0)]


def _radius(*texts):
    for t in texts:
        if not isinstance(t, str):
            continue
        s = t.lower()
        for pat, r in RADIUS_FROM_TEXT:
            if re.search(pat, s):
                return r
    return np.nan


def _trigger(*texts):
    s = " ".join(t.lower() for t in texts if isinstance(t, str))
    if "earthquake" in s:
        return "quake"
    if "glof" in s or "glacial" in s:
        return "glof"
    if any(w in s for w in RAIN_WORDS):
        return "rain"
    if "snow" in s:
        return "snow"
    if "construction" in s or "mining" in s:
        return "anthropogenic"
    return "unknown"


UGLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "datasets", "external", "uglc", "UGLC_point_tile_11_5.gpkg")
UGLC_TRIGGER = {"rainfall": "rain", "seismic": "quake", "anthropic": "anthropogenic"}


def load_uglc():
    """Pakistan records of the Unified Global Landslide Catalogue (Zenodo 18643456, CC-BY-NC 4.0): NASA COOLR and the Global Fatal Landslide
    Database. Positions carry a stated accuracy in metres (-99999 = unknown -> 25 km, flagged). Same table layout as load()'s inventory."""
    import geopandas as gpd
    if not os.path.exists(UGLC):
        return pd.DataFrame(columns=["lon", "lat", "date", "year_only", "trigger", "radius_km", "type", "fatalities", "dataset", "inv_id", "radius_assumed"])
    g = gpd.read_file(UGLC); g = g[g["COUNTRY"].astype(str).str.contains("Pakistan", case=False)]
    acc = pd.to_numeric(g["ACCURACY"], errors="coerce").where(lambda a: a > 0) / 1000.0
    d = pd.to_datetime(g["START DATE"].astype(str).str.replace("/", "-"), errors="coerce")
    e = pd.to_datetime(g["END DATE"].astype(str).str.replace("/", "-"), errors="coerce")
    d = d.where(d.notna() & (e.isna() | (e == d)))                       # day precision only; a multi-day range is not promoted to a day
    out = pd.DataFrame({"lon": g.geometry.x.values, "lat": g.geometry.y.values, "date": d.values, "year_only": np.nan,
                        "trigger": g["PHYSICAL FACTORS"].astype(str).str.split().str[0].map(UGLC_TRIGGER).fillna("unknown").values,
                        "radius_km": acc.values, "type": g["TYPE"].astype(str).str.lower().values,
                        "fatalities": pd.to_numeric(g["FATALITIES"], errors="coerce").where(lambda a: a >= 0).values,
                        "dataset": ("UGLC/" + g["OLD DATASET"].astype(str)).values, "inv_id": g["ID"].astype(str).values})
    out["radius_assumed"] = out["radius_km"].isna(); out["radius_km"] = out["radius_km"].fillna(25.0)
    return out


def load(extra=True):
    import geopandas as gpd
    g = gpd.read_file(INV)
    out = pd.DataFrame({"lon": g.geometry.x, "lat": g.geometry.y})
    d1 = pd.to_datetime(g["event_date"], errors="coerce")
    d2 = pd.to_datetime(g["Date"].astype(str).where(g["Date"].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}"), None), errors="coerce") if "Date" in g else pd.Series(pd.NaT, index=g.index)
    out["date"] = d1.fillna(d2)                    # DAY precision only: year-only / month-only / range strings are NOT promoted to a day
    out["year_only"] = g["Year_1"].where(out["date"].isna())
    out["trigger"] = [_trigger(a, b, c) for a, b, c in zip(g["cause"], g["Trigger"], g.get("Trigger_De", [None] * len(g)))]
    out["radius_km"] = [_radius(a, b) for a, b in zip(g["loc_acc"], g["Data_Quali"])]
    out["type"] = g["ls_type"].fillna(g["Landslide_"]).astype(str).str.lower()
    out["fatalities"] = pd.to_numeric(g["fatalities"], errors="coerce").fillna(pd.to_numeric(g["Deaths"], errors="coerce"))
    out["dataset"] = g["dataset"].fillna(g["Src_File"]).astype(str)
    out["inv_id"] = g["inv_id"].astype(str)
    # a report with no stated accuracy gets the conservative 25 km, and says so
    out["radius_assumed"] = out["radius_km"].isna()
    out["radius_km"] = out["radius_km"].fillna(25.0)
    if extra:
        out = pd.concat([out, load_uglc()], ignore_index=True)
    out = out[(out.lat.between(23.5, 37.2)) & (out.lon.between(60.5, 77.9))].reset_index(drop=True)
    return dedupe(out)


def dedupe(df, km=5.0, days=1):
    """Same place (<5 km) and same event time = one event; keep the most precisely located.
    Day-dated records match within +-1 day; undated records match only if they share the same stated year (or both lack one)."""
    df = df.sort_values("radius_km").reset_index(drop=True)
    keep = np.ones(len(df), bool)
    xy = np.c_[df.lon.values * 111.32 * np.cos(np.radians(df.lat.values)), df.lat.values * 110.57]
    date, yr = df.date.values, df.year_only.values
    for i in range(len(df)):
        if not keep[i]:
            continue
        near = np.hypot(*(xy - xy[i]).T) < km
        both_dated = ~pd.isna(date) & ~pd.isna(date[i])
        both_undated = pd.isna(date) & pd.isna(date[i])
        same_time = np.zeros(len(df), bool)
        same_time[both_dated] = np.abs((date[both_dated] - date[i]).astype("timedelta64[D]").astype(int)) <= days
        same_time[both_undated] = (pd.isna(yr[both_undated]) & pd.isna(yr[i])) | (yr[both_undated] == yr[i])
        dup = near & same_time
        dup[: i + 1] = False
        keep &= ~dup
    return df[keep].reset_index(drop=True)


def summary(df):
    return {"records": int(len(df)), "dated": int(df.date.notna().sum()), "by_trigger": df.trigger.value_counts().to_dict(),
            "radius_le_1km": int((df.radius_km <= 1).sum()), "radius_le_5km": int((df.radius_km <= 5).sum()), "radius_le_10km": int((df.radius_km <= 10).sum()),
            "radius_assumed": int(df.radius_assumed.sum()), "years": [int(df.date.dt.year.min()), int(df.date.dt.year.max())]}
