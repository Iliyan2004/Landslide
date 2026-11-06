"""Spatially varying ground parameters. Off by default (a run asks for it with spatial_ground: true).

Layers (each optional; a missing layer is skipped and reported, never invented):
  lithology  GLiM v1.1 first-level classes (datasets/external/glim)           -> cohesion x exp(w_g)   and friction x (1 + kphi w_g) by lithology GROUP g
  texture    SoilGrids 2.0 clay, sand, coarse fragments, mean of 5-60 cm      -> cohesion x exp(a_c (clay-20)/20),  friction x (1 + a_phi (sand-40)/40 + a_cf cf/30)
  regolith   absolute depth to bedrock, SoilGrids 2017 BDTICM                 -> slip depth capped at  max(min_m, scale x BDTICM)   (only if regolith.use)
  land cover ESRI 10 m classes                                                -> root cohesion (kPa) table
Every coefficient lives in configs/ground_classes.yaml and is NEUTRAL (no effect) until scripts/calibrate_physics.py fits it on held-out spatial blocks
and the result is adopted. Nothing here is filled from intuition."""
from __future__ import annotations
import os
import numpy as np
import yaml
from rasterio.enums import Resampling
from ..app import paths, rasters

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "..", "..", "configs", "ground_classes.yaml")
EXT = os.path.join(HERE, "..", "..", "..", "datasets", "external")
GLIM = os.path.join(EXT, "glim", "glim_pk.tif"); GLIM_CLASSES = os.path.join(EXT, "glim", "glim_classes.json")
SG = os.path.join(EXT, "soilgrids")
BDTICM = os.path.join(SG, "bdticm_cm.tif")
TEX_DEPTHS = ("5-15cm", "15-30cm", "30-60cm")
# GLiM class code -> lithology group (grouping is a modelling choice; the per-group coefficients are what calibration fits)
GROUPS = {"su": "unconsolidated", "ss": "sedimentary", "sm": "sedimentary", "sc": "carbonate", "ev": "sedimentary", "mt": "metamorphic",
          "pa": "plutonic", "pi": "plutonic", "pb": "plutonic", "va": "volcanic", "vi": "volcanic", "vb": "volcanic", "py": "volcanic"}
GROUP_NAMES = ("unconsolidated", "sedimentary", "carbonate", "metamorphic", "plutonic", "volcanic")


def load_cfg(path=None):
    with open(path or CFG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read(path, grid, rs):
    return rasters.read(path, grid, rs) if os.path.exists(path) else None


def load_layers(grid, shape):
    """All ground rasters on the analysis grid (cached by the caller). Returns dict with arrays or None."""
    import json
    L = {"group": None, "clay": None, "sand": None, "cf": None, "bdticm_m": None, "lulc": rasters.read(paths.get("LULC"), grid, Resampling.nearest)}
    g = _read(GLIM, grid, Resampling.nearest)
    if g is not None and os.path.exists(GLIM_CLASSES):
        code = {int(k): v["code"] for k, v in json.load(open(GLIM_CLASSES)).items()}
        gi = np.full(shape, -1, "int8")
        for k, c in code.items():
            if c in GROUPS:
                gi[np.isfinite(g) & (np.rint(np.nan_to_num(g)) == k)] = GROUP_NAMES.index(GROUPS[c])
        L["group"] = gi
    for name, stem, scale in (("clay", "clay", 0.1), ("sand", "sand", 0.1), ("cf", "cfvo", 0.1)):
        parts = [x for x in (_read(os.path.join(SG, f"{stem}_{d}.tif"), grid, Resampling.bilinear) for d in TEX_DEPTHS) if x is not None]
        if parts:
            L[name] = (np.nanmean(np.stack(parts), 0) * scale).astype("float32")           # g/kg -> %, cm3/dm3 -> %
    b = _read(BDTICM, grid, Resampling.bilinear)
    if b is not None:
        L["bdticm_m"] = (b / 100.0).astype("float32")
    return L


def apply(sp, grid, shape, cfg=None, cache=None):
    """Copy of the scenario point sp with per-cell arrays. Returns (sp2, report). `cache` (a dict) keeps the rasters read for this grid."""
    cfg = cfg or load_cfg()
    if cache is not None and "L" in cache:
        L = cache["L"]
    else:
        L = load_layers(grid, shape)
        if cache is not None:
            cache["L"] = L
    sp2 = dict(sp); rep = {"lithology_coverage": 0.0, "texture_coverage": 0.0, "regolith_coverage": 0.0, "landcover_coverage": 0.0, "active": []}
    c_mult = np.ones(shape, "float32"); f_mult = np.ones(shape, "float32")
    lw = cfg.get("lithology", {}); kphi = float(lw.get("friction_per_unit", 0.0))
    if L["group"] is not None:
        gi = L["group"]; rep["lithology_coverage"] = float((gi >= 0).mean())
        for j, name in enumerate(GROUP_NAMES):
            w = float(lw.get("weights", {}).get(name, 0.0))
            if w != 0.0:
                c_mult[gi == j] *= np.exp(w); f_mult[gi == j] *= 1.0 + kphi * w
                if "lithology" not in rep["active"]:
                    rep["active"].append("lithology")
    tx = cfg.get("texture", {}); ac, aphi, acf = float(tx.get("a_c", 0.0)), float(tx.get("a_phi", 0.0)), float(tx.get("a_cf", 0.0))
    if (ac or aphi or acf) and L["clay"] is not None and L["sand"] is not None:
        clay, sand = np.nan_to_num(L["clay"], nan=20.0), np.nan_to_num(L["sand"], nan=40.0); cf = np.nan_to_num(L["cf"], nan=0.0) if L["cf"] is not None else 0.0
        c_mult *= np.exp(ac * (clay - 20.0) / 20.0); f_mult *= 1.0 + aphi * (sand - 40.0) / 40.0 + acf * cf / 30.0
        rep["texture_coverage"] = float(np.isfinite(L["clay"]).mean()); rep["active"].append("texture")
    if (c_mult != 1.0).any() or (f_mult != 1.0).any():
        sp2["effective_cohesion"] = sp["effective_cohesion"] * c_mult
        sp2["friction_angle"] = np.clip(sp["friction_angle"] * f_mult, 12.0, 45.0).astype("float32")
    rg = cfg.get("regolith", {})
    if rg.get("use") and L["bdticm_m"] is not None:
        cap = np.maximum(float(rg.get("min_m", 0.3)), float(rg.get("scale", 1.0)) * L["bdticm_m"]); sp2["regolith_cap_m"] = np.where(np.isfinite(cap), cap, np.nan).astype("float32")
        rep["regolith_coverage"] = float(np.isfinite(L["bdticm_m"]).mean()); rep["active"].append("regolith")
    lc = L["lulc"]
    if lc is not None:
        add = np.zeros(shape, "float32")
        for k, kpa in cfg.get("landcover_root_cohesion_kpa", {}).items():
            add[np.isfinite(lc) & (np.rint(np.nan_to_num(lc)) == int(k))] = float(kpa) * 1000.0
        # the scenario root cohesion (0-5 kPa range) is REPLACED by the land-cover value where the land cover is known, kept elsewhere
        base = np.full(shape, float(sp["root_cohesion"]), "float32")
        sp2["root_cohesion"] = np.where(np.isfinite(lc), add, base).astype("float32")
        rep["landcover_coverage"] = float(np.isfinite(lc).mean()); rep["active"].append("landcover")
    return sp2, rep


def apply_zones(sp, zones, grid, shape):
    """User-drawn strength zones (FastSlide-style 'set cohesion / friction'): each zone is {geometry (GeoJSON polygon, lon/lat), cohesion_kpa?, friction_deg?}.
    Later zones override earlier ones. Cells in a zone get the stated effective cohesion and/or friction angle (replacing, not multiplying, the scenario value); everything
    else keeps the scenario / ground-map value. Returns (sp2, report)."""
    from shapely.geometry import shape as shp
    c = np.broadcast_to(np.asarray(sp["effective_cohesion"], "float32"), shape).copy(); f = np.broadcast_to(np.asarray(sp["friction_angle"], "float32"), shape).copy(); n = 0; cells = 0
    for z in (zones or [])[:50]:
        try:
            m = rasters.polygon_mask(z["geometry"], grid)
        except Exception:
            continue
        if not m.any():
            continue
        if z.get("cohesion_kpa") is not None:
            c[m] = float(np.clip(float(z["cohesion_kpa"]), 0.0, 100.0)) * 1000.0
        if z.get("friction_deg") is not None:
            f[m] = float(np.clip(float(z["friction_deg"]), 5.0, 50.0))
        n += 1; cells += int(m.sum())
    sp2 = dict(sp); sp2["effective_cohesion"] = c; sp2["friction_angle"] = f
    return sp2, {"zones_applied": n, "cells": cells}
