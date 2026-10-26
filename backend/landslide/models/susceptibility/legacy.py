"""M01 legacy slope+lithology screening score (fast fallback; NOT a physical probability)."""
from __future__ import annotations
import numpy as np
import yaml


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def lithology_rank(codes, cfg):
    table = cfg["glim_erodibility_rank"]
    out = np.full(np.asarray(codes).shape, np.nan)
    for k, v in table.items():
        if v is not None:
            out[np.asarray(codes) == k] = v
    return out


def score(slope_pct, litho_rank, cfg):
    """Return (class_index 0-3 or -1 for NODATA, score 0-1). Unknown inputs -> NODATA (never low risk)."""
    bins = cfg["slope_pct_bins"]
    s_cls = np.digitize(slope_pct, bins)                      # 0..len(bins)
    s_norm = s_cls / len(bins)
    l_norm = (litho_rank - 1) / 4.0
    w = cfg["weights"]
    sc = w["slope"] * s_norm + w["lithology"] * l_norm
    valid = np.isfinite(slope_pct) & np.isfinite(litho_rank)
    cls = np.digitize(sc, cfg["class_cutoffs"])
    return np.where(valid, cls, -1), np.where(valid, sc, np.nan)
