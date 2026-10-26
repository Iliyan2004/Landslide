"""M07 rainfall I-D threshold and M22 watch orchestration. Exceedance = WATCH, never 'confirmed landslide' (§0, §9.4)."""
from __future__ import annotations
import numpy as np
from datetime import datetime, timezone

TIERS = ("none", "watch", "elevated_watch")


def fit_id_threshold(duration_h, intensity_mm_h, quantile=0.05):
    """Lower-envelope I = alpha D^-beta by log-OLS shifted to the residual `quantile` (event-only fit; non-event
    dates are required for POD/FAR evaluation, see `contingency`)."""
    ld, li = np.log10(duration_h), np.log10(intensity_mm_h)
    slope, intercept = np.polyfit(ld, li, 1)
    resid = li - (slope * ld + intercept)
    shift = np.quantile(resid, quantile)
    return {"alpha": float(10 ** (intercept + shift)), "beta": float(-slope), "quantile": quantile}


def exceeds(threshold, duration_h, intensity_mm_h):
    return np.asarray(intensity_mm_h) >= threshold["alpha"] * np.asarray(duration_h) ** (-threshold["beta"])


def contingency(pred, obs):
    pred, obs = np.asarray(pred, bool), np.asarray(obs, bool)
    h, m, f, c = (pred & obs).sum(), (~pred & obs).sum(), (pred & ~obs).sum(), (~pred & ~obs).sum()
    pod = h / (h + m) if h + m else np.nan
    far = f / (h + f) if h + f else np.nan
    csi = h / (h + m + f) if h + m + f else np.nan
    return {"hits": int(h), "misses": int(m), "false_alarms": int(f), "correct_neg": int(c),
            "POD": float(pod), "FAR": float(far), "CSI": float(csi)}


def watch_state(rain_exceeds, api_percentile=None, forecast_exceeds=None, hindcast_validated=False,
                data_issued_utc=None, max_age_h=6, now=None, instrument_alert=False):
    """Evidence-labelled watch. Without hindcast validation output is `experimental_unvalidated`."""
    now = now or datetime.now(timezone.utc)
    age_h = None if data_issued_utc is None else (now - data_issued_utc).total_seconds() / 3600
    stale = age_h is None or age_h > max_age_h
    score = int(bool(rain_exceeds)) + int(api_percentile is not None and api_percentile >= 0.9) + int(bool(forecast_exceeds))
    tier = TIERS[0] if score == 0 else TIERS[1] if score == 1 else TIERS[2]
    return {"tier": tier, "evidence": {"observed_exceedance": bool(rain_exceeds), "forecast_exceedance": bool(forecast_exceeds),
            "api_percentile": api_percentile, "instrument_alert": bool(instrument_alert)},
            "data_age_h": age_h, "stale_data": stale,
            "status": "decision_support" if hindcast_validated else "experimental_unvalidated",
            "disclaimer": "Watch trigger only; not a confirmed landslide, not an evacuation order. Defer to national authorities."}
