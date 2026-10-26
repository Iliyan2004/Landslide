"""Antecedent precipitation index and rolling accumulations (methodology §4.4, §5.3). Empirical proxies only."""
import numpy as np


def antecedent_precip_index(precip_mm, k=0.9, api0=0.0):
    """API_t = P_t + k*API_{t-1}, 0<k<1."""
    if not 0 < k < 1:
        raise ValueError("k must be in (0,1)")
    p = np.asarray(precip_mm, float)
    out = np.empty_like(p)
    prev = api0
    for i, v in enumerate(p):
        prev = v + k * prev
        out[i] = prev
    return out


antecedent_precipitation_index = antecedent_precip_index


def rolling_sum(x, window):
    """Trailing sum over `window` steps (NaN until the window is full -> no partial sums presented as full)."""
    x = np.asarray(x, float)
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0))
    out = c[window:] - c[:-window]
    return np.concatenate([np.full(window - 1, np.nan), out]) if x.size >= window else np.full(x.size, np.nan)


def accumulations(precip_mm_hourly, hours=(1, 3, 6, 12, 24, 48, 72, 168, 360, 720)):
    return {f"rain_{h}h": rolling_sum(precip_mm_hourly, h) for h in hours}


def deaccumulate_era5(acc, reset_hour_index):
    """ERA5-Land accumulations reset at 00 UTC: convert to per-step amounts. `acc` hourly, resets where index%24==reset."""
    a = np.asarray(acc, float)
    out = np.diff(a, prepend=0.0)
    idx = np.arange(a.size)
    out[(idx % 24) == reset_hour_index] = a[(idx % 24) == reset_hour_index]
    return np.maximum(out, 0.0)
