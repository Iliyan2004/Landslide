"""Build docs/TECHNICAL_REFERENCE.md, .html and .pdf for the Gilgit Landslide Platform.

The chapters are written in docs/techref/part*.md. Numbers and tables that come from data or results (validation tests, events,
datasets, rainfall thresholds, hourly analysis) are filled in from the real files, so the document cannot drift from them:
  {{key}}            a number from the page data, results or the file system
  {{TBL_xxx}}        a generated table
The PDF is printed by headless Chrome from the HTML (A4, running footer with page numbers).
Usage: python -X utf8 scripts/build_technical_reference.py [--no-pdf]
"""
import base64, datetime as dt, html, json, re, subprocess, sys, tempfile
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[2]
LP = ROOT / "landslide-platform"
DOCS = LP / "docs"
PARTS = sorted((DOCS / "techref").glob("part*.md"), key=lambda p: int(re.search(r"part(\d+)", p.name).group(1)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DATA = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit")

page = (LP / "site/index.html").read_text(encoding="utf-8")
D = json.loads(re.search(r"const D=(\{.*?\});\nconst S=", page, re.S).group(1))
VR = json.loads((DOCS / "validation_results.json").read_text(encoding="utf-8"))
HC = json.loads((DOCS / "hourly_climate_results.json").read_text(encoding="utf-8"))
CAL = json.loads((DOCS / "calibration_results.json").read_text(encoding="utf-8"))
S = D["stats"]
f0 = lambda v: f"{v:,.0f}"
f1 = lambda v: f"{v:,.1f}"
f2 = lambda v: f"{v:,.2f}"

def table(head, rows, align=None):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(("---:" if (align and align[i] == "r") else "---") for i in range(len(head))) + "|"]
    nw = lambda c: re.sub(r"^(\d{4}-\d\d-\d\d)$", lambda m: '<span class="nw">' + m.group(1) + '</span>', str(c).replace("|", "/"))
    for r in rows: out.append("| " + " | ".join(nw(c) for c in r) + " |")
    return "\n".join(out)

T = {}
# ---------------------------------------------------------------- verification tests
T["TBL_TESTS"] = table(["ID", "Group", "What is checked", "Expected", "Got", "Tolerance", "Result"],
    [[t["id"], t["group"], t["name"], t["expected"], (f"{t['got']:.4g}" if isinstance(t["got"], (int, float)) else t["got"]), t["tol"], "pass" if t["pass"] else "FAIL"] for t in VR["tests"]])
T["TBL_TEST_NOTES"] = "\n".join(f"- **{t['id']}**: {t['note']}" for t in VR["tests"] if t.get("note"))
# ---------------------------------------------------------------- ROC
T["TBL_ROC"] = table(["Predictor", "Points", "AUC", "95 % interval", "Points in top 20 %", "Area in top 20 %"],
    [[r["name"], r["n"], r["auc"], f"{r['lo']}-{r['hi']}", r["hit_top20"], r["area_top20"]] for r in VR["empirical"]["roc"]])
# ---------------------------------------------------------------- events
ev = VR["empirical"]["events"]
T["TBL_EVENTS"] = table(["Date", "Type and trigger", "Size class, report accuracy", "Mode", "Release m3", "Peak m/s", "Mean distance m", "Reached", "Fall-height ratio", "Pore ratio"],
    [[e["iso"], f"{e['cat'].replace('_', ' ')}, {e['trig']}", f"{e['size'].replace('_', ' ')}, {e['acc']}", e["mode"], f0(e["vol0"]),
      (f"{e['rock_vmax']:.1f} (block)" if e["mode"] == "rock" else f"{e['vmax']:.1f}"), f0(e["Lm"]), "yes" if e["reach"] else "no", e.get("H_ratio", ""), f"{e['lambda']:.2f}"] for e in ev], "lllrrrrlrr")
# ---------------------------------------------------------------- ShakeMaps
T["TBL_SHAKE"] = table(["ShakeMap event", "Date", "Magnitude", "Place", "Depth km", "PGA mean %g", "PGA max %g", "MMI max", "Role"],
    [[s["id"], s["date"], s["mag"], s["place"].replace("?", "a"), s["depth"], s["pga_mean"], s["pga_max"], s["mmi_max"], "most recent covering the area" if s["recent"] else "strongest at the area"] for s in D["shake"]])
# ---------------------------------------------------------------- GLiM and WorldCover
LIT = {"su": "Unconsolidated sediments", "ss": "Siliciclastic sedimentary", "sm": "Mixed sedimentary", "sc": "Carbonate sedimentary", "py": "Pyroclastics", "va": "Acid volcanics", "vi": "Intermediate volcanics", "vb": "Basic volcanics", "pa": "Acid plutonics", "pi": "Intermediate plutonics", "pb": "Basic plutonics", "mt": "Metamorphics", "ev": "Evaporites", "wb": "Water bodies", "ig": "Ice and glaciers", "nd": "No data"}
RANK = {"su": 5, "ss": 3, "sm": 3, "sc": 2, "py": 4, "va": 2, "vi": 2, "vb": 2, "pa": 1, "pi": 1, "pb": 1, "mt": 3, "ev": 3}
tot = sum(D["lit_area"].values())
T["TBL_GLIM"] = table(["GLiM code", "Class", "Area km2", "Share of extent", "Rank used"], [[k, LIT.get(k, k), f1(v), f"{v/tot*100:.1f} %", RANK.get(k, "unrated")] for k, v in sorted(D["lit_area"].items(), key=lambda x: -x[1])], "llrrr")
LC = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice", 80: "Open water", 90: "Herbaceous wetland", 100: "Moss and lichen"}
ROOT_C = {1: 5, 2: 3, 3: 2, 4: 1}
lt = sum(D["lc_area"].values())
T["TBL_WC"] = table(["WorldCover code", "Class", "Area km2", "Share", "Root cohesion kPa", "In soil-stability model"],
    [[k, LC.get(int(k), k), f1(v), f"{v/lt*100:.1f} %", ROOT_C.get(int(k) // 10, 0), "no (snow, ice or water)" if int(k) in (70, 80) else "yes, on 10-50 degree slopes"] for k, v in sorted(D["lc_area"].items(), key=lambda x: int(x[0]))], "rlrrrl")
# ---------------------------------------------------------------- rainfall threshold
T["TBL_RTHR"] = table(["Duration (days)", "Threshold mm/day", "Events above", "Other season days above", "TSS", "AUC"],
    [[r["d"], f2(r["thr"]), f"{r['pod']*100:.0f} %", f"{r['pofd']*100:.1f} %", f2(r["tss"]), f2(r["auc"])] for r in D["rthr"]["per"]], "rrrrrr")
# ---------------------------------------------------------------- hourly
G = HC["groups"]["rain-type triggers"]
T["TBL_HOURLY"] = table(["Predictor", "AUC", "Best threshold", "Hits", "False alarms", "TSS"], [[r["feature"], f"{r['auc']:.3f}", r["threshold"], f"{r['pod']*100:.0f} %", f"{r['pofd']*100:.0f} %", f"{r['tss']:.2f}"] for r in G["rows"]], "lrrrrr")
GA = HC["groups"]["all reports"]
T["TBL_HOURLY_ALL"] = table(["Predictor", "AUC", "Best threshold", "Hits", "False alarms", "TSS"], [[r["feature"], f"{r['auc']:.3f}", r["threshold"], f"{r['pod']*100:.0f} %", f"{r['pofd']*100:.0f} %", f"{r['tss']:.2f}"] for r in GA["rows"]], "lrrrrr")
T["TBL_HMODELS"] = table(["Predictor set", "All reports (AUC)", "Rain-type reports (AUC)"], [[k, HC["models"]["all reports"][k], HC["models"]["rain-type triggers"][k]] for k in HC["models"]["all reports"]], "lrr")
# ---------------------------------------------------------------- calibration
cb = CAL["calibration"]
T["TBL_CAL"] = table(["Soil set", "Depth m", "Cohesion kPa", "Friction deg", "Saturation", "Storm mm", "AUC train", "AUC new ground", "AUC new window"],
    [["Default", *cb["default"]["theta"], f2(cb["default"]["auc_train"]), f2(cb["default"]["auc_test_new_ground"]), f2(cb["default"]["auc_test_new_window"])],
     ["Best of 300", *cb["best"]["theta"], f2(cb["best"]["auc_train"]), f2(cb["best"]["auc_test_new_ground"]), f2(cb["best"]["auc_test_new_window"])],
     ["Slope only", "", "", "", "", "", f2(cb["slope_only"]["auc_train"]), f2(cb["slope_only"]["auc_test_new_ground"]), f2(cb["slope_only"]["auc_test_new_window"])]], "lrrrrrrrr")
T["TBL_CALR"] = table(["Parameter", "Range of the best 5 % of draws"], [[k.replace("_", " "), f"{v[0]} to {v[1]}"] for k, v in cb["top5pct_ranges"].items()])
# ---------------------------------------------------------------- run-out sites
T["TBL_FLOW"] = table(["Site", "Volume m3", "L m", "H m", "H/L", "vs debris flow", "vs landslide", "vs rock avalanche"],
    [[f["site"], f0(f["volume_m3"]), f0(f["L_m"]), f0(f["H_m"]), f["HL"], f["H_ratio_debris"], f["H_ratio_landslide"], f["H_ratio_rock"]] for f in VR["empirical"]["flow"]], "rrrrrrrr")
# ---------------------------------------------------------------- files
def size(p):
    try: return f"{p.stat().st_size/1e6:,.1f} MB" if p.stat().st_size > 1e6 else f"{p.stat().st_size/1e3:,.1f} kB"
    except Exception: return "n/a"
files = [(DATA / n, d) for n, d in [("worldcover_2021.tif", "ESA WorldCover 2021, uint8, 26.6 m grid"), ("worldpop_2020.tif", "WorldPop 2020, float32, 100 m resampled to the grid"), ("open_buildings_v3.geojson", "Open Buildings v3 footprints, confidence 0.7 or more"),
         ("gem_active_faults_pakistan.gpkg", "GEM harmonised active faults, Pakistan window"), ("chirps_daily_aoi_mean.csv", "CHIRPS daily, area mean, 1981 to present"), ("embedding_2017_int8.tif", "Satellite embedding 2017, 64 bands int8"), ("embedding_2024_int8.tif", "Satellite embedding 2024, 64 bands int8"),
         ("s2_change_2017_2020.tif", "Sentinel-2 dNDVI, dBSI, NDVI pre, BSI post, 2017 to 2020"), ("s2_change_2020_2024.tif", "Sentinel-2 change, 2020 to 2024"), ("shakemap_summary.csv", "ShakeMap summary for 164 events"), ("glim/glim_gilgit_bbox.gpkg", "GLiM lithology clipped to the area"),
         ("osm/pakistan.gpkg", "Geofabrik OSM Pakistan"), ("hourly_climate.npz", "ERA5-Land hourly windows, 752 x 720 x 5"), ("soil_texture_250m.tif", "SoilGrids sand, silt, clay 0-30 cm, 250 m"), ("soil_factors.npz", "Cohesion factor and friction offset on the 160 m grid"), ("validation_inputs.npz", "Screening score, slope, nodata and inventory cells for validation")]]
T["TBL_FILES"] = table(["File (under D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit)", "Size", "Content"], [[p.relative_to(DATA).as_posix(), size(p), d] for p, d in files], "lrl")
T["TBL_SCRIPTS"] = table(["Script", "Lines", "Purpose"], [[p.name, len(p.read_text(encoding="utf-8").splitlines()), d] for p, d in [
    (LP / "scripts/build_dashboard_page.py", "Builds every dashboard array and writes the page"), (LP / "scripts/dashboard_template.html", "The dashboard: CSS, markup and all browser code"), (LP / "scripts/download_gilgit_data.py", "Earth Engine and GitHub downloads on the DEM grid"),
    (LP / "scripts/download_shakemaps.py", "USGS ShakeMap grids"), (LP / "scripts/download_s2_change.py", "Sentinel-2 change layers"), (LP / "scripts/download_hourly_climate.py", "ERA5-Land hourly windows for reports and controls"), (LP / "scripts/download_soil_texture.py", "SoilGrids texture"),
    (LP / "scripts/analyze_hourly_climate.py", "Hourly rain, soil water and snowmelt skill"), (LP / "scripts/calibrate_stability.py", "Scar candidates and soil calibration"), (LP / "scripts/validate_simulation.py", "Runs the harness and empirical checks, writes the report"),
    (LP / "scripts/validation_harness.js", "Verification tests V1-V36 in headless Chrome"), (LP / "scripts/build_registries.py", "Builds data and model registries"), (LP / "scripts/run_pipeline.py", "Synthetic end-to-end demo of the backend"), (LP / "scripts/aoi_builder.py", "Builds the data package and page for a drawn area"), (LP / "scripts/aoi_ee.py", "Earth Engine layers on an area's grid"), (LP / "scripts/aoi_server.py", "Serves pages and builds areas on request"), (LP / "scripts/prepare_pakistan.py", "National lithology, rivers and outline"), (LP / "scripts/download_shakemaps_pk.py", "National ShakeMap library"), (LP / "scripts/page_check.py", "Headless Chrome page check"), (LP / "scripts/infra_data.py", "Roads, bridges, facilities, places and building footprints for the impact assessment"), (LP / "scripts/aoi_hist.py", "Before and after imagery and change mapping for historical events"), (LP / "scripts/build_technical_reference.py", "This document")]], "lrl")

# ---------------------------------------------------------------- scalar values
rr = VR["empirical"]["rain"]["rows"]
T["TBL_RAINEV"] = table(["Report date", "Trigger", "Rain that day mm", "Percentile (season days)", "3 days mm", "Percentile", "7 days mm", "Percentile"], [[r["date"], r["trigger"], r["mm1"], f"{r['pct1']:.0f}", r["mm3"], f"{r['pct3']:.0f}", r["mm7"], f"{r['pct7']:.0f}"] for r in rr], "llrrrrrr")
import rasterio as _rio
with _rio.open(LP / "datasets/dem_30m.tif") as _d: _pkw, _pkh = _d.width, _d.height
_shk = list((LP / "datasets/raw/pakistan/shakemap").glob("*.npz"))
V = {"pk_dem_w": f0(_pkw), "pk_dem_h": f0(_pkh), "pk_rivers": "83,975", "pk_shake": len(_shk), "pk_shake_mb": f0(sum(p.stat().st_size for p in _shk) / 1e6), "pk_pts": len(D["allpts"]) if D.get("allpts") else len(D["pts"]), "n_roads": len(D["infra"]["roads"]), "n_pois": len(D["infra"]["pois"]), "n_places": len(D["infra"]["places"]), "page_mb": f1((LP / "docs/gilgit_landslide_dashboard.html").stat().st_size / 1e6), "hf_w": D["elev53"]["w"], "hf_h": D["elev53"]["h"], "hf_res": f1(D["elev53"]["res"]), "area_km2": f0(S["area_km2"]), "zmin": f0(S["zmin"]), "zmax": f0(S["zmax"]), "zmean": f0(S["zmean"]), "slope_mean": f1(S["slope_mean_pct"]), "res": f"{S['res']:.2f}", "W": S["W"], "H": S["H"],
     "cls0": f1(S["cls_pct"][0]), "cls1": f1(S["cls_pct"][1]), "cls2": f1(S["cls_pct"][2]), "cls3": f1(S["cls_pct"][3]),
     "scr0": f1(D["scr_pct"][0]), "scr1": f1(D["scr_pct"][1]), "scr2": f1(D["scr_pct"][2]), "scr3": f1(D["scr_pct"][3]), "unk": f1(D["unk_pct"]),
     "bld": f0(D["bld_total"]), "pop": f0(D["pop_total"]), "nfaults": len(D["faults"]), "nfaults_near": D["faults_near"], "w2": D["w"], "h2": D["h"], "cell_m": f1(D["cell_m"]), "cells": f0(D["w"] * D["h"]),
     "npts": len(D["pts"]), "npts_in": len([p for p in D["pts"] if p["inside"]]), "nq": len(D["qs"]), "eq_total": f0(S["eq_total"]), "nshake": len(D["shake"]),
     "loo_med": f0(D["emb"]["loo_median"] * 100), "loo_t10": f0(D["emb"]["loo_hit_top10"] * 100), "loo_t25": f0(D["emb"]["loo_hit_top25"] * 100), "slope_med": f0(D["emb"]["slope_median"] * 100),
     "scr_med": f0(D["scr_val"]["median"] * 100), "scr_slope_med": f0(D["scr_val"]["slope_median"] * 100),
     "crest": f1(D["amp_stats"]["crest_pct"]), "valley": f1(D["amp_stats"]["valley_pct"]), "soft": f1(D["amp_stats"]["soft_pct"]), "semi": f1(D["amp_stats"]["semi_pct"]),
     "rain_first": D["rain"]["first"], "rain_last": D["rain"]["last"], "rain_max1": D["rain"]["max1"], "rain_max1d": D["rain"]["max1_date"], "rain_max3": D["rain"]["max3"], "rain_max7": D["rain"]["max7"], "rain_p99": D["rain"]["p99_wet"], "rain_wet": f1(D["rain"]["wet_frac"] * 100),
     "nthr": D["rthr"]["n_events"], "nrivers": len(D["rivers"]), "ntests": VR["summary"]["verification_total"], "npass": VR["summary"]["verification_passed"],
     "scarA": f1(CAL["windows"]["A"]["scar_km2"]), "scarB": f1(CAL["windows"]["B"]["scar_km2"]), "pyjs": f"{CAL['python_vs_browser_max_abs_diff']:.4f}",
     "ev_reached": VR["empirical"]["events_summary"]["reached"], "ev_n": VR["empirical"]["events_summary"]["n"], "ev_tol": VR["empirical"]["events_summary"]["tolerance_limited"], "ev_vflow": VR["empirical"]["events_summary"]["median_flow_vmax"], "ev_vrock": VR["empirical"]["events_summary"]["median_rock_vmax"], "ev_hr": VR["empirical"]["events_summary"]["median_H_ratio"],
     "hr_n": HC["n_reports"], "hr_c": HC["n_controls"], "date": dt.date.today().strftime("%d %B %Y")}
V.update(T)

text = "\n\n".join(p.read_text(encoding="utf-8") for p in PARTS)
def sub(m):
    k = m.group(1)
    if k not in V: raise SystemExit(f"unknown placeholder {{{{{k}}}}}")
    return str(V[k])
text = re.sub(r"\{\{(\w+)\}\}", sub, text)
(DOCS / "TECHNICAL_REFERENCE.md").write_text(text, encoding="utf-8")

# ---------------------------------------------------------------- HTML
md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"], extension_configs={"toc": {"toc_depth": "1-2", "permalink": False}})
body = md.convert(text)
CSS = """
@page{size:A4;margin:20mm 17mm 20mm 17mm;@bottom-center{content:"Pakistan Landslide Platform Technical Reference \\00B7 Page " counter(page);font:8pt Arial,sans-serif;color:#667}}
@page:first{@bottom-center{content:""}}
html{font:10pt/1.5 'Segoe UI',Arial,sans-serif;color:#1b2430}
body{margin:0}
h1{font:700 19pt/1.2 'Segoe UI',Arial;color:#0b3a4a;border-bottom:2px solid #0b3a4a;padding-bottom:4pt;margin:26pt 0 8pt;break-before:page;break-after:avoid}
h1.part{font-size:23pt;border:0;color:#0b3a4a;margin-top:140pt}
h2{font:700 13pt/1.25 'Segoe UI',Arial;color:#0e5a70;margin:16pt 0 4pt;break-after:avoid}
h3{font:700 10.5pt/1.3 'Segoe UI',Arial;color:#1b3a4a;margin:11pt 0 3pt;break-after:avoid}
p{margin:0 0 6pt;orphans:3;widows:3}
li{margin:0 0 2pt}
code{font:8.6pt Consolas,'Courier New',monospace;background:#eef2f4;padding:0 2pt;border-radius:2pt}
pre{font:8pt/1.35 Consolas,'Courier New',monospace;background:#f2f5f7;border:1px solid #d5dde2;border-radius:3pt;padding:6pt 8pt;white-space:pre-wrap;break-inside:avoid}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:6pt 0 10pt;font-size:8pt;line-height:1.35}
th{background:#0b3a4a;color:#fff;text-align:left;padding:3pt 4pt;font-weight:600}
td{border-bottom:1px solid #d9e0e5;padding:2.5pt 4pt;vertical-align:top}
tr{break-inside:avoid}
tr:nth-child(even) td{background:#f6f9fa}
blockquote{margin:6pt 0;padding:4pt 9pt;border-left:3pt solid #e0a030;background:#fff8e8;color:#3a2f10}
.cover{height:240mm;display:flex;flex-direction:column;justify-content:center;break-after:page}
.cover .k{font:700 10pt Arial;letter-spacing:.2em;color:#0e8ea0}
.cover h1{border:0;font-size:36pt;color:#0b3a4a;margin:6pt 0 2pt;break-before:auto}
.cover .s{font:600 15pt/1.3 Arial;color:#0e5a70;margin:0 0 20pt}
.cover p{font-size:11pt;color:#334;max-width:150mm}
.toc{break-after:page}.toc ul{list-style:none;padding-left:0}.toc ul ul{padding-left:14pt}.toc>ul>li{margin-top:6pt;font-weight:700}.toc>ul>li>ul>li{font-weight:400}
.toc a{color:#1b2430;text-decoration:none}
a{color:#0e5a70}
.nw{white-space:nowrap}
"""
toc = md.toc
html_doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pakistan Landslide Platform: Technical Reference</title><style>{CSS}</style></head><body>
<div class="cover"><div class="k">TECHNICAL REFERENCE &amp; SYSTEM DOCUMENTATION</div><h1>Pakistan Landslide Platform</h1><div class="s">Terrain screening, scenario simulation, 3D failure replay and validation for any area of Pakistan, with a Gilgit pilot</div>
<p>Complete technical reference covering the architecture, every dataset, every model and formula in use, every control in the dashboard, the backend library, the verification and validation record, the design decisions, and the stated limitations.</p>
<p>Edition of {V['date']}. Written against the code and data as they stand on that date.</p></div>
<div class="toc"><h1 style="break-before:auto;margin-top:0">Contents</h1>{toc}</div>
{body}</body></html>"""
(DOCS / "TECHNICAL_REFERENCE.html").write_text(html_doc, encoding="utf-8")
print("wrote md and html;", len(text.split()), "words")
if "--no-pdf" in sys.argv: sys.exit(0)

pdf = DOCS / "Pakistan_Landslide_Platform_Technical_Reference.pdf"
prof = tempfile.mkdtemp(prefix="chrome_pdf_")
r = subprocess.run([CHROME, "--headless=new", f"--user-data-dir={prof}", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", (DOCS / "TECHNICAL_REFERENCE.html").as_uri()], capture_output=True, text=True, timeout=300)
print("pdf", pdf, pdf.exists() and f"{pdf.stat().st_size/1e6:.1f} MB", r.stderr[-300:] if not pdf.exists() else "")
