"""Verification and validation of the Gilgit dashboard simulation.

1. Appends validation_harness.js to a copy of site/index.html and runs it in headless Chrome, so the real simulation
   code is what gets tested (analytic benchmarks, conservation, projection, heightfield, data integrity, DEM benchmark).
2. Compares the model with observations that exist locally: COOLR inventory (ROC), CHIRPS rainfall on event dates,
   ShakeMap shaking at earthquake-triggered reports, and published run-out relations (Corominas 1996, shadow angle).
Writes docs/validation_results.json and docs/VALIDATION_REPORT.md. Re-run build_dashboard_page.py afterwards to put the
results in the dashboard's Validation tab.
"""
import base64, html, json, re, subprocess, sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage, stats

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "landslide-platform/site"
DOCS = ROOT / "landslide-platform/docs"
DATA = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
dec = lambda b: np.frombuffer(base64.b64decode(b), np.uint8)
def to_ts(v):
    v = int(float(v)); return pd.Timestamp(v, unit="ms" if v > 1e11 else "s")

# ------------------------------------------------------------------ run the harness
page = (SITE / "index.html").read_text(encoding="utf-8")
harness = (Path(__file__).with_name("validation_harness.js")).read_text(encoding="utf-8")
test = SITE / "_validate.html"
test.write_text(page.replace("</body>", "<script>" + harness + "</script></body>"), encoding="utf-8")
print("running harness in headless Chrome ...")
try:
    dom = subprocess.run([CHROME, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                          "--window-size=1200,900", "--virtual-time-budget=1500000", "--dump-dom", test.as_uri()],
                         capture_output=True, timeout=1500, text=True, encoding="utf-8", errors="replace").stdout
finally:
    test.unlink(missing_ok=True)
m = re.search(r'<pre id="vresults"[^>]*>(.*?)</pre>', dom, re.S)
if not m:
    sys.exit("harness produced no results")
R = json.loads(html.unescape(m.group(1)))
if R["errors"]:
    print("harness errors:", R["errors"])

# ------------------------------------------------------------------ page data for the empirical checks
D = json.loads(re.search(r"const D=(\{.*?\});\nconst S=", page, re.S).group(1))
W, H = D["w"], D["h"]
b = D["stats"]["bounds"]
inv = np.load(DATA / "validation_inputs.npz", allow_pickle=True)
score, sd, nd, cells = inv["score"], inv["sd"], inv["nd"], inv["cells"]
valid = ~nd
pts_in = [p for p in D["pts"] if p["inside"]]

# ---- projection vs pyproj
from pyproj import Transformer
tr = Transformer.from_crs(4326, 32643, always_xy=True)
pr = np.array(R["proj"])
ex, ny = tr.transform(pr[:, 0], pr[:, 1])
perr = float(np.max(np.hypot(pr[:, 2] - ex, pr[:, 3] - ny)))
bx, by = Transformer.from_crs(32643, 4326, always_xy=True).transform(pr[:, 2], pr[:, 3])
rerr = float(np.max(np.hypot((bx - pr[:, 4]) * 111320 * 0.81, (by - pr[:, 5]) * 110574)))
R["tests"].append(dict(id="V13", group="Geometry", name="Browser lon/lat to UTM 43N matches pyproj", expected="0 m", got=round(perr, 4), tol="< 0.01 m", pass_=perr < 0.01,
                       note=f"200 points; inverse (UTM to lon/lat) differs from pyproj by up to {rerr:.4f} m"))
R["tests"][-1]["pass"] = R["tests"][-1].pop("pass_")

# ---- heightfield decoded in the browser vs the DEM on disk
with rasterio.open(ROOT / "gilgit_dem.tif") as r:
    z = r.read(1).astype("float32"); z[z == r.nodata] = np.nan
h53, w53 = r.height // 2, r.width // 2
z53 = np.nanmean(z[:h53 * 2, :w53 * 2].reshape(h53, 2, w53, 2), axis=(1, 3))
z53 = np.round(np.where(np.isfinite(z53), z53, np.nanmin(z53))).astype(np.int16)
hf = np.array(R["hf"]); bad = int(np.sum(z53[hf[:, 1], hf[:, 0]] != hf[:, 2]))
R["tests"].append(dict(id="V14", group="Geometry", name="Terrain decoded in the browser equals the DEM on disk (53 m heightfield)", expected="0 differing cells", got=bad, tol="= 0", **{"pass": bad == 0},
                       note=f"{len(hf)} random cells of {R['hfdim'][0]}×{R['hfdim'][1]}"))

# ---- embedded rasters vs source totals
dd = R["data"]
R["tests"].append(dict(id="V15", group="Data", name="Embedded building and population grids add up to the source totals", expected=f"{dd['bld_total']} buildings / {dd['pop_total']:.0f} people",
                       got=f"{dd['sum_bld']:.0f} / {dd['sum_pop']:.0f}", tol="buildings within 2 % (cells capped at 255); people within 3 %",
                       **{"pass": abs(dd["sum_bld"] - dd["bld_total"]) / dd["bld_total"] < .02 and abs(dd["sum_pop"] - dd["pop_total"]) / dd["pop_total"] < .03},
                       note="the building grid counts only buildings inside the DEM extent"))
R["tests"].append(dict(id="V16", group="Data", name="Valid cell area matches the DEM statistics", expected=f"{dd['area_km2']:.0f} km²", got=round(dd["valid_cells"] * dd["cell_km2"]), tol="< 1 %",
                       **{"pass": abs(dd["valid_cells"] * dd["cell_km2"] - dd["area_km2"]) / dd["area_km2"] < .01}, note="160 m cells against the 26.6 m count"))

# ------------------------------------------------------------------ inventory ROC
def auc(pos, neg):
    neg = np.sort(neg); lo = np.searchsorted(neg, pos, "left"); hi = np.searchsorted(neg, pos, "right")
    return float(np.mean((lo + 0.5 * (hi - lo)) / len(neg)))
def tol_max(a): return ndimage.maximum_filter(np.where(np.isfinite(a), a, -1e9), size=5)
ci = [(int(i), int(j)) for i, j in cells]
rng = np.random.default_rng(1)
def roc(name, arr, mask=None):
    mask = valid if mask is None else mask & valid
    f = tol_max(np.where(mask, arr, np.nan))
    pos = np.array([f[i, j] for i, j in ci if mask[i, j]]); neg = f[mask]
    if len(pos) < 5: return dict(name=name, n=len(pos), auc=None)
    a = auc(pos, neg); boots = [auc(pos[rng.integers(0, len(pos), len(pos))], neg) for _ in range(1000)]
    top = np.quantile(neg, 0.8); hit20 = float(np.mean(pos >= top)); share20 = float(np.mean(neg >= top))
    return dict(name=name, n=int(len(pos)), auc=round(a, 3), lo=round(float(np.percentile(boots, 2.5)), 3), hi=round(float(np.percentile(boots, 97.5)), 3),
                hit_top20=round(hit20, 3), area_top20=round(share20, 3))
rocs = [roc("Slope only", sd), roc("Slope + lithology screening score", score)]
labels = {"S1": "Simulation, 10 mm/h × 24 h", "S2": "Simulation, 25 mm/h × 24 h", "S3": "Simulation, 40 mm/h × 24 h", "S4": "Simulation, 10 mm/h, no root cohesion",
          "S5": "Simulation, 2015 earthquake only", "S6": "Simulation, 2005 earthquake only", "S7": "Simulation, 2019 earthquake only"}
for k, lab in labels.items():
    p = dec(R["scen"][k]["prob"]).reshape(H, W).astype(float) / 255
    if k == "S1": np.save(DATA / "S1_prob.npy", dec(R["scen"][k]["prob"]).reshape(H, W))
    # failing probability is zero outside the modelled soil-covered cells; those cells are real negatives
    rocs.append(dict(roc(lab, p), failing_cells=R["scen"][k]["nfail"]))

# ------------------------------------------------------------------ rainfall on event dates (CHIRPS)
ch = pd.read_csv(DATA / "chirps_daily_aoi_mean.csv", parse_dates=["date"]).set_index("date")["precip_mm"]
season = ch[(ch.index.month >= 6) & (ch.index.month <= 9)]
ev = []
for p in pts_in:
    try: d = to_ts(p["date"]).normalize()
    except Exception: continue
    ev.append(dict(date=str(d.date()), cat=p["cat"], trig=p["trig"]))
rain_ev = [e for e in ev if re.search(r"rain|downpour|monsoon|flood", e["trig"].lower()) and "1981" <= e["date"] <= "2025-12-31"]
roll = {n: ch.rolling(n).sum() for n in (1, 3, 7)}
rows = []
for e in rain_ev:
    d = pd.Timestamp(e["date"]); r_ = {"date": e["date"], "trigger": e["trig"]}
    for n in (1, 3, 7):
        v = max(roll[n].get(d, np.nan), roll[n].get(d + pd.Timedelta(days=1), np.nan))   # report dates can be a day late
        ref = roll[n][roll[n].index.isin(season.index)].dropna()
        r_[f"mm{n}"] = None if not np.isfinite(v) else round(float(v), 1)
        r_[f"pct{n}"] = None if not np.isfinite(v) else round(float((ref < v).mean() * 100), 1)
    rows.append(r_)
rain = dict(n=len(rows), rows=rows)
if rows:
    for n in (1, 3, 7):
        ref = roll[n][roll[n].index.isin(season.index)].dropna(); vals = np.array([r_[f"mm{n}"] for r_ in rows if r_[f"mm{n}"] is not None])
        u = stats.mannwhitneyu(vals, ref.values, alternative="greater") if len(vals) else None
        rain[f"w{n}"] = dict(median_event=round(float(np.median(vals)), 1), median_season=round(float(ref.median()), 1), p_value=round(float(u.pvalue), 4) if u else None,
                             pod_p90=round(float(np.mean(vals >= ref.quantile(.9))), 3), pod_p95=round(float(np.mean(vals >= ref.quantile(.95))), 3), n=int(len(vals)))
rain["scenario_mm"] = 240; rain["record_max_1d"] = D["rain"]["max1"]; rain["record_max_3d"] = D["rain"]["max3"]

# ------------------------------------------------------------------ shaking at earthquake-triggered reports
quake = [p for p in pts_in if "earthquake" in p["trig"].lower()]
qrows = []
for p in quake:
    d = to_ts(p["date"]).date().isoformat()
    j = int(p["u"] * W); i = int(p["v"] * H)
    for e in D["shake"]:
        if abs((pd.Timestamp(e["date"]) - pd.Timestamp(d)).days) <= 1:
            arr = dec(e["pga"]).reshape(H, W).astype(float) / 10; arr[dec(e["pga"]).reshape(H, W) == 255] = np.nan
            v = float(np.nanmax(arr[max(0, i - 2):i + 3, max(0, j - 2):j + 3]))
            qrows.append(dict(date=d, event=e["date"] + " M" + str(e["mag"]), pga_at_report=round(v, 2), pct_of_area=round(float(np.mean(arr[np.isfinite(arr)] < v) * 100), 1),
                              mean_pga=e["pga_mean"], max_pga=e["pga_max"]))
quakes = dict(n=len(quake), matched=qrows)

# ------------------------------------------------------------------ run-out against published relations
COR = {"debris flow": (1.109, 0.857), "landslide": (2.606, 0.669), "rock avalanche": (1.758, 0.859), "rockfall": (1.999, 0.803)}
flow = []
for s in R["sites"]:
    L, Hh = s["L"], s["H"]
    row = dict(site=s["site"], volume_m3=round(s["vol_m3"]), L_m=round(L), H_m=round(Hh), HL=round(Hh / L, 3) if L else None)
    for k in ("debris flow", "landslide", "rock avalanche"):
        a, bb = COR[k]; row["H_ratio_" + k.split()[0]] = round(Hh / (a * L ** bb), 2) if L else None
    flow.append(row)
ang, ratios = [], []
for s in R["sites"]:
    for rk in s["rocks"]:
        ang.append(rk["deg"]); a, bb = COR["rockfall"]; ratios.append(rk["drop"] / (a * rk["trav"] ** bb))
ang = np.array(ang); ratios = np.array(ratios)
rock = dict(n=int(len(ang)), median_deg=round(float(np.median(ang)), 1), p10_deg=round(float(np.percentile(ang, 10)), 1), p90_deg=round(float(np.percentile(ang, 90)), 1),
            below22=round(float(np.mean(ang < 22)), 3), below27_5=round(float(np.mean(ang < 27.5)), 3), within_factor2=round(float(np.mean((ratios > .5) & (ratios < 2))), 3),
            median_ratio=round(float(np.median(ratios)), 2))
R["empirical"] = dict(roc=rocs, rain=rain, quakes=quakes, flow=flow, rock=rock, n_inventory=len(ci))

# ---- reconstructions of the reported landslides
evs = R.get("events", [])
KEY = {"debris_flow": "debris flow", "mudslide": "debris flow", "landslide": "landslide", "complex": "landslide"}
for e in evs:
    k = KEY.get(e["cat"])
    if k and e["mode"] != "rock" and e["L"] > 0 and e["nrel"] > 0:
        a_, b_ = COR[k]; e["H_ratio"] = round(e["drop"] / (a_ * e["L"] ** b_), 2)
    e["vol_gain_pct"] = round(100 * (e["vol_end"] - e["vol0"]) / e["vol0"], 1) if e["vol0"] else None
    e.pop("rain", None)
fl_ = [e for e in evs if e["mode"] != "rock"]
rat = [e["H_ratio"] for e in fl_ if "H_ratio" in e]
events_summary = dict(n=len(evs), reached=int(sum(1 for e in evs if e["reach"])), tolerance_limited=int(sum(1 for e in evs if e["tol"] < e["acc_m"])),
                      median_flow_vmax=round(float(np.median([e["vmax"] for e in fl_])), 1) if fl_ else None, median_rock_vmax=round(float(np.median([e["rock_vmax"] for e in evs if e["rocks"]])), 1) if any(e["rocks"] for e in evs) else None,
                      median_H_ratio=round(float(np.median(rat)), 2) if rat else None, within_factor3=round(float(np.mean([(r_ > 1 / 3) and (r_ < 3) for r_ in rat])), 2) if rat else None,
                      quake_events=[dict(iso=e["iso"], **e["quake"]) for e in evs if e.get("quake")])
R["empirical"]["events"] = evs; R["empirical"]["events_summary"] = events_summary
R["empirical"]["events_impact"] = R.get("events_impact", [])

# ------------------------------------------------------------------ outputs
for k in R["scen"]: R["scen"][k].pop("prob", None)
for s in R["sites"]: s.pop("rocks", None)
R.pop("hf"); R.pop("proj")
npass = sum(1 for t in R["tests"] if t["pass"]); ntot = len(R["tests"])
R["summary"] = dict(verification_passed=npass, verification_total=ntot, status="verified against analytic benchmarks; not validated against observed events")
(DOCS / "validation_results.json").write_text(json.dumps(R), encoding="utf-8")

L_ = []
L_.append("# Gilgit simulation: verification and validation report\n")
L_.append(f"Generated by `scripts/validate_simulation.py`. Verification tests passed: **{npass} of {ntot}**.\n")
L_.append("Validation status in the sense of `docs/validation_protocol.md`: `screening_only`. The code does what its equations say (verification). Whether it predicts real landslides (validation) is tested below against the little observation data held locally, and the answer is limited.\n")
L_.append("## 1. Verification (does the code solve its own equations?)\n")
L_.append("| ID | Group | Test | Expected | Got | Tolerance | Result |\n|---|---|---|---|---|---|---|")
for t in R["tests"]:
    L_.append(f"| {t['id']} | {t['group']} | {t['name']} | {t['expected']} | {t['got']} | {t['tol']} | {'pass' if t['pass'] else '**FAIL**'} |")
L_.append("\nNotes: " + "; ".join(f"{t['id']}: {t['note']}" for t in R["tests"] if t.get("note")) + "\n")
L_.append("## 2. Validation against inventory points (ROC)\n")
L_.append(f"Positives: the {len(ci)} COOLR report points inside the extent that fall on valid cells, each given a 2-cell (about 320 m) tolerance because report positions are rounded. Negatives: every valid cell, scored the same way. AUC 0.5 is no skill.\n")
L_.append("| Predictor | Points | AUC | 95 % interval | Points in top 20 % | Area in top 20 % |\n|---|---|---|---|---|---|")
for r_ in rocs:
    L_.append(f"| {r_['name']} | {r_['n']} | {r_.get('auc')} | {r_.get('lo')}–{r_.get('hi')} | {r_.get('hit_top20')} | {r_.get('area_top20')} |")
L_.append("\n## 3. Rainfall on event dates (CHIRPS area mean)\n")
for n in (1, 3, 7):
    w = rain.get(f"w{n}")
    if w: L_.append(f"- {n}-day rain at the {w['n']} rain-triggered reports: median {w['median_event']} mm vs {w['median_season']} mm on all June to September days (one-sided Mann-Whitney p = {w['p_value']}); {w['pod_p90']*100:.0f} % of events at or above the 90th percentile, {w['pod_p95']*100:.0f} % at or above the 95th.")
L_.append(f"- The default scenario delivers {rain['scenario_mm']} mm; the largest area-mean day on record is {rain['record_max_1d']} mm and the largest 3 days {rain['record_max_3d']} mm. The scenario is far outside what the CHIRPS record shows.\n")
L_.append("## 4. Shaking at earthquake-triggered reports (ShakeMap)\n")
for q_ in qrows: L_.append(f"- {q_['date']} report, {q_['event']}: PGA {q_['pga_at_report']} %g at the report (area mean {q_['mean_pga']}, peak {q_['max_pga']}); higher than {q_['pct_of_area']} % of the area.")
if not qrows: L_.append("- No earthquake-triggered report matched a downloaded ShakeMap date.")
L_.append("\n## 5. Run-out against published relations\n")
L_.append("Corominas (1996) height-versus-length fits as quoted in an EGU22 presentation (H = a L^b): debris flows 1.109 L^0.857, landslides 2.606 L^0.669, rock avalanches 1.758 L^0.859, rockfalls 1.999 L^0.803. A ratio near 1 means the simulated height drop matches the relation.\n")
L_.append("| Site | Volume m³ | L m | H m | H/L | vs debris flow | vs landslide | vs rock avalanche |\n|---|---|---|---|---|---|---|---|")
for f in flow: L_.append(f"| {f['site']} | {f['volume_m3']:,} | {f['L_m']} | {f['H_m']} | {f['HL']} | {f['H_ratio_debris']} | {f['H_ratio_landslide']} | {f['H_ratio_rock']} |")
L_.append(f"\nRockfall: {rock['n']} blocks, reach angle (source to stop) median {rock['median_deg']}° (10th to 90th percentile {rock['p10_deg']}° to {rock['p90_deg']}°); {rock['below22']*100:.0f} % below 22° and {rock['below27_5']*100:.0f} % below 27.5°, the shadow-angle values attributed to Wieczorek et al. (1998) and Evans and Hungr (1993). {rock['within_factor2']*100:.0f} % of blocks lie within a factor of 2 of the rockfall relation (median ratio {rock['median_ratio']}).\n")
L_.append("## 6. Discrete-element feasibility benchmark (browser, single thread)\n")
for bch in R["bench"]: L_.append(f"- {bch['N']:,} particles: {bch['ms_per_step']:.1f} ms per step (stable: {bch['finite']}).")
L_.append("\n## 7. What is not validated\n")
L_.append("- No mapped deposit or scar polygons exist locally, so run-out depth and extent cannot be scored (IoU, depth error).\n- Soil strength, depth and water table are scenarios, not measurements, so absolute failure probability is unvalidated.\n- Seven or fewer in-area reports, with rounded positions, limit any inventory statistic; confidence intervals above are wide.\n- Rockfall and debris-flow parameters (friction, restitution, drag) are not calibrated to any event.\n")
(DOCS / "VALIDATION_REPORT.md").write_text("\n".join(L_), encoding="utf-8")
print(f"verification {npass}/{ntot}")
for t in R["tests"]: print(("PASS " if t["pass"] else "FAIL "), t["id"], t["name"][:70], "|", t["got"])
print("ROC:", [(r_["name"], r_.get("auc")) for r_ in rocs])
print("rain:", {k: v for k, v in rain.items() if k.startswith("w")})
print("quakes:", qrows)
print("flow:", flow); print("rock:", rock); print("bench:", R["bench"])
