#!/usr/bin/env python3
"""Validate the ground-motion models against USGS ShakeMap PGA for past earthquakes in and around Pakistan.

Archive: datasets/external/shakemap/<event>.npz (scripts/download_shakemaps_pk.py: M >= 5.5 since 1973, 57-81 E, 20-41 N).
Metadata (epicentre, magnitude) comes from the USGS event service. Models compared on the ShakeMap grid cells (every 3rd cell):
  jb81    Joyner & Boore (1981), no site term                       - the screening relation the platform used before
  bssa14  Boore et al. (2014) NGA-West2 with Vs30 from the USGS global grid  - shallow crustal events
  auto    bssa14 for events shallower than 40 km, Abrahamson et al. (2016) BC Hydro intraslab model for deeper ones (Hindu Kush)  - the platform default
Distance: epicentre distance minus half the Wells & Coppersmith rupture length (a centred line; the real finite faults are not known here),
so near-field cells (< ~15 km) are the weakest part of the comparison and are reported separately.
A ShakeMap is itself a model (GMPE + stations + site amplification), so this tests agreement with the USGS product, not with ground truth.
Writes docs/validation/pga_validation.json."""
import json, sys
from pathlib import Path
import numpy as np
import rasterio
import requests
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.engine import trigger as TR, site as SITE     # noqa: E402

ARCH = ROOT / "datasets/external/shakemap"
API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BINS = [(0, 15), (15, 50), (50, 100), (100, 200), (200, 300)]


def events():
    ev = requests.get(API, params=dict(format="geojson", minmagnitude=5.5, starttime="1973-01-01", producttype="shakemap", orderby="time", limit=2000,
                                       minlongitude=57, maxlongitude=81, minlatitude=20, maxlatitude=41), timeout=120).json()["features"]
    return {e["id"]: dict(lon=e["geometry"]["coordinates"][0], lat=e["geometry"]["coordinates"][1], depth=e["geometry"]["coordinates"][2],
                          mag=e["properties"]["mag"], place=e["properties"]["place"], time=e["properties"]["time"]) for e in ev}


def load_faults():
    """Mapped fault traces (lon/lat polylines) as shapely lines in a flat km frame per event (see rupture_distance)."""
    import geopandas as gpd
    from landslide.app import paths
    g = gpd.read_file(paths.get("FAULTS_SHP")); L = []
    for geom in g.geometry:
        if geom is not None:
            L += list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
    return L


def rupture_distance(faults, e, LO, LA, snap_km=25.0):
    """Distance (km) from each cell to a Wells-Coppersmith-length segment of the nearest mapped fault centred on the epicentre's projection,
    or None if no fault lies within snap_km (the caller then keeps the centred-point distance). Flat-earth frame at the epicentre."""
    from shapely.geometry import LineString, Point
    from shapely.ops import substring
    kx, ky = 111.32 * np.cos(np.radians(e["lat"])), 110.57
    fr = lambda xs, ys: np.c_[(np.asarray(xs) - e["lon"]) * kx, (np.asarray(ys) - e["lat"]) * ky]
    p = Point(0, 0); best, bd = None, 1e9
    for f in faults:
        if abs(f.bounds[0] - e["lon"]) > 3 and abs(f.bounds[2] - e["lon"]) > 3:
            continue
        xy = fr(*zip(*f.coords)[:2]) if False else fr([c[0] for c in f.coords], [c[1] for c in f.coords])
        ln = LineString(xy); d = ln.distance(p)
        if d < bd:
            best, bd = ln, d
    if best is None or bd > snap_km:
        return None
    L = TR.rupture_length_km(e["mag"]); s0 = best.project(p); seg = substring(best, max(0, s0 - L / 2), min(best.length, s0 + L / 2))
    pts = np.array(seg.coords) if seg.geom_type == "LineString" and seg.length > 0 else np.array([[0.0, 0.0]])
    if len(pts) > 1:                                                              # densify to ~1 km so the nearest-vertex distance is the line distance
        t = np.linspace(0, seg.length, max(2, int(seg.length) + 2)); pts = np.array([seg.interpolate(x).coords[0] for x in t])
    cells = fr(LO.ravel(), LA.ravel()); from scipy.spatial import cKDTree
    return cKDTree(pts).query(cells)[0].reshape(LO.shape)


def stats(err):
    return {"n": int(err.size), "bias_ln": float(err.mean()), "sd_ln": float(err.std()), "rmse_ln": float(np.sqrt((err ** 2).mean()))}


def main():
    ev = events(); rows = []; faults = load_faults(); pooled = {"jb81": [], "bssa14": [], "auto": [], "auto_fault": [], "fault_used": [], "d": [], "m": [], "deep": [], "obs": []}
    vs = rasterio.open(SITE.VS30)
    for f in sorted(ARCH.glob("*.npz")):
        e = ev.get(f.stem)
        if e is None:
            continue
        z = np.load(f); pga = z["pga"].astype("float32") / 100.0                      # ShakeMap PGA is stored in %g
        ny, nx = pga.shape; lon = z["lon0"] + np.arange(nx) * z["dlon"]; lat = z["lat0"] + np.arange(ny) * z["dlat"]
        lon, lat, pga = lon[::3], lat[::3], pga[::3, ::3]; LO, LA = np.meshgrid(lon, lat)
        d_epi = np.hypot((LO - e["lon"]) * 111.32 * np.cos(np.radians(e["lat"])), (LA - e["lat"]) * 110.57)
        deep = e["depth"] > TR.SLAB_DEPTH_KM
        d = d_epi if deep else np.maximum(d_epi - 0.5 * TR.rupture_length_km(e["mag"]), 0.0)         # intraslab events are point sources at the hypocentre
        d_fault = None if deep else rupture_distance(faults, e, LO, LA)
        used = d_fault is not None
        ok = np.isfinite(pga) & (pga > 0.005) & (d < 300)
        if ok.sum() < 50:
            continue
        v = np.array([x[0] for x in vs.sample(list(zip(LO[ok], LA[ok])))], "float32"); v = np.where(np.isfinite(v), v, 760.0)
        obs = np.log(pga[ok]); r = {}
        for name, pred in (("jb81", TR.jb81_pga_g(e["mag"], d[ok])), ("bssa14", TR.bssa14_pga_g(e["mag"], d[ok], v)),
                           ("auto", TR.pga_model(e["mag"], d[ok], v, "auto", e["depth"]))):
            err = np.log(pred) - obs; r[name] = stats(err); pooled[name].append(err)
        dd = d_fault[ok] if used else d[ok]                                             # events with a mapped fault within 25 km use the fault trace, others the centred line
        errf = np.log(TR.pga_model(e["mag"], dd, v, "auto", e["depth"])) - obs; pooled["auto_fault"].append(errf); pooled["fault_used"].append(np.full(ok.sum(), used))
        pooled["d"].append(d[ok]); pooled["m"].append(np.full(ok.sum(), e["mag"])); pooled["obs"].append(obs); pooled["deep"].append(np.full(ok.sum(), deep))
        rows.append({"event": f.stem, "mag": e["mag"], "depth_km": e["depth"], "place": e["place"], **r})
    if not rows:
        sys.exit("no events processed: run scripts/download_shakemaps_pk.py first")
    P = {k: np.concatenate(v) for k, v in pooled.items()}; out = {"events": len(rows), "cells": int(P["d"].size), "ln_error_is_model_minus_shakemap": True, "pooled": {}, "by_distance": {}, "by_magnitude": {}}
    out["events_deep_gt40km"] = int(sum(r["depth_km"] > TR.SLAB_DEPTH_KM for r in rows)); sh, dp = ~P["deep"], P["deep"]
    for name in ("jb81", "bssa14", "auto"):
        out["pooled"][name] = {"all": stats(P[name]), "shallow_le40km": stats(P[name][sh]), **({"deep_gt40km": stats(P[name][dp])} if dp.any() else {})}
        out["by_distance"][name] = {f"{a}-{b}km": stats(P[name][sh & (P["d"] >= a) & (P["d"] < b)]) for a, b in BINS if (sh & (P["d"] >= a) & (P["d"] < b)).sum() > 50}
        out["by_magnitude"][name] = {f"M{a}-{b}": stats(P[name][sh & (P["m"] >= a) & (P["m"] < b)]) for a, b in [(5.5, 6.0), (6.0, 6.5), (6.5, 7.0), (7.0, 9.5)] if (sh & (P["m"] >= a) & (P["m"] < b)).sum() > 50}
    fu = P["fault_used"]; big = sh & (P["m"] >= 6.5)
    out["fault_trace"] = {"cells_with_fault": int((fu & sh).sum()),
                          "shallow_events_with_fault": {"centred_line": stats(P["auto"][fu & sh]), "fault_trace": stats(P["auto_fault"][fu & sh])} if (fu & sh).any() else None,
                          "M65_plus_with_fault": {"centred_line": stats(P["auto"][fu & big]), "fault_trace": stats(P["auto_fault"][fu & big])} if (fu & big).sum() > 50 else None,
                          "near_field_lt15km_with_fault": {"centred_line": stats(P["auto"][fu & sh & (P["d"] < 15)]), "fault_trace": stats(P["auto_fault"][fu & sh & (P["d"] < 15)])} if (fu & sh & (P["d"] < 15)).sum() > 50 else None}
    out["by_distance_note"] = "shallow events only; error = ln(model) - ln(ShakeMap)"
    out["per_event_median_abs_bias_ln"] = {n: float(np.median([abs(r[n]["bias_ln"]) for r in rows])) for n in ("jb81", "bssa14", "auto")}
    out["worst_events_auto"] = sorted(({"event": r["event"], "mag": r["mag"], "depth_km": r["depth_km"], "place": r["place"], "bias_ln": r["auto"]["bias_ln"]} for r in rows), key=lambda x: -abs(x["bias_ln"]))[:8]
    (ROOT / "docs/validation/pga_validation.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("events", "events_deep_gt40km", "cells", "pooled", "per_event_median_abs_bias_ln")}, indent=1))


if __name__ == "__main__":
    main()
