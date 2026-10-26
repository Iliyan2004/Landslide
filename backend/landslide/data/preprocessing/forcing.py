"""Rainfall forcing preparation (§4.4): UTC, dedupe, QC, event window with antecedent padding."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ...errors import GateError


def prepare_hourly(times, values, source_id, version, acquired_utc, max_gap_h=3):
    t = pd.to_datetime(pd.Series(times), utc=True)
    s = pd.Series(np.asarray(values, float), index=t).sort_index()
    s = s[~s.index.duplicated(keep="first")]
    if (s < 0).any():
        raise GateError(["negative precipitation values"])
    if s.max() > 300:
        raise GateError([f"implausible hourly precipitation {s.max():.0f} mm/h"])
    full = pd.date_range(s.index.min(), s.index.max(), freq="1h")
    s = s.reindex(full)
    gaps = s.isna().astype(int).groupby((s.notna()).cumsum()).sum()
    if gaps.max() > max_gap_h:
        raise GateError([f"gap of {gaps.max()} h exceeds {max_gap_h} h"])
    return s, {"source_id": source_id, "version": version, "acquired_utc": acquired_utc,
               "n_missing": int(s.isna().sum()), "timezone": "UTC"}


def event_window(series: pd.Series, event_start, event_end, antecedent_days=30):
    t0 = pd.Timestamp(event_start, tz="UTC") - pd.Timedelta(days=antecedent_days)
    t1 = pd.Timestamp(event_end, tz="UTC")
    w = series.loc[t0:t1]
    if w.index.min() > t0:
        raise GateError(["forcing does not cover the antecedent window"])
    return w
