"""Landslide inventory standardisation (§4.5). Label = initiation/source scar, not deposit; keep subtype & confidence."""
from __future__ import annotations
import pandas as pd

SCHEMA = ["event_id", "hazard_subtype", "occurrence_utc", "lon", "lat", "geometry_kind", "feature_role",
          "position_uncertainty_m", "area_m2", "confidence", "trigger", "source_id", "reference"]
ROLES = ("source_scar", "runout_deposit", "undifferentiated", "candidate_change")


def standardise(df: pd.DataFrame, source_id: str, defaults: dict | None = None) -> pd.DataFrame:
    d = df.copy()
    for k, v in (defaults or {}).items():
        if k not in d:
            d[k] = v
    for c in SCHEMA:
        if c not in d:
            d[c] = pd.NA
    d["source_id"] = source_id
    d["occurrence_utc"] = pd.to_datetime(d["occurrence_utc"], utc=True, errors="coerce")
    d["feature_role"] = d["feature_role"].fillna("undifferentiated")
    bad = ~d["feature_role"].isin(ROLES)
    if bad.any():
        raise ValueError(f"invalid feature_role values: {sorted(set(d.loc[bad, 'feature_role']))}")
    return d[SCHEMA]


def dedupe(df: pd.DataFrame, radius_deg=0.002, days=1) -> pd.DataFrame:
    """Drop near-duplicate reports (same subtype, within radius & +/- days)."""
    d = df.sort_values("occurrence_utc").reset_index(drop=True)
    keep = []
    for i, r in d.iterrows():
        dup = False
        for j in keep:
            q = d.loc[j]
            if (q["hazard_subtype"] == r["hazard_subtype"] and abs(q["lon"] - r["lon"]) < radius_deg
                    and abs(q["lat"] - r["lat"]) < radius_deg and pd.notna(r["occurrence_utc"]) and pd.notna(q["occurrence_utc"])
                    and abs((q["occurrence_utc"] - r["occurrence_utc"]).days) <= days):
                dup = True
                break
        if not dup:
            keep.append(i)
    return d.loc[keep]


def susceptibility_positives(df: pd.DataFrame, max_uncertainty_m=250):
    """Source-scar records only, with acceptable position uncertainty. Uncertain points are NOT confident negatives."""
    ok = (df["feature_role"] == "source_scar") & (df["position_uncertainty_m"].astype(float) <= max_uncertainty_m)
    return df[ok]
