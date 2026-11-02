"""Rainfall sources for landslide triggering: design storm, uploaded CSV, Open-Meteo forecast/recent, ERA5 hourly
hindcast (1980-2026, server zarr) and CHIRPS daily. All return hourly (or finer) rain depth series with provenance.
Plus global intensity-duration thresholds used for the watch tier (labelled experimental, not validated here)."""
from __future__ import annotations
import csv, io, os
from datetime import datetime, timedelta
import numpy as np
import requests
from . import paths

ERA5_TP = os.path.join(paths.SHARE, "0. ERA-5 Variables", "tp_zarr_time_opt")
CHIRPS_DIR = os.path.join(paths.SHARE, "0. CHIRPS", "tiff_by_year")
_OM = "https://api.open-meteo.com/v1/forecast"
_OM_ARCH = "https://archive-api.open-meteo.com/v1/archive"


def triangular(peak_mm_h, dur_h, dt_min=15):
    """SAILAB-style triangular hyetograph peaking at mid-storm. Returns (t_h at step ends, rate mm/h)."""
    dt = dt_min / 60.0
    t = np.arange(dt, dur_h + 1e-9, dt)
    mid = dur_h / 2.0
    rate = np.where(t - dt / 2 <= mid, peak_mm_h * (t - dt / 2) / mid, peak_mm_h * (1 - (t - dt / 2 - mid) / (dur_h - mid)))
    return t, np.maximum(rate, 0.0)


def constant(rate_mm_h, dur_h, dt_min=15):
    dt = dt_min / 60.0
    t = np.arange(dt, dur_h + 1e-9, dt)
    return t, np.full(t.shape, float(rate_mm_h))


def series_payload(times_h, rate_mm_h, source, start_iso=None, extra=None):
    th, r = np.asarray(times_h, float), np.asarray(rate_mm_h, float)
    return {"source": source, "start_iso": start_iso, "times_h": th.tolist(), "rate_mm_h": np.round(r, 3).tolist(),
            "total_mm": float(np.sum(r * np.gradient(th) if len(th) > 1 else r)), "peak_mm_h": float(r.max() if r.size else 0),
            "duration_h": float(th[-1] if th.size else 0), **(extra or {})}


def to_step_depths(times_h, rate_mm_h, dt_s):
    """Resample a (time, rate) series to uniform steps of dt_s; returns depth mm per step (mass-preserving)."""
    th, r = np.asarray(times_h, float), np.asarray(rate_mm_h, float)
    edges_in = np.concatenate([[0.0], th])
    depth_in = np.diff(edges_in) * r                   # mm per input interval
    cum = np.concatenate([[0.0], np.cumsum(depth_in)])
    n = int(np.ceil(th[-1] * 3600 / dt_s))
    e = np.arange(n + 1) * dt_s / 3600.0
    return np.maximum(np.diff(np.interp(e, edges_in, cum)), 0.0)


def parse_csv(text, unit="mm_per_hour"):
    """Flexible CSV: a time column (ISO / date-time or elapsed hours) and a rainfall column. unit: mm_per_hour | mm_per_interval."""
    rows = list(csv.reader(io.StringIO(text.strip())))
    if len(rows) < 3:
        raise ValueError("CSV needs a header and at least 2 rows")
    head = [h.strip().lower() for h in rows[0]]
    ti = next((i for i, h in enumerate(head) if any(k in h for k in ("time", "date", "hour", "stamp"))), 0)
    ri = next((i for i, h in enumerate(head) if any(k in h for k in ("rain", "precip", "mm", "prcp"))), 1 if len(head) > 1 else 0)
    ts, vs = [], []
    for r in rows[1:]:
        if len(r) <= max(ti, ri) or not r[ri].strip():
            continue
        ts.append(r[ti].strip()); vs.append(float(r[ri]))
    try:
        t = np.array([datetime.fromisoformat(x.replace("Z", "+00:00").replace(" ", "T")) for x in ts])
        hours = np.array([(x - t[0]).total_seconds() / 3600.0 for x in t]); start = t[0].isoformat()
    except ValueError:
        hours = np.array([float(x) for x in ts]); hours = hours - hours[0]; start = None
    v = np.array(vs)
    if np.any(v < 0) or not np.all(np.isfinite(v)):
        raise ValueError("rainfall has negative or non-numeric values")
    if np.any(np.diff(hours) <= 0):
        raise ValueError("timestamps must be strictly increasing")
    dt = np.median(np.diff(hours))
    rate = v / dt if unit == "mm_per_interval" else v
    t_end = hours + dt                                  # each value covers the interval ending dt after its timestamp
    return series_payload(t_end - hours[0], rate, f"uploaded CSV ({os.path.basename('upload')})", start)


def _open_meteo_raw(lat, lon, past_days=3, forecast_days=3):
    r = requests.get(_OM, params={"latitude": lat, "longitude": lon, "hourly": "precipitation", "past_days": past_days,
                                  "forecast_days": forecast_days, "timezone": "UTC"}, timeout=25)
    r.raise_for_status()
    h = r.json()["hourly"]
    p = np.nan_to_num(np.array(h["precipitation"], float))
    t = np.arange(1, len(p) + 1, dtype=float)
    now_idx = int(past_days * 24)
    return series_payload(t, p, "Open-Meteo (recent observed + forecast)", h["time"][0] + ":00Z",
                          {"now_hour_index": now_idx, "past_mm": float(p[:now_idx].sum()), "forecast_mm": float(p[now_idx:].sum()),
                           "times_iso": h["time"]})


OM_CACHE_MAX_AGE_H = 6.0


def open_meteo(lat, lon, past_days=3, forecast_days=3):
    """Live rain from Open-Meteo with recovery (the data-interruption agent, app/agents.py): up to 3 tries with back-off, then the last good response for the same
    point (rounded to 0.1 degree) if it is under OM_CACHE_MAX_AGE_H old, marked 'stale_cache' and 'data_age_h' so callers and the page can say so. Otherwise raises."""
    import time as _t
    from . import agents
    err = None
    for k in range(3):
        try:
            out = _open_meteo_raw(lat, lon, past_days, forecast_days)
            agents.cache_put(("om", round(lat, 1), round(lon, 1), past_days, forecast_days), out)
            agents.note_source("open-meteo", True)
            return out
        except Exception as e:
            err = e; _t.sleep(1.5 * (k + 1))
    agents.note_source("open-meteo", False, str(err)[:120])
    hit = agents.cache_get(("om", round(lat, 1), round(lon, 1), past_days, forecast_days), OM_CACHE_MAX_AGE_H)
    if hit is not None:
        data, age_h = hit
        data = dict(data); data.update(stale_cache=True, data_age_h=round(age_h, 2), source=data["source"] + f" [CACHED {age_h:.1f} h ago: live feed down]")
        return data
    raise err


def era5_event(lat, lon, start, end):
    import xarray as xr
    d = xr.open_zarr(ERA5_TP)
    s = d.tp.sel(latitude=lat, longitude=lon, method="nearest").sel(time=slice(start, end)).load()
    if s.size == 0:
        raise ValueError(f"ERA5 store covers {str(d.time.values[0])[:10]} to {str(d.time.values[-1])[:10]}; nothing in {start}..{end}")
    p = np.maximum(s.values.astype(float), 0)
    return series_payload(np.arange(1, len(p) + 1, dtype=float), p, "ERA5-Land hourly total precipitation (server zarr, ~9 km)",
                          str(s.time.values[0])[:19] + "Z", {"grid_lat": float(s.latitude), "grid_lon": float(s.longitude)})


def era5_antecedent(lat, lon, start, days=30):
    """Daily ERA5-Land totals (mm) for the `days` days before `start`, oldest first (the last entry is the day before the storm)."""
    import xarray as xr, pandas as pd
    d = xr.open_zarr(ERA5_TP)
    t1 = pd.Timestamp(start).floor("D"); t0 = t1 - pd.Timedelta(days=days)
    s = d.tp.sel(latitude=lat, longitude=lon, method="nearest").sel(time=slice(t0, t1 - pd.Timedelta(hours=1))).load()
    if s.size < 24 * days * 0.9:
        raise ValueError(f"ERA5 has no {days}-day history before {start}")
    return np.maximum(s.values.astype(float), 0).reshape(-1)[: 24 * days].reshape(days, 24).sum(1).tolist()


def era5_scale_field(grid, series, ref_lat, ref_lon, lo=0.3, hi=3.0):
    """Per-cell rain multiplier for the analysis grid: the storm total of the ERA5-Land cell under each analysis cell divided by the total at the cell the
    series was taken from (ref_lat, ref_lon). Needs series['start_iso'] and its hourly length. Returns (ny, nx) float32 or None if the store lacks the window."""
    import xarray as xr, pandas as pd
    from pyproj import Transformer
    if not series.get("start_iso"):
        return None
    t0 = pd.Timestamp(series["start_iso"].rstrip("Z")); t1 = t0 + pd.Timedelta(hours=int(round(series["duration_h"])) - 1)
    d = xr.open_zarr(ERA5_TP); ny, nx = grid["height"], grid["width"]
    tr = Transformer.from_crs(grid["crs"], 4326, always_xy=True); a = grid["affine"]
    cols, rows = np.meshgrid(np.arange(nx) + 0.5, np.arange(ny) + 0.5); xs, ys = a * (cols, rows); lon, lat = tr.transform(xs, ys)
    pad = 0.15; la0, la1, lo0, lo1 = lat.min() - pad, lat.max() + pad, lon.min() - pad, lon.max() + pad
    tp = d.tp.sel(time=slice(t0, t1)); latn = d.latitude.values
    tp = tp.sel(latitude=slice(la1, la0) if latn[0] > latn[-1] else slice(la0, la1), longitude=slice(lo0, lo1))
    if tp.time.size < 2 or tp.latitude.size < 2 or tp.longitude.size < 2:
        return None
    tot = np.maximum(tp.sum("time").load().values.astype(float), 0.0); la_c, lo_c = tp.latitude.values, tp.longitude.values
    from scipy.interpolate import RegularGridInterpolator
    if la_c[0] > la_c[-1]:
        la_c, tot = la_c[::-1], tot[::-1]
    f = RegularGridInterpolator((la_c, lo_c), tot, bounds_error=False, fill_value=None)
    ref = float(f([[ref_lat, ref_lon]])[0])
    if ref <= 1.0:                                                           # a dry reference cell has no meaningful ratio
        return None
    return np.clip(f(np.stack([lat.ravel(), lon.ravel()], -1)).reshape(ny, nx) / ref, lo, hi).astype("float32")


def era5_wettest_event(lat, lon, years=None, window_h=72):
    """Wettest rolling window at the point (the storm a hindcast would most plausibly target)."""
    import xarray as xr
    d = xr.open_zarr(ERA5_TP)
    s = d.tp.sel(latitude=lat, longitude=lon, method="nearest")
    if years:
        s = s.sel(time=slice(f"{years[0]}-01-01", f"{years[1]}-12-31"))
    v = np.maximum(s.load().values.astype(float), 0)
    c = np.convolve(v, np.ones(window_h), "valid")
    i = int(np.argmax(c))
    t0 = str(s.time.values[i])[:13]
    return {"start": t0, "end": str(s.time.values[min(i + window_h - 1, len(v) - 1)])[:13], "total_mm": float(c[i])}


def chirps_daily(lat, lon, start, end):
    import rasterio
    d0, d1 = datetime.fromisoformat(start[:10]), datetime.fromisoformat(end[:10])
    vals, days = [], []
    d = d0
    while d <= d1:
        f = os.path.join(CHIRPS_DIR, str(d.year), f"chirps_pak_{d:%Y%m%d}.tif")
        if os.path.exists(f):
            with rasterio.open(f) as r:
                v = next(r.sample([(lon, lat)]))[0]
                vals.append(max(0.0, float(v)) if v != r.nodata else 0.0)
                days.append(d)
        d += timedelta(days=1)
    if not vals:
        raise ValueError("no CHIRPS days in that range")
    rate = np.repeat(np.array(vals) / 24.0, 24)         # daily total spread evenly (CHIRPS has no sub-daily information)
    return series_payload(np.arange(1, len(rate) + 1, dtype=float), rate, "CHIRPS v2 daily (5 km), spread evenly over 24 h",
                          days[0].isoformat() + "T00:00:00Z", {"daily_mm": vals})


IMERG_DIR = os.path.join(paths.SHARE, "0. Imerg", "Data")


def imerg_event(lat, lon, start, end):
    """IMERG V07 half-hourly precipitation (NASA GPM, 0.1 degree, 2000-): resolves short bursts better than hourly ERA5-Land.
    Reads the monthly files that cover [start, end]; the value for each 30-min slot is a depth (mm); the series is returned as mm/h at 30-min steps."""
    import xarray as xr, pandas as pd
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59)
    parts = []
    for p in pd.period_range(t0, t1, freq="M"):
        f = os.path.join(IMERG_DIR, f"IMERG_subhourly_PAK_{p.year}{p.month:02d}.nc")
        if os.path.exists(f):
            with xr.open_dataset(f) as d:
                parts.append(d.precipitation_mm.sel(lat=lat, lon=lon, method="nearest").sel(time=slice(t0, t1)).load())
    if not parts:
        raise ValueError("IMERG files do not cover that period (they start in 2000)")
    s = xr.concat(parts, "time")
    v = np.maximum(np.nan_to_num(s.values.astype(float)), 0.0)
    th = (np.arange(len(v)) + 1) * 0.5
    return series_payload(th, v / 0.5, "IMERG V07 half-hourly (GPM, 0.1 degree)", str(s.time.values[0])[:19] + "Z", {"grid_lat": float(s.lat), "grid_lon": float(s.lon), "step_min": 30})


# ---- intensity-duration thresholds (global, empirical; WATCH tier only, experimental/unvalidated for Pakistan)
ID_THRESHOLDS = {
    "caine_1980": {"a": 14.82, "b": -0.39, "dmin_h": 0.167, "dmax_h": 500, "ref": "Caine (1980) global I = 14.82 D^-0.39 (mm/h, h)"},
    "guzzetti_2008": {"a": 2.20, "b": -0.44, "dmin_h": 0.1, "dmax_h": 1000, "ref": "Guzzetti et al. (2008) global I = 2.20 D^-0.44 (mm/h, h)"},
}


def id_check(rate_mm_h, dt_h=1.0, which="guzzetti_2008"):
    """Highest intensity over each duration vs the threshold curve; returns exceedance ratios per duration."""
    th = ID_THRESHOLDS[which]
    r = np.asarray(rate_mm_h, float)
    out = []
    for D in (1, 3, 6, 12, 24, 48, 72):
        n = int(round(D / dt_h))
        if n < 1 or n > len(r):
            continue
        I = float(np.max(np.convolve(r, np.ones(n) / n, "valid")))
        thr = th["a"] * D ** th["b"]
        out.append({"duration_h": D, "max_intensity_mm_h": round(I, 2), "threshold_mm_h": round(thr, 2), "ratio": round(I / thr, 2)})
    return {"threshold": th["ref"], "rows": out, "exceeded": any(o["ratio"] >= 1 for o in out),
            "status": "experimental_unvalidated"}
