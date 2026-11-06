#!/usr/bin/env python3
"""Run the real USGS TRIGRS program (v2.1.0c, built from source with gfortran) on single-column cases and compare it with (a) the Green-Ampt proxy the platform uses and
(b) the Iverson (2000) analytic solution implemented in scripts/compare_iverson.py. Same inputs, same infinite-slope FS, saturated infinite-depth TRIGRS option.

Usage: compare_trigrs.py <TRIGRS source checkout> <trg executable>. The program is run in a scratch copy of the checkout's flume example (a 1 x 1 cell grid), one run per case.
Output times are every 15 minutes for 48 h; failure time = first output time with FS <= 1 at the slip surface depth. Writes docs/validation/trigrs_comparison.json."""
import itertools, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "scripts"))
import compare_iverson as CI                                                  # noqa: E402
from landslide.units import GAMMA_W                                           # noqa: E402

DT = 900.0; HOURS = 48; TIMES = np.arange(1, int(HOURS * 3600 / DT) + 1) * DT


def trigrs_fs(work, exe, tpl, slope, z, ks, rain_mm_h, d_off):
    I = min(rain_mm_h / 3.6e6, ks)
    (work / "data/flume/slope.asc").write_text("ncols 1\nnrows 1\nxllcorner 0\nyllcorner 0\ncellsize 10\nNODATA_value -9999\n%s\n" % slope)
    L = list(tpl)
    L[3] = f"{TIMES.size}, 10, -100, 1"                                       # tx = time steps per rain period, so every 15-minute output time exists
    L[5] = f"100, 0.00, {GAMMA_W}, 1, {HOURS * 3600}"
    L[7] = f"{z}, {z + d_off}, 0., 0., 90.0"                                 # zmax = slip depth, initial water table depth, no initial flux
    L[10] = f"{CI.C}, {CI.PHI}, {CI.GS}, {CI.D0_FACTOR * ks}, {ks}, {CI.THS}, 0.06, -1.4"
    L[12] = f"{I}"; L[14] = f"0,{HOURS * 3600}"
    i = [k for k, l in enumerate(L) if l.startswith("Number of times to save")][0]
    L[i + 1] = str(TIMES.size); L[i + 3] = ", ".join(f"{t:.0f}." for t in TIMES)
    j = [k for k, l in enumerate(L) if l.startswith("Skip other timesteps")][0]; L[j + 1] = "T"      # save only the requested times
    (work / "tr_in.txt").write_text("\n".join(L) + "\n")
    subprocess.run([str(exe)], cwd=work, capture_output=True, timeout=60, check=True)
    txt = (work / "data/flume/TRlist_z_p_fs_flume.txt").read_text().splitlines()
    fs = []; last = None
    for ln in txt[4:]:
        if ln.startswith("cell"):
            if last is not None:
                fs.append(last)
            last = None
        else:
            p = ln.split()
            if len(p) >= 6:
                last = float(p[-1])
    if last is not None:
        fs.append(last)
    return np.array(fs)


def first(fs):
    i = np.where(fs <= 1.0)[0]; return float(TIMES[i[0]] / 3600.0) if i.size else None


def main(src, exe):
    src = Path(src); work = Path(tempfile.mkdtemp(prefix="trigrs_run_"))
    shutil.copytree(src / "data", work / "data"); tpl = (src / "tr_in_flume.txt").read_text().splitlines()
    rows = []
    for d_off, slope, z, ks, rain in itertools.product((0.0, 0.5, 1.0), (25, 30, 35, 40, 45), (1.0, 2.0, 3.0), (1e-6, 1e-5, 1e-4), (5, 10, 25, 50, 100)):
        fs_t = trigrs_fs(work, exe, tpl, slope, z, ks, rain, d_off)
        ti, tg, _, _ = CI.run_case(slope, z, ks, rain, d_off, hours=HOURS, dt=DT)
        rows.append({"water_table_below_slip_m": d_off, "slope": slope, "z": z, "ks": ks, "rain_mm_h": rain, "t_trigrs_h": first(fs_t[:TIMES.size]) if fs_t.size >= TIMES.size else None,
                     "t_iverson_python_h": ti, "t_greenampt_h": tg, "n_output_blocks": int(fs_t.size)})
    ok = [r for r in rows if r["n_output_blocks"] >= TIMES.size]
    def agree(a, b):
        return float(100 * np.mean([(r[a] is None) == (r[b] is None) for r in ok]))
    def ratio(a, b):
        v = [r[a] / r[b] for r in ok if r[a] is not None and r[b] is not None]; return {"n": len(v), "median": float(np.median(v)), "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90))} if v else None
    out = {"cases": len(rows), "cases_with_full_output": len(ok), "trigrs": "USGS TRIGRS 2.1.0c, saturated infinite-depth option", "output_step_s": DT,
           "fail_vs_nofail_agreement_pct": {"trigrs_vs_iverson_python": agree("t_trigrs_h", "t_iverson_python_h"), "trigrs_vs_greenampt": agree("t_trigrs_h", "t_greenampt_h")},
           "trigrs_fails": sum(r["t_trigrs_h"] is not None for r in ok), "greenampt_fails": sum(r["t_greenampt_h"] is not None for r in ok),
           "only_trigrs_fails": sum(r["t_trigrs_h"] is not None and r["t_greenampt_h"] is None for r in ok), "only_greenampt_fails": sum(r["t_trigrs_h"] is None and r["t_greenampt_h"] is not None for r in ok),
           "time_ratio_python_iverson_over_trigrs": ratio("t_iverson_python_h", "t_trigrs_h"), "time_ratio_greenampt_over_trigrs": ratio("t_greenampt_h", "t_trigrs_h"), "rows": rows}
    (ROOT / "docs/validation/trigrs_comparison.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
