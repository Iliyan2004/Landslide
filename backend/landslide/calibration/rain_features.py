"""Rainfall features at an inventory event or a control date, from ERA5-Land hourly precipitation (server zarr, ~9 km).

A day-resolved event covers 24 h of UTC time and its timestamp inside the day is unknown, so the window ends at 23:00 UTC of the event
day and every intensity is the MAXIMUM over end-times within that day (identical treatment for events and controls)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ..app import rainfall as RF

DURS = (1, 3, 6, 12, 24, 48, 72, 168)
_ds = None


def _era():
    global _ds
    if _ds is None:
        import xarray as xr
        _ds = xr.open_zarr(RF.ERA5_TP)
    return _ds


_cell_cache = {}


def _cell(lat, lon):
    """Whole hourly series of the nearest ERA5 cell, cached in RAM (a few hundred cells cover every event)."""
    d = _era()
    la = float(d.latitude.sel(latitude=lat, method="nearest")); lo = float(d.longitude.sel(longitude=lon, method="nearest"))
    k = (round(la, 3), round(lo, 3))
    if k not in _cell_cache:
        s = d.tp.sel(latitude=la, longitude=lo).load()
        _cell_cache[k] = (s.time.values, np.maximum(s.values.astype("float32"), 0.0))
    return _cell_cache[k]


def series(lat, lon, day, back_days=32):
    """Hourly mm for [day-back_days, day] inclusive (UTC), as (times, values)."""
    t, v = _cell(lat, lon)
    t1 = np.datetime64(pd.Timestamp(day).normalize() + pd.Timedelta(hours=23))
    t0 = t1 - np.timedelta64(back_days, "D")
    i0, i1 = np.searchsorted(t, t0), np.searchsorted(t, t1, side="right")
    return t[i0:i1], v[i0:i1].astype("float64")


def features(lat, lon, day):
    t, v = series(lat, lon, day)
    n = len(v)
    if n < 24 * 31:
        return None
    out = {}
    last24 = slice(n - 24, n)
    for D in DURS:
        roll = np.convolve(v, np.ones(D) / D, "valid")                    # mean intensity over D h ending at each hour (index i ends at i+D-1)
        ends = np.arange(D - 1, n)                                        # end hour index for each roll value
        sel = ends >= n - 24                                              # end times within the event day
        out[f"I{D}"] = float(roll[sel].max())
    out["day_mm"] = float(v[last24].sum())
    pre = v[: n - 24]                                                     # everything before the event day
    for d in (3, 7, 14, 30):
        out[f"A{d}"] = float(pre[-24 * d:].sum()) if len(pre) >= 24 * d else np.nan
    # antecedent precipitation index, k=0.9/day on daily totals before the event day
    daily = pre[: len(pre) // 24 * 24].reshape(-1, 24).sum(1)
    api = 0.0
    for x in daily:
        api = 0.9 * api + x
    out["API"] = float(api)
    return out


def controls(df_events, n_per=20, seed=0, years=(1981, 2025), window_days=30, exclude_days=7, min_km_excl=25.0):
    """Same location as each event, random other days within +-window_days of the same day-of-year (same season), never within
    exclude_days of ANY inventory event near that place. This removes location and season as explanations."""
    rng = np.random.default_rng(seed)
    ev = df_events[df_events.date.notna()]
    rows = []
    for k, e in ev.iterrows():
        doy = e.date.dayofyear
        n = 0; tries = 0
        while n < n_per and tries < 400:
            tries += 1
            y = int(rng.integers(years[0], years[1] + 1))
            off = int(rng.integers(-window_days, window_days + 1))
            try:
                d = pd.Timestamp(year=y, month=1, day=1) + pd.Timedelta(days=doy - 1 + off)
            except Exception:
                continue
            if d.year != y or d > pd.Timestamp("2026-05-01"):
                continue
            near = ev[(np.hypot((ev.lon - e.lon) * 111.32 * np.cos(np.radians(e.lat)), (ev.lat - e.lat) * 110.57) < min_km_excl)]
            if (np.abs((near.date - d).dt.days) <= exclude_days).any():
                continue
            rows.append({"event_idx": k, "lon": e.lon, "lat": e.lat, "date": d, "radius_km": e.radius_km, "trigger": e.trigger})
            n += 1
    return pd.DataFrame(rows)
