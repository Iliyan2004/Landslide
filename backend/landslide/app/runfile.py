"""Save and load a run as a small JSON file (as SAILAB's run file): the area, the storm or earthquake and the settings, so a colleague (or you, later) can restore the
same scenario. The file holds INPUTS only, never results, so loading re-runs the model under the current code. Loading is validated and whitelisted: unknown keys are
dropped and reported, the geometry must be a polygon inside Pakistan's working limits, and a custom elevation file id is kept only if that file is still on the server."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "landlab-run-file"
SCALARS = {"mode": str, "texture": str, "strength_preset": str, "strength_quantile": float, "failure_type": str, "entrain": bool, "entrain_depth_m": float, "depth_vs_slope": bool,
           "spatial_ground": bool, "antecedent": bool, "ensemble": int, "min_slope_deg": float, "min_cluster_cells": int, "release_factor": float, "mu": float, "xi": float,
           "max_soil_slope_deg": float, "seed": int, "wetness_beta": float, "suction_kpa": float, "rain_field": bool, "custom_dem_id": str, "min_source_slope_deg": float}
RAIN_KEYS = ("times_h", "rate_mm_h", "source", "start_iso", "antecedent_daily_mm", "total_mm", "peak_mm_h", "duration_h", "grid_lat", "grid_lon")
ZONE_KEYS = ("geometry", "cohesion_kpa", "friction_deg")
QUAKE_KEYS = ("magnitude", "depth_km", "lon", "lat", "time_h", "d_crit_cm", "snap_to_fault", "gmpe")


def build(rid, runs_root, version):
    d = Path(runs_root) / rid
    full = json.loads((d / "inputs.json").read_text()) if (d / "inputs.json").exists() else None
    if full:
        geom, params = full["geometry"], full["params"]
    else:                                                  # runs made before inputs.json existed: the manifest's subset of the parameters
        man = json.loads((d / "manifest.json").read_text()); g = json.loads((d / "geom.json").read_text()) if (d / "geom.json").exists() else {}
        geom, params = g.get("geom"), (man.get("params") or {})
    if not geom:
        raise FileNotFoundError("this run did not store its area (run it again to be able to save it)")
    return {"format": FORMAT, "format_version": 1, "model": "LANDLAB", "model_version": version, "saved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": rid, "geometry": geom, "params": params, "note": "Inputs only. Loading restores the area and settings; the model is run again."}


def _num(v, typ):
    if typ is bool:
        return bool(v)
    if typ is str:
        return str(v)[:80]
    return typ(v)


def sanitize(doc):
    """(geometry, params, warnings) from an uploaded run file; raises ValueError with a plain message when it cannot be used."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("this is not a LANDLAB run file")
    g = doc.get("geometry")
    if not isinstance(g, dict) or g.get("type") != "Polygon" or not g.get("coordinates"):
        raise ValueError("the run file has no polygon area")
    ring = g["coordinates"][0]
    if len(ring) < 4 or any((not isinstance(c, (list, tuple)) or len(c) < 2) for c in ring):
        raise ValueError("the area in the run file is not a valid polygon")
    if not all(60.0 <= float(c[0]) <= 78.5 and 23.0 <= float(c[1]) <= 37.5 for c in ring):
        raise ValueError("the area in the run file is outside Pakistan")
    p, warn, dropped = {}, [], []
    for k, v in (doc.get("params") or {}).items():
        if k in SCALARS:
            try:
                p[k] = _num(v, SCALARS[k])
            except Exception:
                dropped.append(k)
        elif k == "rain" and isinstance(v, dict):
            r = {kk: v[kk] for kk in RAIN_KEYS if kk in v}
            if isinstance(r.get("times_h"), list) and isinstance(r.get("rate_mm_h"), list) and len(r["times_h"]) == len(r["rate_mm_h"]) and 1 <= len(r["times_h"]) <= 5000:
                p["rain"] = r
            else:
                dropped.append("rain")
        elif k == "strength_zones" and isinstance(v, list):
            p["strength_zones"] = [{kk: z[kk] for kk in ZONE_KEYS if kk in z} for z in v[:50] if isinstance(z, dict) and isinstance(z.get("geometry"), dict)]
        elif k == "quake" and isinstance(v, dict):
            p["quake"] = {kk: v[kk] for kk in QUAKE_KEYS if kk in v}
        elif k in ("backend",):
            continue
        else:
            dropped.append(k)
    if dropped:
        warn.append("Settings not restored (unknown to this version): " + ", ".join(sorted(set(dropped))))
    if p.get("custom_dem_id"):
        from . import custom_dem as CD
        if CD.info(p["custom_dem_id"]) is None:
            warn.append("The run used an uploaded elevation file that is no longer on the server: the Pakistan SRTM will be used unless you upload it again.")
            p.pop("custom_dem_id")
    if doc.get("model_version") and str(doc["model_version"]).split(".")[0] != "2":
        warn.append(f"The file was saved by model version {doc['model_version']}; results may differ from the original.")
    return g, p, warn
