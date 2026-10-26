"""Return-period design storms from OBSERVATIONAL annual maxima, and climate scaling.

Data: the per-cell rainfall-indices cube on the server (ERA5-Land hourly 1980-2025, 0.1 deg: annual maximum accumulation over running
windows of 1, 2, 3, 6, 12, 24 h; IMERG V07 30-min product 2000-2026: 30-180 min windows). Both are read-only.

Method: Gumbel (EV1) fitted by L-moments to the annual maxima of each duration (46 ERA5 years). L-moments are stable at n ~ 40 where a
3-parameter GEV is not. Depth(T, D) = xi - alpha ln(-ln(1 - 1/T)). The 24 h depth is the anchor; depth is made non-decreasing in D.
Short durations (below 1 h) take their SHAPE from IMERG and their LEVEL from ERA5 (IMERG alone is only ~26 years).
Point rainfall is used (no areal reduction): conservative for the 20-700 km2 areas this platform runs.
Hyetograph: alternating blocks (largest block at the centre). Climate: delta change (ratio of the Gumbel T-year 24 h value, SSP / historical,
ensemble median across CMIP6 models), applied as a multiplier. ERA5-Land smooths convective bursts, so depths are LOWER BOUNDS for short durations."""
from __future__ import annotations
import glob, json, os
import numpy as np
from . import paths

FLOOD = os.path.join(paths.SHARE, "Tasks", "Reselli_AI", "flood", "global_data", "rainfall_idf")
ERA = os.environ.get("LANDSLIDE_IDF_ERA", os.path.join(FLOOD, "rainfall_indices_pixel_1980_2026.nc"))
IMG = os.environ.get("LANDSLIDE_IDF_IMERG", os.path.join(FLOOD, "rainfall_indices_imerg_pixel_2000_2026.nc"))
CMIP6 = os.path.join(paths.SHARE, "CMIP6")
RETURN_PERIODS = (2, 5, 10, 25, 50, 100, 200)
EULER = 0.5772156649015329


def available():
    return os.path.exists(ERA)


def gumbel_lmom(x):
    """(xi, alpha) by probability-weighted moments: alpha = l2/ln2, xi = l1 - gamma alpha."""
    x = np.sort(np.asarray(x, float)); x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        raise ValueError(f"need at least 8 annual maxima, have {n}")
    i = np.arange(1, n + 1)
    b0 = x.mean(); b1 = np.sum((i - 1) / (n - 1) * x) / n
    l1, l2 = b0, 2 * b1 - b0
    alpha = l2 / np.log(2.0)
    return float(l1 - EULER * alpha), float(max(alpha, 1e-9))


def gumbel_quantile(xi, alpha, T):
    return xi - alpha * np.log(-np.log(1.0 - 1.0 / np.asarray(T, float)))


def annual_maxima(lat, lon, season="all"):
    """(durations_h, years, A[year, duration] mm) at the nearest cell; partial years are dropped."""
    import xarray as xr
    with xr.open_dataset(ERA) as d:
        c = d.sel(latitude=lat, longitude=lon, method="nearest")
        s = list(d.season.values).index(season)
        A = c.idf.isel(season=s).values.astype("float64")
        years = d.year.values
        dur = d.duration_h.values.astype(float)
        keep = years < 2026
        A, years = A[keep], years[keep]
        la, lo = float(c.latitude), float(c.longitude)
    ok = np.isfinite(A).all(1)
    return dur, years[ok], A[ok], (la, lo)


def imerg_shape(lat, lon, season="all"):
    """Depth ratio D/60min for sub-hourly durations from IMERG annual maxima (median of per-year ratios), or None."""
    if not os.path.exists(IMG):
        return None
    import xarray as xr
    try:
        with xr.open_dataset(IMG) as d:
            c = d.sel(latitude=lat, longitude=lon, method="nearest")
            s = list(d.season.values).index(season)
            dm = d.duration_min.values.astype(float)
            A = c.idf_sub.isel(season=s).values.astype("float64") * (dm / 60.0)[None, :]   # variable is INTENSITY (mm/h): depth = I x D
        ok = np.isfinite(A).all(1) & (A > 0).all(1)
        if ok.sum() < 8 or 60 not in dm:
            return None
        r = A[ok] / A[ok][:, [list(dm).index(60)]]
        return dm, np.median(r, axis=0)
    except Exception:
        return None


def return_period_table(lat, lon, periods=RETURN_PERIODS, season="all", n_boot=200, seed=0):
    dur, years, A, cell = annual_maxima(lat, lon, season)
    rng = np.random.default_rng(seed)
    fits = [gumbel_lmom(A[:, j]) for j in range(A.shape[1])]
    depth = np.array([[float(gumbel_quantile(*fits[j], T)) for j in range(len(dur))] for T in periods])     # T x D
    depth = np.maximum.accumulate(depth, axis=1)                                                           # non-decreasing in duration
    lo = np.zeros_like(depth); hi = np.zeros_like(depth)
    for j in range(len(dur)):                                                                              # parametric bootstrap, 90% interval
        bs = []
        for _ in range(n_boot):
            u = rng.uniform(size=len(years)); samp = fits[j][0] - fits[j][1] * np.log(-np.log(u))
            try:
                bs.append(gumbel_quantile(*gumbel_lmom(samp), np.array(periods)))
            except ValueError:
                pass
        bs = np.array(bs)
        lo[:, j], hi[:, j] = np.percentile(bs, 5, axis=0), np.percentile(bs, 95, axis=0)
    return {"cell": {"lat": cell[0], "lon": cell[1]}, "years": [int(years[0]), int(years[-1])], "n_years": int(len(years)), "durations_h": dur.tolist(),
            "periods": list(periods), "depth_mm": depth.round(2).tolist(), "depth_p05": lo.round(2).tolist(), "depth_p95": hi.round(2).tolist(),
            "intensity_mm_h": (depth / dur[None, :]).round(2).tolist(), "source": "ERA5-Land annual maxima, Gumbel (L-moments); point rainfall, no areal reduction",
            "note": "ERA5-Land smooths convective bursts: short-duration depths are lower bounds"}


def cumulative_depth_fn(table, T, lat=None, lon=None, short="imerg"):
    """P(D) in mm for any duration D (h) from 0.25 to 24: log-log interpolation of the fitted depths; below 1 h scaled by IMERG shape
    (or by the 1-3 h power law if IMERG is unavailable)."""
    dur = np.array(table["durations_h"], float); k = table["periods"].index(T)
    P = np.array(table["depth_mm"][k], float)
    sh = imerg_shape(lat, lon) if (short == "imerg" and lat is not None) else None
    ld, lp = np.log(dur), np.log(P)
    b13 = (np.log(P[2]) - np.log(P[0])) / (np.log(dur[2]) - np.log(dur[0]))
    def f(D):
        D = np.asarray(D, float)
        out = np.exp(np.interp(np.log(np.clip(D, 1e-3, None)), ld, lp))
        sub = D < 1.0
        if sub.any():
            if sh is not None:
                dm, ratio = sh
                mins = D[sub] * 60.0
                r = np.interp(mins, dm, ratio)
                r = np.where(mins < dm[0], ratio[0] * (mins / dm[0]) ** 0.9, r)     # below the shortest IMERG window: ~D^0.9
                out[sub] = P[0] * r
            else:
                out[sub] = P[0] * D[sub] ** b13
        return out
    return f


def design_hyetograph(table, T, duration_h, dt_min=15, lat=None, lon=None, short="imerg", climate_factor=1.0):
    """Alternating-block hyetograph for a T-year storm of the given total duration (<= 24 h)."""
    if duration_h > 24.0 + 1e-9:
        raise ValueError("design storms are available up to 24 h (the IDF record's longest window)")
    dt = dt_min / 60.0; n = int(round(duration_h / dt))
    P = cumulative_depth_fn(table, T, lat, lon, short)
    cum = P(np.arange(0, n + 1) * dt + 1e-9) * climate_factor
    cum[0] = 0.0
    inc = np.maximum(np.diff(np.maximum.accumulate(cum)), 0.0)
    order = np.argsort(-inc)                                      # largest first
    out = np.zeros(n); mid = n // 2
    pos = [mid] + [mid + s * k for k in range(1, n) for s in (-1, 1)]
    pos = [p for p in pos if 0 <= p < n][:n]
    for rank, idx in enumerate(order):
        out[pos[rank]] = inc[idx]
    t = (np.arange(n) + 1) * dt
    return {"times_h": t.tolist(), "rate_mm_h": (out / dt).round(3).tolist(), "total_mm": float(out.sum()), "peak_mm_h": float(out.max() / dt),
            "duration_h": float(duration_h), "return_period_y": T, "climate_factor": climate_factor,
            "source": f"design storm T={T} y, {duration_h:g} h, alternating blocks from observed annual maxima" + (f", x{climate_factor:.2f} climate" if climate_factor != 1 else "")}


# ----------------------------------------------------------------------------------------------- climate scaling (HEAVY: not run by default)
def _annual_max_mm(lat, lon, model, scenario, y0, y1):
    import xarray as xr
    mx, rc = [], None
    for y in range(y0, y1 + 1):
        f = glob.glob(os.path.join(CMIP6, model, scenario, "*", "pr", f"pr_day_{model}_{scenario}_*_{y}_*.nc"))
        if not f:
            continue
        with xr.open_dataset(f[0]) as ds:
            if rc is None:
                rc = (int(np.abs(ds.lat.values - lat).argmin()), int(np.abs(ds.lon.values - lon).argmin()))
            v = ds["pr"].isel(lat=rc[0], lon=rc[1]).values.astype("float64") * 86400.0
            if np.isfinite(v).any():
                mx.append(float(np.nanmax(v)))
    return np.array(mx)


def climate_factor(lat, lon, scenario="ssp585", period=(2036, 2065), T=50, models=None, cap=8, cache_dir=None):
    """Delta-change multiplier for the T-year daily rainfall: ratio of Gumbel return values (future / 1985-2014), ensemble median over models.
    Reads up to cap x 60 yearly files of ~30 MB: SLOW (minutes). Cached per (location, scenario, period, T)."""
    cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "datasets", "state", "climate_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cp = os.path.join(cache_dir, f"{round(lat,2)}_{round(lon,2)}_{scenario}_{period[0]}-{period[1]}_T{T}.json")
    if os.path.exists(cp):
        return json.load(open(cp))
    models = models or sorted(m for m in os.listdir(CMIP6) if os.path.isdir(os.path.join(CMIP6, m)))[:cap]
    ratios = []
    for m in models:
        try:
            h = _annual_max_mm(lat, lon, m, "historical", 1985, 2014); f = _annual_max_mm(lat, lon, m, scenario, *period)
            if len(h) >= 8 and len(f) >= 8:
                qh = float(gumbel_quantile(*gumbel_lmom(h), T)); qf = float(gumbel_quantile(*gumbel_lmom(f), T))
                ratios.append({"model": m, "ratio": qf / qh})
        except Exception:
            continue
    if not ratios:
        raise RuntimeError("no CMIP6 model had enough years at this location")
    r = np.array([x["ratio"] for x in ratios])
    out = {"factor": float(np.median(r)), "range": [float(r.min()), float(r.max())], "n_models": len(ratios), "models": ratios, "scenario": scenario, "period": list(period),
           "T": T, "method": "delta change on Gumbel (L-moment) T-year daily rainfall, ensemble median of the ratio"}
    json.dump(out, open(cp, "w"))
    return out
