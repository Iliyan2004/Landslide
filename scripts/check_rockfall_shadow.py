#!/usr/bin/env python3
"""Rockfall sanity calibration against published runout statistics (there are no Pakistani deposit data on the server).

A synthetic cliff-talus-valley profile (60 deg cliff 250 m high, 36 deg talus 700 m long, flat floor; 30 m cells like the DEM) is run through the rockfall
engine for a grid of (sub-grid roughness, restitution multiplier, friction multiplier) values. For each rock the reach angle is atan(H/L) from release to stop. Published
statistics used as targets (Evans & Hungr 1993; Jaboyedoff & Labiouse 2011; Corominas 1996):
    shadow angle (angle to the FARTHEST 1% of rocks)        27-32 degrees (mean ~ 29-31)
    most rocks stop on the talus / at its foot                 median reach angle ~ 33-40 degrees for a talus of 36 degrees
A parameter pair is admissible when the 1st-percentile reach angle is in 27-32 and the median in 33-42. Among admissible pairs the one nearest the centre of
the literature restitution ranges is reported. This fixes the order of magnitude of the dissipation; it is NOT a field calibration.
Writes docs/validation/rockfall_shadow.json.   *** GPU run: only on request ***"""
import json, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.engine import rockfall as RK    # noqa: E402

DX = 30.0


def profile(ny=40, nx=140, cliff_h=250.0, cliff_deg=60.0, talus_len=700.0, talus_deg=36.0):
    x = np.arange(nx) * DX; z = np.zeros(nx)
    cl = cliff_h / np.tan(np.deg2rad(cliff_deg)); tl = talus_len
    z_top = cliff_h + tl * np.tan(np.deg2rad(talus_deg))
    for i, xi in enumerate(x):
        if xi < 60.0:
            z[i] = z_top
        elif xi < 60.0 + cl:
            z[i] = z_top - (xi - 60.0) * np.tan(np.deg2rad(cliff_deg))
        elif xi < 60.0 + cl + tl:
            z[i] = z_top - cliff_h - (xi - 60.0 - cl) * np.tan(np.deg2rad(talus_deg))
        else:
            z[i] = 0.0
    return np.tile(z[None, :], (ny, 1)).astype("float32"), x, 60.0 + cl, 60.0 + cl + tl


def run(rough, rscale, mscale=1.0, seed=0, n_per=60):
    Z, x, x_toe_cliff, x_toe_talus = profile(); ny, nx = Z.shape
    sc = int(round((60.0 + 20.0) / DX)); rows = np.arange(ny // 2 - 6, ny // 2 + 6)
    src = (rows, np.full(rows.shape, sc))
    rn = np.full(Z.shape, 0.32 * rscale, "float32"); rt = np.full(Z.shape, 0.76, "float32"); mu = np.full(Z.shape, 0.45 * mscale, "float32")
    o = RK.simulate(Z, DX, src, rocks_per_source=n_per, d50=0.8, rn=rn, rt=rt, mu=mu, rough_deg=rough, t_max=120.0, track=20, seed=seed, stagger_s=2.0)
    a = o["travel_angle_deg"][o["state"] >= 2]; L = np.hypot(*(o["stop_xy"] - o["src_xy"]).T)
    beyond = float((o["stop_xy"][:, 0] > x_toe_talus).mean())
    return {"p1": float(np.percentile(a, 1)), "p10": float(np.percentile(a, 10)), "p50": float(np.percentile(a, 50)), "p90": float(np.percentile(a, 90)),
            "share_beyond_talus_toe": beyond, "median_run_m": float(np.median(L)), "n": int(a.size)}


def main():
    res = {"profile": "cliff 250 m @ 60 deg + talus 700 m @ 36 deg + flat floor, 30 m cells", "targets": {"p1_deg": [27, 32], "p50_deg": [33, 42]}, "grid": []}
    t = time.time()
    for rough in (9.0,):
        for rs in (0.8, 1.0):
            for ms in (0.3, 0.4, 0.5):
                r = run(rough, rs, ms); r.update(rough_deg=rough, restitution_scale=rs, friction_scale=ms); r["admissible"] = bool(27 <= r["p1"] <= 32 and 33 <= r["p50"] <= 42); res["grid"].append(r)
                print(f"rough {rough:4.1f} Rn x{rs:4.2f} mu x{ms:4.2f}: p1 {r['p1']:5.1f} p50 {r['p50']:5.1f} p90 {r['p90']:5.1f} beyond toe {r['share_beyond_talus_toe']:.2f} {'OK' if r['admissible'] else ''}", flush=True)
    adm = [r for r in res["grid"] if r["admissible"]]
    if adm:
        best = min(adm, key=lambda r: abs(r["restitution_scale"] - 1.0) + abs(r["rough_deg"] - 9.0) / 10.0 + abs(np.log(r["friction_scale"]))); res["chosen"] = best
    else:
        res["chosen"] = None; res["note"] = "no pair in the grid meets both targets; the dissipation model itself needs work"
    res["elapsed_s"] = round(time.time() - t)
    (ROOT / "docs/validation/rockfall_shadow.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res.get("chosen"), indent=1))


if __name__ == "__main__":
    main()
