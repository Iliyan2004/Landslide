"""Hourly rain, soil moisture and snowmelt for every Pakistan landslide report, plus matched no-landslide dates.

Source: ECMWF ERA5-Land hourly (Earth Engine), ~9 km, 1950-now. Hourly data replace the daily CHIRPS means for the
rainfall intensity-duration threshold and give the antecedent wetness and snowmelt that daily rain cannot.

For each report (NASA Global Landslide Catalog records in the Pakistan inventory) the window is the 30 days that end at
the close of the report day. For each report, 3 control windows are drawn at the same place and the same time of year in
other years, at least 20 days away from any report. Output: datasets/raw/gilgit/hourly_climate.npz
"""
import sys, time, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, ee

ROOT = Path(r"D:\Downloads\CMIP6")
INV = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/landslide_inventory/landslide_inventory.gpkg"
OUT = Path(r"D:\Downloads\datasets\raw\gilgit\hourly_climate.npz")
BANDS = ["total_precipitation_hourly", "snowmelt_hourly", "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2", "temperature_2m"]
NH = 30 * 24
NCTRL = 3
ee.Initialize(project="bamboo-storm-482319-s1")
col = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").select(BANDS)
rng = np.random.default_rng(7)

g = gpd.read_file(INV).to_crs(4326)
g["t"] = pd.to_datetime(g.event_date, unit="ms").dt.normalize()
g = g[(g.t >= "1981-01-01") & (g.t <= pd.Timestamp.today() - pd.Timedelta(days=10))].reset_index(drop=True)
rain_re = "rain|downpour|monsoon|flood|snow|storm|unknown|earthquake|mining"
print("reports used", len(g))

jobs = []                                    # (id, kind, lon, lat, end_time)
for i, w in g.iterrows():
    end = w.t + pd.Timedelta(days=1)
    jobs.append((i, 1, w.geometry.x, w.geometry.y, end))
    others = g.t.values
    n = 0
    while n < NCTRL:
        yr = int(rng.integers(2001, 2025)); doy = (w.t.dayofyear + int(rng.integers(-25, 26)))
        t = pd.Timestamp(year=yr, month=1, day=1) + pd.Timedelta(days=int(np.clip(doy, 1, 365)) - 1)
        if t > pd.Timestamp.today() - pd.Timedelta(days=10) or np.min(np.abs((others - np.datetime64(t)) / np.timedelta64(1, "D"))) < 20: continue
        jobs.append((i, 0, w.geometry.x, w.geometry.y, t + pd.Timedelta(days=1))); n += 1
print("windows", len(jobs))


def fetch(job):
    i, kind, lon, lat, end = job
    pt = ee.Geometry.Point([lon, lat])
    c = col.filterDate((end - pd.Timedelta(hours=NH)).strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    for k in range(5):
        try:
            rows = c.getRegion(pt, 11132).getInfo()
            break
        except Exception as e:
            time.sleep(3 + 3 * k); rows = None
    if rows is None: return job, None
    hdr = rows[0]; idx = [hdr.index(b) for b in BANDS]
    a = np.array([[r[j] if r[j] is not None else np.nan for j in idx] for r in rows[1:]], np.float32)
    return job, a[-NH:]


res = []
t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for n, (job, a) in enumerate(ex.map(fetch, jobs)):
        res.append((job, a))
        if n % 50 == 0: print(n, len(jobs), round(time.time() - t0), "s", flush=True)
ok = [(j, a) for j, a in res if a is not None and a.shape[0] == NH]
print("fetched", len(ok), "of", len(jobs))
np.savez_compressed(OUT, X=np.stack([a for _, a in ok]), rec=np.array([j[0] for j, _ in ok]), kind=np.array([j[1] for j, _ in ok]),
                    lon=np.array([j[2] for j, _ in ok]), lat=np.array([j[3] for j, _ in ok]), end=np.array([str(j[4]) for j, _ in ok]), bands=np.array(BANDS))
print("wrote", OUT)
