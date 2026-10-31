"""Mitigation scenarios for landslides (a separate set from anything flood related).

Nature-based levers act on the stability inputs, inside an optional zone polygon (default: the whole area):
  planting      adds root cohesion (Pa)                             [reinforcement, Pollen/Schwarz-type ranges 2-10 kPa; the user sets it]
  regrading     caps the slope used for stability (terracing, cut-and-fill benching) at a given angle
  drainage      lowers the baseline water table (m) and scales the saturated fraction m (subsurface drains)
Grey structures act in the runout solver:
  barrier       a wall of given height and width across the flow path raises the bed; flow is stopped or overtops it as the solver decides.
All effect sizes are USER scenario inputs with defaults that are plausible, not measured; the platform reports the change in failing area and
loss against the unmitigated run, it does not claim an engineered performance."""
from __future__ import annotations
import itertools
import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import LineString, shape
from shapely.ops import transform as shp_transform

NBS_DEFAULTS = {"planting": {"root_cohesion_add_pa": 5000.0}, "regrading": {"max_slope_deg": 30.0}, "drainage": {"m_scale": 0.6, "water_table_add_m": 2.0}}


def zone_mask(zone_geom, grid, shape_hw):
    if not zone_geom:
        return np.ones(shape_hw, bool)
    from ..app import rasters
    return rasters.polygon_mask(zone_geom, grid)


def nbs_fields(spec, grid, shape_hw, valid=None):
    """spec: {"zone": polygon|None, "planting": {...}|None, "regrading": {...}|None, "drainage": {...}|None} -> per-cell fields for trigger._eff."""
    if not spec:
        return None
    zm = zone_mask(spec.get("zone"), grid, shape_hw)
    if valid is not None:
        zm &= valid
    out = {"c_root_add": None, "slope_cap": None, "m_scale": None, "wt_add": None, "zone_cells": int(zm.sum())}
    pl = spec.get("planting")
    if pl:
        out["c_root_add"] = np.where(zm, float(pl.get("root_cohesion_add_pa", NBS_DEFAULTS["planting"]["root_cohesion_add_pa"])), 0.0).astype("float32")
    rg = spec.get("regrading")
    if rg:
        out["slope_cap"] = np.where(zm, float(rg.get("max_slope_deg", NBS_DEFAULTS["regrading"]["max_slope_deg"])), np.nan).astype("float32")
    dr = spec.get("drainage")
    if dr:
        out["m_scale"] = np.where(zm, float(dr.get("m_scale", 0.6)), 1.0).astype("float32")
        out["wt_add"] = np.where(zm, float(dr.get("water_table_add_m", 2.0)), 0.0).astype("float32")
    return out


def barriers_mask(barriers, grid, epsg, shape_hw, slope_deg=None):
    """Rasterise barrier polylines (lon/lat) with their widths. Returns (bed raise in m, list of summaries).
    A barrier's height is measured ABOVE THE GROUND IMMEDIATELY UPSLOPE of it. On a grid the bed falls by tan(slope) x cell across the wall
    cell, so the wall cell is raised by height + tan(slope) x cell; otherwise a wall lower than the ground drop across one cell would not
    stand above its upslope neighbour at all (found by test: a '6 m wall' on a 0.35 slope with 20 m cells let 90% of a flow through)."""
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    add = np.zeros(shape_hw, "float32"); info = []
    for b in barriers or []:
        pts = b["coords"]
        if len(pts) < 2:
            continue
        line = shp_transform(tr.transform, LineString(pts))
        w = max(float(b.get("width_m", 6.0)), grid["resolution_m"])          # a wall narrower than a cell is widened to one cell
        m = rasterize([(line.buffer(w / 2.0), 1)], out_shape=shape_hw, transform=grid["affine"], fill=0, dtype="uint8").astype(bool)
        h = float(b.get("height_m", 4.0))
        drop = (np.tan(np.deg2rad(np.nan_to_num(slope_deg))) * grid["resolution_m"]) if slope_deg is not None else 0.0
        add = np.where(m, np.maximum(add, h + drop), add)
        info.append({"length_m": float(line.length), "height_m": h, "width_m": w, "cells": int(m.sum()), "height_basis": "above the ground immediately upslope"})
    return add, info


def apply_barriers(Z, add):
    return Z + add.astype(Z.dtype)


def nbs_combos():
    """The 7 non-empty combinations of the three levers (plus the baseline) for ranking."""
    levers = ("planting", "regrading", "drainage")
    return [c for r in range(1, 4) for c in itertools.combinations(levers, r)]


def rank_nbs(eval_fn, spec_zone=None, defaults=None):
    """eval_fn(spec) -> {'failing_km2':..., 'failing_cells':...}. Returns the baseline and every combination ranked by failing-area reduction.
    This is an FS-only evaluation (no flow): fast, and it ranks the stability benefit, not the runout benefit."""
    d = {k: dict(v) for k, v in NBS_DEFAULTS.items()}
    if defaults:
        for k, v in defaults.items():
            d.setdefault(k, {}).update(v)
    base = eval_fn(None)
    key = "unstable_km2" if "unstable_km2" in base else "failing_km2"      # like-for-like: includes slopes already unstable before the storm
    rows = []
    for combo in nbs_combos():
        spec = {"zone": spec_zone, **{k: d[k] for k in combo}}
        r = eval_fn(spec)
        rows.append({"levers": list(combo), **r, "reduction_km2": base[key] - r[key],
                     "reduction_frac": (base[key] - r[key]) / base[key] if base[key] > 0 else 0.0})
    rows.sort(key=lambda x: -x["reduction_km2"])
    return {"baseline": base, "ranked": rows, "measure": key, "note": "stability-only ranking with user-set effect sizes; runout benefit needs a full run. Ranked by the unstable area at the end of the storm, which includes slopes that were already unstable before it"}
