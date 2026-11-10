# HISAAB — Pakistan Landslide Loss & Risk (CLIMADA Core + Petals) — Executable Runbook

**How to use:** give this file to Claude and say *"run HISAAB_Landslide_CLIMADA_Runbook.md"*. Claude executes Stages 0–9 in order, stops at every **GATE**, and writes everything to `$OUT` (below). Anything marked **DOWNLOAD** is only fetched if the local check in Stage 1 fails.

**Status of this document:** written 2026-11-10 from a read-only survey of the shared drive; **revised 2026-11-10 (rev 2)** after reading two HISAAB screenshots (`Risk Assessment/1.png`, `2.png`). Nothing was installed or executed. CLIMADA API names below are from the 6.x docs/source as understood at writing; Stage 0 re-checks them and the stage code must adapt to the installed version.

**What the screenshots show about HISAAB (Pakistan risk page; sub-tabs Outlook · Hazard Explorer · Loss & Impact · Area Assessment):**
* **Hazard Explorer** lists hazards by group (Water: urban flood, glacial lake outburst, observed floods; Ground: *Earthquake years*, *Earthquake (each place at its 1-in-T shaking)*, **Landslide susceptibility**, Avalanche; Air & heat: heatwave years, heatwave 1-in-T hottest day, smog). It shows a **district choropleth** (154 districts; hatched = disputed J&K, dashed = LoC, light grey = reported zero, dark grey = unavailable), a metric dropdown (e.g. "Area at high or very high susceptibility"), an "About" button, a "show as share of district" tickbox, and a side panel of national headline numbers, each stating "N of 154 districts with values · N reported zero · N unavailable".
* **Landslide is already in HISAAB as susceptibility only** (partial coverage: 59 of 154 districts): area at high/very-high susceptibility 13.1K km², people 1.27 M, buildings (estimate) 311.3K, road length 6,498 km. The **Financial loss tile reads: "Susceptibility classes only, no return period, so no annual loss."** — this is exactly the gap this runbook fills.
* Earthquake already has a **"each place at its 1-in-T shaking"** layer, i.e. return-period hazard maps are an accepted HISAAB pattern.
* **Loss & Impact** is a **scenario replay: "What if a past disaster happened today?"** — pick an event (earthquakes 1945 Makran … 2015 Hindu Kush, hypothetical M7.0; floods 2022 … 1988); shows *Houses destroyed or badly damaged* with a *sensitivity range* (e.g. 421.6K, 214.9K–776.9K), *what happened at the time* (deaths, registered observation, cost then vs **PKR at 2025 prices**, with the note that historical exposure and valuation differ), and a table of top districts: *Houses · Damage (≈ PKR bn) · Shaking (MMI)*. Shaking source named: USGS ShakeMap.
* Not needed / out of scope: how HISAAB ingests data and the Outlook/Area Assessment tabs. The deliverables are standard files plus a plain-language integration README so the owner can integrate them (e.g. with Claude). Exposure/valuation/damage-method choices below are made here and documented, not requested.

---

## 0. Purpose, scope, honest limits

Add **landslide return-period hazard and loss** to HISAAB's *Pakistan risk → Hazard Explorer* and *Loss & Impact* tabs. HISAAB already has *susceptibility classes* (no loss); this module adds three things, in HISAAB's own style:
1. **Hazard Explorer:** "Landslide — each place at its 1-in-T rainfall-triggered occurrence" (mirrors the earthquake 1-in-T layer) plus **annual-probability** and **expected annual loss** district metrics, in the same "area / people / buildings (estimate) / road length" tiles and with the same *value / reported zero / unavailable* convention.
2. **Loss & Impact — annual view:** expected annual loss (PKR, **2025 prices**) and loss by return period per district, with a sensitivity range.
3. **Loss & Impact — scenario replay:** "What if a past landslide-triggering rainfall event happened today?" using dated inventory events and the actual rain of that day (Stage 8d). Same table layout: *Houses · Damage (≈ PKR bn) · Trigger (3-day rain, mm)*.

* **Scope:** the landslide-prone north of Pakistan only (GB, KP, AJK, Murree/Potohar fringe). Region = the extent of the existing susceptibility model (UTM43N, ~31°–37°N, ~65–74°E; see §2). Southern/Sindh/most of Balochistan/plains are *out of scope by design* (landslide-negligible); outputs there = nodata/0, and the layer's metadata says so.
* **Hazard type:** rainfall-triggered shallow landslides/debris slides (primary). Earthquake-triggered is an optional add-on (Stage 8). Not covered: rockfall, deep-seated slides, snow avalanche, GLOF, landslide-dam floods.
* **What the result is:** a **screening-level** probabilistic direct-loss estimate. It is *not calibrated to observed Pakistani landslide damage* (no such open dataset was found; see platform plan §4). Every output carries `calibration_status="not_calibrated"`, `not_for_engineering_design=true`.
* **Biggest scientific gap (stated, not hidden):** the existing LSM (`susceptibility_prob_Ensemble.tif`) is a *relative susceptibility probability*, **not** an annual probability. The inventory is small (392 points; 214 dated, 2004–2018; many with 10–50 km location error) and cannot give absolute frequencies. Annual frequency here comes from **rainfall return periods** (CHIRPS) combined with susceptibility and an inventory-calibrated rainfall trigger, then benchmarked against the UNEP/NGI global annual-probability raster. Absolute PKR/yr values are therefore **order-of-magnitude**; relative ranking between districts is more reliable than the magnitude.
* **Prior work to reuse (do not redo):** `/home/laiba123/DGX-Shared/Iliyan/Landslide/Risk Assessment/CLIMADA_Risk_Assessment_Integration_Plan.md` (AOI-scale plan for the LANDLAB tool: fragility, valuation, frequency maths). This runbook is the **national, susceptibility-driven** counterpart; it reuses that plan's valuation and AAL conventions (§4.3, §3.10 there).

---

## 1. Paths and variables

```bash
S=/home/laiba123/DGX-Shared                       # share root (also ~/Desktop/DGX-Shared on some hosts)
L=$S/Iliyan/Landslide
LSM=$S/"MERGED LANDSLIDE LAYERS"/LSM_CNN_DNN/outputs
OUT=$L/"Risk Assessment"/hisaab_landslide_run      # all products
WORK=$OUT/work                                     # intermediates
ENV=climada_ls                                     # conda env name
PY=$(conda run -n $ENV which python)               # after Stage 0
```
Rule: downloaded files go into their own new folder under `$OUT/downloads/<name>/`; scripts live in `$OUT/scripts/` (not inside download folders); run Python with `-I`-style isolation where it reads downloaded content.

---

## 1b. PREFLIGHT — run first, report blockers, then continue (added rev 3)

Run P0 → P3 **before any heavy work**. Write `$OUT/preflight_report.md` with a table `check | PASS/FAIL/WARN | detail | action taken`. **Blocker rule:** if any FAIL remains, print a BLOCKERS list (what failed, evidence = command + error text, what is needed) and **stop for the user**. WARNs are listed and the run continues with the stated fallback. The same rule applies at every later GATE: report failures with evidence; never skip silently or fabricate data.

### P0. Install and test CLIMADA (Core + Petals)
1. **Conda:** `/opt/miniconda3/condabin/conda --version` (else `which conda mamba micromamba`). Missing ⇒ blocker.
2. **Check availability first:** `conda search -c conda-forge climada`; record the newest version and its Python pins. Target 6.2.x; accept the newest available and record it.
3. **Create env:** `conda create -n climada_ls -c conda-forge python=3.11 climada -y` (log to `$OUT/logs/conda_install.log`). On solver failure retry once with `--solver libmamba`/`mamba`, then report the solver message as a blocker.
4. **Extras inside the env only:** check `conda list` and install only what is missing (rasterio, geopandas, pyarrow, scipy, matplotlib). `pip install --no-deps climada-petals==<climada version>`; if that exact version does not exist, use `pip index versions climada-petals`, take the closest compatible, record it (WARN).
5. **Import test:** `conda run -n climada_ls python -c "import climada, climada_petals; from climada_petals.hazard.landslide import Landslide; print(climada.__version__)"`. Missing Petals-only dependencies named in the traceback: install just those and log them. If `landslide.py` still fails ⇒ WARN `petals_unavailable=true` (validation/benchmark done with equivalent numpy/rasterio code, flagged). Core import failure ⇒ blocker.
6. **Signature dump** to `$OUT/logs/climada_api.txt`: `inspect.signature` + first docstring line of `Hazard.__init__`, `Centroids.from_pnt_bounds/from_meta/from_geodataframe`, `Exposures` (+`assign_centroids`), `ImpactFunc`, `ImpactFuncSet`, `ImpactCalc.impact`, `Impact.calc_freq_curve`, `Impact.impact_at_reg`, `Landslide.from_hist`, `Landslide.from_prob`, `unsequa` (`InputVar`, `CalcImpact`). **All later code uses the printed signatures, not this document's.**
7. **Smoke test T-00** (`$OUT/scripts/t00_smoke.py`, run in the env). PASS only if every assertion holds:
   * 5×5 centroids; `Hazard(haz_type="LS")` with 3 events, intensity in [0,1], frequencies 0.1/0.04/0.01;
   * 4 `Exposures` points with known values; `ImpactFunc` with `mdd = 0.1·intensity`, `paa = 1`;
   * `ImpactCalc(...).impact(save_mat=True)`; hand-calculated `at_event`, `eai_exp`, `aai_agg` match (tol 1e-9) and `aai_agg == Σ freq·at_event`;
   * `calc_freq_curve` returns monotone exceedance points;
   * a minimal `unsequa` run (2 variables, 8 samples) completes;
   * `Landslide.from_hist` on 3 synthetic points returns 3 events with nonzero intensity at the expected cells; `Landslide.from_prob` on a tiny synthetic raster (values × `corr_fact`) returns the requested number of years. Report any `date` handling problem.
   Any failure ⇒ traceback reported as a blocker; do not proceed to Stage 4.
8. Record CLIMADA, Petals, Python, GDAL and rasterio versions in the report.

### P1. CHIRPS check (`$S/"0. CHIRPS"/tiff_by_year/`)
* List year folders; confirm 1981–2025 (report missing years); count files per year (expect 365/366; report years < 360 or gaps > 2 days).
* Open one file per decade: CRS, resolution (expect ~0.05°), shape, dtype, nodata, bounds. **PASS requires bounds covering the landslide region** (all of the LSM extent converted to EPSG:4326, roughly lon 69–78°E, lat 30–38°N); partial coverage ⇒ FAIL.
* Parse the filename date pattern (unique days); confirm unit mm/day (no negatives except nodata, max < ~600); a monsoon-month sample over the north must have nonzero values.
* Read `Chirps_download.py` to record the product version (final vs preliminary) in provenance.
* Estimate time/memory for annual maxima (45 y × 365 d) and plan chunking; WARN if reading one year takes > 5 min.

### P2. Building and exposure checks
* `$S/Tasks/Reselli_AI/flood/global_data/buildings_pk/`: count `PK_*.parquet`, total size; per file read **schema only** (`pyarrow.parquet.read_schema`) and row count from metadata. Report columns, geometry encoding (WKB/WKT/native), CRS metadata, presence of `area_in_meters` (or equivalent) and a confidence column. Sample 1 000 rows: geometry validity, area range (flag < 5 m² or > 10⁴ m²), duplicates, coordinates inside Pakistan. Determine tile bounds (quadkey or sample) and test coverage of the landslide region; list gaps. FAIL if no usable area/geometry.
* Estimate the building count inside the landslide mask (sum of row counts of intersecting tiles) to choose building-level vs 1 km aggregated exposure (§4.3).
* `roads_pk/pak_roads_indexed.gpkg`: layers, feature count, CRS, road-class column. Hospitals, Schools, Telecom, Power, Rail shapefiles: open, count, CRS, geometry type; report empty/unreadable ones.
* `WorldPop_population_2020.tif`: Pakistan total (expect ≈ 2.2×10⁸; WARN if off > 15 %), nodata, CRS.
* PBS `district_housing_type.csv`: match district names to E6 (report unmatched both ways; GB/AJK expected missing ⇒ WARN, national mix used).

### P3. Remaining checks
* LSM raster: EPSG:32643, 90 m, 7333×8874, values 0–1, NaN fraction; class raster levels.
* Inventory: `Landslides_All.shp` (392 rows) + UGLC Pakistan rows: count valid dates, `loc_acc` ≤ 10 km, inside LSM extent. **WARN if usable dated events < 30** (trigger falls back to literature thresholds, flagged).
* **D1 (UNEP/NGI):** open `https://preview.grid.unep.ch/index.php?preview=data&events=landslides&evcat=2&lang=eng`, locate the precipitation-trigger download; if found, download to `$OUT/downloads/ngi_precip/` and read CRS/resolution/value range to set `corr_fact`. Not locatable after 3 attempts ⇒ WARN `ngi_benchmark_unavailable`; Stage 5 skipped (no silent substitute).
* **D3 (CPI/FX):** try to obtain Pakistan CPI 2010–2025 and PKR/EUR for 2010 and 2025 from an official source; else WARN and write 2025-price outputs as `NOT_COMPUTED` (platform-parity values shown instead).
* **D2 (JRC):** try to read the Asia/Pakistan residential max-damage value; else WARN, use 111 EUR/m² labelled "not verified".
* Resources: ≥ 50 GB free in `$OUT`, CPUs, RAM, write permission; time/size estimate for the full run.

### Preflight summary format
```
PREFLIGHT RESULT: <PASS | PASS WITH WARNINGS | BLOCKED>
BLOCKERS: <numbered: check, evidence (command + error), what is needed from the user>
WARNINGS: <numbered: check, fallback used, effect on outputs>
```

---

## 2. Dataset inventory (what exists vs. what is missing)

Verified on disk at survey time (sizes/CRS read with rasterio; "n/v" = not verified).

### 2.1 Present locally — USE (no download)

| ID | Role in CLIMADA chain | Local path | Spec (verified) | Notes |
|---|---|---|---|---|
| H1 | **Hazard spatial driver** — susceptibility probability | `$LSM/04_maps/susceptibility_prob_Ensemble.tif` | EPSG:32643, 90 m, 7333×8874, float32, bounds x −42030…756630, y 3445110…4105080 | Ensemble of CNN/DNN+ML. Relative index (0–1), not annual probability. Also `susceptibility_class_Ensemble.tif` (classes) |
| H2 | Hazard-class check / existing risk products | `$LSM/05_risk/{hazard_effective,risk_index,exposure_index,risk_class,district_risk.csv}` | same grid | Use for **sanity comparison only** (index, not PKR) |
| H3 | Conditioning layers (for QC/maps) | `$LSM/01_layers/{slope,elevation,twi,rainfall,lulc,geology,dist_faults,dist_rivers,dist_roads,...}.tif` | same 90 m grid | Slope for runout-agnostic masks (e.g. slope>5°) |
| H4 | **Landslide inventory** (Petals `from_hist`, trigger calibration, validation) | `$S/"MERGED LANDSLIDE LAYERS"/Landslide_inventories/Landslides_All.shp` | EPSG:4326, 392 pts: NASA_RPT_P 110, GLC_RAIN 104 (+local); `year` 2004–2018 (214 dated); `loc_acc` mostly "Not reported"/1–50 km; fields `event_date, cause, ls_type, fatalities, injuries, Houses_Des, Volume_M3` | Position error ≫ 90 m: always use tolerance ≥ `loc_acc` or ≥ 5 km |
| H5 | More inventory | `$L/datasets/external/uglc/UGLC_point_tile_*.gpkg` (6 tiles) | EPSG:4326 pts | **CC-BY-NC 4.0** — fine for research/internal calibration; flag to HISAAB owner before commercial redistribution of derived inventory |
| R1 | **Rainfall (trigger)** daily | `$S/"0. CHIRPS"/tiff_by_year/<1981…2025>/` | daily GeoTIFF, ~0.05° (n/v extent/naming) | Used for return-period rainfall maps and trigger calibration |
| R2 | Rainfall alt. | `$S/"0. Imerg"`, `$S/"0. ERA-5 Variables"` | n/v | optional hourly intensity check |
| R3 | Climate scenarios | `$S/CMIP6/<model>/` | n/v | Optional future-climate run (Stage 8b) |
| E1 | **Buildings (exposure points)** | `$S/Tasks/Reselli_AI/flood/global_data/buildings_pk/PK_<quadkey>.parquet` | Google Open Buildings; 7 tiles at survey time; ~5.5 GB (n/v columns: `area_in_meters`, geometry, confidence) | Same source LANDLAB uses (`layers.py`) |
| E2 | Roads | `$S/Tasks/Reselli_AI/flood/global_data/roads_pk/pak_roads_indexed.gpkg` (≈419 MB); also `$S/"4. Vector Data"/Roads/hotosm_pak_roads_lines_shp/` | line features, OSM/HOTOSM | Indicator (km at risk), not PKR |
| E3 | Facilities | `$S/"4. Vector Data"/{Hospital,Schools,Telecom Infrastructure,Electricity Transmission Line,Railway data}` | .shp | Counts at risk |
| E4 | **Population** | `$S/"3. Raster Data"/"Pop 84"/WorldPop_population_2020.tif` (also 2000–2019) ; `$LSM/05_risk/exposure/population.tif` | 4326 ~0.000985° (~100 m), 13915×19960, float32; resampled 90 m copy in LSM | Persons per cell |
| E5 | Housing construction mix | `$L/datasets/external/pbs/district_housing_type.csv`, `district_population.csv`, `district_shp/` | PBS 2023: pakka / semi-pakka / kacha households per district | Drives vulnerability mix. No row for GB/AJK → national mix (flagged) |
| E6 | **Admin boundaries (district = aggregation unit)** | `$S/"4. Vector Data"/"Pakistan Boundary"/"Pakistan, Tehsil and District Boundaries"/{Pakistan,District,Tehsil}_Boundary.shp` (164 districts, EPSG:4326, fields `name, province, division`); identical copies in `PBS DATA district/district shp/` and `$L/datasets/external/pbs/district_shp/`; `$L/datasets/national/districts.geojson` (same 164 + LSM stats) | polygons | **Use this file.** No 154-district file exists on the share (searched; other copies are the same 164 or GB/Balochistan subsets). HISAAB's map shows 154 districts; outputs are keyed by `province + name` (+ a stable `district_id` generated here) and the README states the unit count, so the owner can merge by name. Report name clashes/duplicates in the log, don't hand-crosswalk |
| T1 | Terrain | `$S/"3. Raster Data"/DEM_SRTM/pakDEM/Pak_srtm.tif` (EPSG:32642, 29 m); `.../GLO-30/*.filepart` (**incomplete download — do not use**) | | Only if slope/relief recompute is needed |
| G1 | Soil depth / texture | `$L/datasets/external/soilgrids/{bdticm_cm,clay_*,sand_*,bdod,cfvo}.tif` | EPSG:4326, 250 m | QC / optional covariates |
| G2 | Lithology | `$L/datasets/external/glim/glim_pk.tif` (+`glim_classes.json`) | EPSG:4326, 0.002° | optional |
| G3 | Faults / PGA | `$S/"4. Vector Data"/"Fault lines"`; `$L/datasets/external/{shakemap,vs30}` | | Stage 8 only |

### 2.2 MISSING — DOWNLOAD only if needed (all free)

| ID | Dataset | Why CLIMADA needs it | Where | Required spec | Priority |
|---|---|---|---|---|---|
| D1 | **UNEP/NGI global landslide hazard — precipitation-triggered** (annual probability) | Input to Petals `Landslide.from_prob`; used as **benchmark** for absolute frequency level of our calibrated hazard | UNEP GRID Europe preview: `https://preview.grid.unep.ch/index.php?preview=data&events=landslides&evcat=2&lang=eng` (Petals docs point here; the direct zip link could not be confirmed from search — open the page, locate "Landslide hazard — precipitation trigger", download GeoTIFF). Also mirrored via World Bank/GFDRR data catalogue (n/v) | GeoTIFF, ~1 km, WGS84; values = expected annual probability × 10⁶ (**check `corr_fact` against the file; Petals default differs between versions**); clip to Pakistan north bbox | **High** (benchmark) |
| D2 | **Max damage / unit construction values** | Exposure value (PKR) per building | JRC "Global flood depth-damage functions" (Huizinga et al. 2017, JRC105688) used by LANDLAB (111 EUR/m² Asia residential, 2010 prices). Landing page: `https://publications.jrc.ec.europa.eu/repository/handle/JRC105688` (n/v: tables) | Record: value per m², unit basis (floor vs footprint), price year, contents included? Or **owner-supplied PKR/m² by class — preferred if HISAAB already has exposure values** | **High** (or reuse HISAAB's own) |
| D3 | CPI / FX series (**now required**) | HISAAB reports loss in **PKR at 2025 prices**; the platform's JRC value is 2010 EUR prices × current FX, so it must be re-based to 2025 PKR | State Bank of Pakistan / PBS | annual Pakistan CPI 2010–2025; PKR/EUR (2010 and 2025); document the formula used | **High** |
| D4 | GEM Global Seismic Hazard Map (PGA, 10 % in 50 y) | Optional earthquake-triggered component (Stage 8a) | `https://www.globalquakemodel.org/gem-maps` (GEM GSHM 2018, CC-BY-SA, n/v) ; or reuse local ShakeMaps | GeoTIFF PGA (g), 475-yr | Low/optional |
| D5 | Observed damage records (calibration) | Fit/validate vulnerability and absolute loss | NDMA/PDMA/GBDMA — **no open location+intensity dataset exists**; not used, run proceeds uncalibrated | event, location, houses damaged, PKR | Ask owner; model runs without it |
| D6 | HISAAB's own exposure layers (buildings/asset values/population by district) | **Replace E1/E4/D2 so landslide loss is consistent with their other hazards** (their "Buildings (estimate)", population and road length already exist for landslide susceptibility, so they have a building/people/road exposure source) | HISAAB owner | Optional input if already available: asset value raster/table (price year, currency) | **Optional** — use only if already at hand; the run does not wait for it |
| D8 | Historical landslide event list for scenario replay (event name, date, region, observed deaths/houses damaged, cost) | Loss & Impact scenario replay (Stage 8d) | Local inventory only (`Houses_Des`, `fatalities`, `event_date`, `Volume_M3`) is sparse. **Default: select from the local inventory** the dated events (≥ year, `loc_acc` ≤ 10 km, with `fatalities`/`Houses_Des`) and use those; no external request | per event: date, district(s), source | Medium |

**GATE 1:** write `$OUT/data_manifest.csv` listing every file used (path, exists, size, CRS, res, bounds, sha256 of first 1 MB, mtime). Missing H1, H4, R1, E1, E5, E6 ⇒ stop and report. Missing D1/D2 ⇒ download (D1), or proceed with D2 = platform value and label it.

---

## 3. CLIMADA modules: what is used, why, how

Environment (Stage 0): conda-forge, Python 3.11–3.12:
```bash
conda create -n climada_ls -c conda-forge python=3.11 climada=6.2 -y   # confirm available version first: conda search -c conda-forge climada
conda run -n climada_ls pip install --no-deps climada-petals==6.2.0     # Petals pinned --no-deps; install only what landslide.py imports
```
(see §1b P0 for the full install and test procedure; pip install of CLIMADA failed on this host earlier for lack of system GDAL; conda route supplies GDAL. `/opt/miniconda3/condabin/conda` exists.) **T-00 smoke test:** `import climada, climada_petals.hazard.landslide`; build a 3×3 toy Hazard/Exposures/ImpactFunc and run `ImpactCalc`. If any step fails, fix the env before continuing; do not fall back silently.

### 3.1 CLIMADA Core

| Module | Use | Why |
|---|---|---|
| `climada.hazard.Hazard` (`haz_type="LS"`), `climada.hazard.Centroids` | Event set: one event per rainfall-return-period scenario (and per optional trigger). `intensity` = **conditional probability of landslide occurrence in the cell** given the scenario (0–1). `frequency` = annual rate of that scenario bin | CLIMADA's data model for event × location hazard; makes EAI/EP-curves standard |
| `climada.entity.Exposures` | Building points (value PKR, `impf_LS`, `region_id`=district, `construction_class`), optionally aggregated to 1 km cells for speed | Standard asset table; supports `assign_centroids` |
| `climada.entity.ImpactFunc`, `ImpactFuncSet` | Per construction class (pakka/semi/kacha): MDD = `k_c × intensity`, PAA = 1 (intensity is probability of occurrence; `k_c` = mean damage ratio given a landslide reaches the cell) | Only one intensity variable allowed; probability-of-occurrence × damage-given-occurrence is the transparent screening form. **`k_c` are assumptions (config, default pakka 0.05, semi 0.10, kacha 0.20 — placeholders, to be replaced by calibration/expert input, and varied in uncertainty analysis)** |
| `climada.engine.ImpactCalc` → `Impact` | `at_event`, `eai_exp`, `aai_agg`, `imp_mat`, `calc_freq_curve`, `impact_at_reg` | Loss per scenario, per asset, per district, expected annual impact (EAI), exceedance curve |
| `climada.engine.unsequa` (`InputVar`, `CalcImpact`) | Monte-Carlo/Sobol on `k_c`, unit value, trigger threshold, frequency scale | Gives uncertainty bands and driver ranking (not statistical confidence intervals) |
| `climada.engine.cost_benefit` / measures | **Optional** (Stage 8c) only if HISAAB wants adaptation; needs user-supplied cost | Skipped by default |
| `climada.util` (`coordinates`, raster I/O) | Reprojection/resampling helpers | |

### 3.2 CLIMADA Petals

| Module | Use | Why / limits |
|---|---|---|
| `climada_petals.hazard.landslide.Landslide.from_hist(bbox, input_gdf, res)` | Convert `Landslides_All.shp` (+UGLC Pakistan) into an LS Hazard on a ~0.0083° (~0.9 km) grid | **Validation & occurrence counts only**: hit rate of recorded slides in our hazard classes; recorded events per district; exposed buildings at recorded cells. Its frequency (`1/years span`) is *not meaningful for incomplete data* (Petals docstring) — never used as loss frequency |
| `Landslide.from_prob(bbox, path_sourcefile, corr_fact, n_years, dist)` | Run on D1 (UNEP/NGI) to get a stochastic annual-probability hazard | **Benchmark**: compare national/district EAI from our hazard vs. from NGI hazard (same exposure & damage functions). Report ratio; if within one order of magnitude, accept absolute level, else scale (see Stage 5) and report the scale factor |
| Everything else in Petals (`black_marble`, `gdp_asset`, `osm_dataloader`, `crop_production`, `supplychain`…) | **Not used** | HISAAB/LANDLAB already supply better local exposure |

Petals has **no landslide impact functions** and does no landslide physics; the damage model is ours (above).

---

## 4. Method (what Claude computes)

### 4.1 Grids
* Analysis grid = `susceptibility_prob_Ensemble.tif` grid (EPSG:32643, 90 m). Everything is resampled to it (bilinear for continuous, nearest for classes). Output COGs are also written in EPSG:4326 (web).
* Mask `M` = valid susceptibility pixels ∩ slope ≥ 5° (slope from `$LSM/01_layers/slope.tif`) ∩ not water/built-up cut-outs as in LULC (list classes used in the log).

### 4.2 Rainfall trigger scenarios (hazard frequency)
1. From CHIRPS 1981–2025 compute per-pixel annual maxima of **3-day accumulated rainfall** (also 1-day, 7-day for sensitivity). Resample to 90 m grid (nearest/bilinear; note CHIRPS ≈5 km ⇒ orographic intensity is under-resolved).
2. Fit Gumbel/GEV per pixel (Lmoments; record fit diagnostics); return levels `R_T` for T ∈ {2, 5, 10, 25, 50, 100, 200}. Years used and limitations in log.
3. **Trigger function** `g(R)=clip((R−R₀)/(R₁−R₀),0,1)` (or logistic). Calibrate `R₀,R₁` (or a regionally varying threshold, e.g. fraction of mean annual max) so that, among dated inventory events (H4/H5, 2004–2018, `loc_acc` ≤ 10 km), CHIRPS 3-day rainfall on the event date exceeds `R₀` in ≥ X % of events while exceeding it on at most Y % of all monsoon days (report ROC/AUC; choose the Youden point). If fewer than 30 usable events ⇒ use literature-based global thresholds and flag `trigger_calibrated=false`.
4. **Occurrence probability** per scenario: `P_occ(x|T) = S(x)^γ · g(R_T(x)) · c` where `S` = susceptibility, γ≥1 sharpens (default 1), `c` ∈ (0,1] = fraction of a susceptible cell that fails (areal density), set by the benchmark step (Stage 5). Output ∈[0,1].
5. **Event frequencies:** treat the T-ladder as annual-exceedance points; event rates by geometric mid-point bins (`E_{-1}=0`, `E_k=√(p_k p_{k+1})`, `E_last=1`, `f_k=E_k−E_{k−1}`), p=1/T; this is the form that makes CLIMADA exceedance functions valid. Save the bin table and the alternative trapezoid-weight EAL (platform `engine/aal.py` convention) as a model-form comparison. Result is an *expected annual-maximum-event loss*, not an annual sum (state this).

### 4.3 Exposure
* Buildings (E1) clipped to M-buffered AOI; keep `area_in_meters`; record `n_found`, `n_used`, truncation (platform keeps ≤ 40 000 per AOI; nationally process **by district and tile**, no cap, but report counts).
* Value: `V_struct = area × storeys × unit_value`, contents `0.5 × V_struct` (switchable; both totals reported), storeys default 2 with bounds {1,2}, unit value = D2 **re-based to 2025 PKR (HISAAB's reporting basis) with D3**: report both the platform-parity figure (111 EUR/m² × 322.5 PKR/EUR, mixed basis) and the aligned 2025 figure (convert at 2010 FX then inflate with Pakistan CPI, and the alternative order; show as a bracket) — the HISAAB layer uses the aligned figure **or HISAAB's own values (D6) if supplied**. Report `price_year=2025`, `fx`, `value_source`. Buildings are labelled **"estimate"** as in HISAAB.
* Class split: district shares pakka/semi/kacha from E5 (national mix for GB/AJK, flagged). Three Exposures sets with `value × share`.
* `region_id` = district from E6 (164 polygons), keyed `province|name`; tehsil optional.
* Also **population**: WorldPop 2020 → persons exposed per cell; **roads / hospitals / schools / power / telecom / rail**: counted/measured where `P_occ(T=100) ≥ 0.1` (indicators, never added to PKR).
* Performance: if buildings > ~10 M in scope, aggregate to 1 km exposure cells (sum of values, centroid points) and report the aggregation; keep building-level only for districts above a threshold or for validation.

### 4.4 Impact
`ImpactCalc(exposures_c, impf_set, hazard).impact(save_mat=True)` for each class `c`; sum. Aggregate: `aai_agg`, `eai_exp`, `at_event`, `impact_at_reg(district)`, EP curve via `calc_freq_curve` on the event-rate hazard. Also persons exposed (value=population as an Exposures set with identity impf `k=1`) → *expected annual affected population* (not casualties).

---

## 5. Stages (execution order)

| Stage | Action | Output / GATE |
|---|---|---|
| **0** | Run **§1b P0** (install + test CLIMADA/Petals, signature dump, T-00) | `env_report.txt`, `logs/climada_api.txt`. **GATE 0:** T-00 passes, else BLOCKED |
| **1** | Run **§1b P1–P3** (CHIRPS, building/exposure, LSM/inventory, NGI/CPI/JRC) then the §2 table audit: record CRS/res/bounds/NaN%/sha for every file; **download D1** (and D2/D3 if obtainable) | `preflight_report.md`, `data_manifest.csv`. **GATE 1:** BLOCKED list shown, run stops on any FAIL |
| **2** | Prep grid, mask M, district rasterisation, rainfall return levels `R_T` | `work/rain_T*.tif`, `work/mask.tif`, log with GEV diagnostics |
| **3** | Trigger calibration against inventory (Petals `from_hist` for gridded counts; hit-rate by susceptibility class; ROC for rainfall threshold) | `validation/inventory_hit_rate.csv`, `trigger_params.json`, ROC figure |
| **4** | Build hazard `P_occ(x\|T)` + event frequencies → CLIMADA `Hazard(haz_type="LS")` saved as HDF5 | `hazard_LS.hdf5`, `event_table.csv` |
| **5** | **Absolute-level benchmark:** run Petals `from_prob` on D1; compute district EAI for both hazards with the *same* exposure and damage functions; report ratio. Set `c` so national hazard-weighted annual landslide-cell probability matches D1 within a stated tolerance **only if** D1 is judged credible (document); otherwise keep `c` and publish the ratio | `benchmark_ngi.csv`, `c_scale.json` |
| **6** | Exposure build (§4.3), valuation, class split, indicators | `exposure_buildings.parquet` (or 1 km), `exposure_summary.csv`. **GATE 6:** totals vs PBS households and WorldPop sanity (±) |
| **7** | Impact (§4.4) for baseline; parity check on a few buildings by hand; uncertainty (`unsequa`, n≥1000 MC + Sobol on `k_c`, unit value, storeys, contents ratio, `R₀`, `c`, γ) | `impact_*`, `uncertainty_*` |
| **8d** | **Scenario replay (Loss & Impact style):** for each event in D8 (or, since no event list is provided, inventory events with a date and `loc_acc` ≤ 10 km): take CHIRPS 1/3-day rain on the event date, compute `P_occ` with the Stage 3 trigger, run `ImpactCalc` as a single-event Hazard; report per district *houses destroyed/badly damaged* (= buildings × P(damage state ≥ 3) proxy: mean damage ratio × count, stated), *damage PKR (2025 prices)*, *trigger rain (mm)*, and a **sensitivity range** from `unsequa`; side-by-side with observed deaths/houses/cost where documented, with HISAAB's caveat that historical and present exposure/valuation differ. Skip an event and say why if location accuracy or rainfall coverage is inadequate | `scenario_replay_<event>.csv/json` |
| **8** | Optional: (a) earthquake trigger from D4/ShakeMaps (Newmark-type probability map) as extra events; (b) CMIP6 rainfall scaling → future hazard & ΔEAI; (c) cost-benefit only with user costs | `scenario_*` |
| **9** | Export HISAAB deliverables (§6), `provenance.json`, `README_for_HISAAB.md`, QA plots | **GATE 9:** schema check (§6.4) passes |

At every GATE print a pass/fail line and stop on fail; **when stopping, print a BLOCKERS list (check, evidence, what is needed)**. At the end of a completed run also print a final **BLOCKERS & WARNINGS summary** of everything that was degraded or skipped (e.g. `ngi_benchmark_unavailable`, `petals_unavailable`, `trigger_calibrated=false`, `2025_price=NOT_COMPUTED`) and write it to `$OUT/run_report.md` and into `README_for_HISAAB.md`. Never invent data: if something cannot be computed, write `NOT_COMPUTED` + reason into the metadata.

---

## 6. Deliverables for HISAAB

### 6.1 Hazard Explorer layers (rasters)
Cloud-Optimized GeoTIFFs in EPSG:4326 (also EPSG:32643 originals), nodata = −9999, 90 m (downsample overview pyramids built-in), for the susceptible north only (outside = nodata):

| File | Content | Units / classes |
|---|---|---|
| `LS_susceptibility_class.tif` | 5-class susceptibility (very low…very high) | 1–5 + legend JSON |
| `LS_susceptibility_prob.tif` | ensemble susceptibility probability | 0–1 (index) |
| `LS_rainfall_trigger_T{10,25,50,100}.tif` | conditional landslide occurrence probability given T-yr 3-day rain (`P_occ`) | 0–1 |
| `LS_annual_prob.tif` | expected annual landslide-cell probability (= Σ f_k·P_occ,k) | yr⁻¹ (also "1-in-N yr" legend) |
| `LS_rain_3d_T{10,100}.tif` | return-level 3-day rainfall (context) | mm |
| `LS_loss_density_EAI.tif` | expected annual loss density (1 km) | PKR km⁻² yr⁻¹ |
| `LS_exposed_pop_T100.tif` | persons in cells with `P_occ(T100) ≥ threshold` | persons/cell |

Each has a sidecar `*.json` (title, unit, source datasets, version, date, `calibration_status`, caveats, colour ramp suggestion, legend breaks).

### 6.1b Hazard Explorer district metrics (match HISAAB's existing tiles)
`LS_hazard_district_metrics.csv` — one row per district (E6) × **return period T ∈ {10, 25, 50, 100}** and `annual`; for each metric also `value_status ∈ {value, reported_zero, unavailable}` (HISAAB shows these three states and counts them: "N of 154 with values · N reported zero · N unavailable"; **outside the modelled north ⇒ `unavailable`, modelled but no hazard ⇒ `reported_zero`**, never blank):
`area_km2_high_occurrence`, `share_of_district_area` (for the "show as share of district" tickbox), `people_exposed`, `buildings_exposed_estimate`, `road_km_exposed`, `hospitals/schools exposed`, `annual_probability_mean`. "High" = `P_occ ≥ thr` (default 0.1; also provide the susceptibility-class based version using HISAAB's own class cut-offs from D7 so the new tiles are comparable with the existing "high or very high susceptibility" ones). Plus an **About** text (method, data, limits) per layer.

### 6.2 Loss & Impact tables (vector + CSV)
`LS_loss_district.geojson` + `.csv` (and `LS_loss_tehsil.*`), one row per **district (E6)**; keys: `district_code, district_name, province`

| Field | Meaning |
|---|---|
| `n_buildings`, `exposed_value_pkr`, `exposed_value_in_hazard_pkr` (P_occ(T100)≥thr) | exposure |
| `eai_pkr` | expected annual impact (direct, structure+contents) |
| `eai_structure_pkr`, `eai_pkr_p05`, `eai_pkr_p50`, `eai_pkr_p95` | sensitivity band from `unsequa` |
| `loss_T10_pkr … loss_T100_pkr`, `loss_T200_pkr` | loss per return-period scenario |
| `eai_pct_of_value` | EAI ÷ exposed value |
| `pop_exposed_T100`, `exp_annual_affected_pop` | people |
| `roads_km_exposed`, `hospitals_exposed`, `schools_exposed`, `power_km`, `telecom_sites` | indicators (not PKR) |
| `rank_eai`, `rank_eai_pct` | ranking |
| `susc_class_mix` | share of area in each class |
| `price_year`, `fx`, `value_source`, `calibration_status`, `data_quality_flag` | metadata |

Also: `LS_ep_curve_national.csv` and per-province (`return_period, loss_pkr`), `LS_event_table.csv` (scenario, T, rate, national loss), `LS_top_assets.csv` (largest building-level EAI, optional), `LS_inventory_validation.csv` (hit rates), `LS_benchmark_ngi.csv`.

### 6.2b Scenario-replay output (Loss & Impact "What if a past disaster happened today?")
`LS_scenario_<event_id>.json` per event: `title, date, trigger_rain_mm, houses_destroyed_or_badly_damaged {central, low, high}, damage_pkr_2025 {central, low, high}, top_districts [{district, houses, damage_pkr_bn, trigger_mm}], what_happened_then {deaths, houses, cost_then, source, note}`, `caveats`. Field layout mirrors the earthquake/flood replay seen in HISAAB (headline number + sensitivity range, historical comparison, top-district table).

### 6.3 Metadata and provenance
`provenance.json`: software versions, dataset list with sha, parameters (`k_c`, `R₀,R₁`, γ, `c`, storeys, contents ratio, unit value), seed, runtime. Plain-language `README_for_HISAAB.md`: field dictionary, caveats (§0), how to refresh.

### 6.4 Acceptance checks (GATE 9)
1. All rasters share CRS/transform per set; values within documented ranges; no NaN inside mask.
2. Sum of district EAI = national `aai_agg` (±1e-6).
3. Monotonic: loss(T) non-decreasing (flag exceptions).
4. District `n_buildings` sums to total used; truncation reported.
5. District ranking compared with existing `district_risk.csv` (Spearman reported, not required to match).
6. Inventory hit-rate: recorded landslides fall in High/Very-high classes at a rate above area share (report lift); if not, flag.
7. No PKR value mixes price years; indicators are never summed into PKR.

### 6.5 Integration README (generated in Stage 9, replaces any request to the owner)
`README_for_HISAAB.md` must let the owner (or Claude working for them) integrate without asking questions: file list, CRS/units/nodata, field dictionary, the value/reported_zero/unavailable convention, district keys (`province|name`, 164 units vs the 154 shown on the map: merge by name, unmatched listed in `district_key_report.csv`), price basis (2025 PKR), how to re-run, and an explicit mapping to the visible HISAAB tiles (area, people, buildings (estimate), road length, financial loss). Where a HISAAB-side choice is unknown, the runbook picks a documented default (class cut-offs: susceptibility class 4–5 = "high or very high"; exposure: E1/E4/E2 with stated valuation) and records it.

---

## 7. Inputs → outputs summary (CLIMADA view)

| CLIMADA object | Inputs | Produced |
|---|---|---|
| `Hazard` (LS) | H1 susceptibility, R1 CHIRPS return levels, trigger params (H4/H5), scale `c`, T-ladder with event rates | intensity matrix `P_occ` [events × centroids], frequency per event |
| `Exposures` ×3 | E1 buildings (or HISAAB assets), D2/D6 values, E5 class shares, E6 districts | value per asset, `impf_LS`, `region_id` |
| `ImpactFuncSet` | `k_c` per class | MDD curves |
| `Impact` | above | `at_event`, `eai_exp`, `aai_agg`, regional sums, EP curve |
| `Landslide.from_hist` | H4/H5 | validation hazard (counts per cell) |
| `Landslide.from_prob` | D1 | benchmark hazard |
| `unsequa` | parameter ranges | Monte-Carlo samples, Sobol indices |

---

## 8. Known risks / things to tell the HISAAB owner

1. Susceptibility is not frequency; absolute PKR/yr is order-of-magnitude. State this on the layer info panel.
2. Inventory is thin and positionally coarse — calibration is weak; more complete national inventory (NDMA, GSP, KKH/NHA road-blockage logs) would improve it most.
3. Damage-given-occurrence `k_c` are assumptions; no Pakistani damage data. If HISAAB has loss records, calibrate `k_c`.
4. Valuation basis (2010 EUR price × current FX) mixes years; contents may be double-counted; storeys unknown. Prefer HISAAB's own exposure values.
5. CHIRPS (~5 km) misses localized cloudbursts; GB/Chitral rainfall is poorly constrained.
6. Not modelled: rockfall, deep-seated slides, glacial/GLOF, landslide dams, cascading flood, indirect/business-interruption loss, casualties.
7. UGLC licence is non-commercial.
8. CLIMADA API names must be re-verified against the installed version (Stage 0) — signatures in 6.x changed for measures and Hazard fields.
9. Boundaries: only the 164-district file exists locally; HISAAB's map shows 154. Merge is by `province|name`; mismatches are reported, not guessed.
10. HISAAB's existing landslide susceptibility tiles (59/154 districts) may come from a different model/cut-offs than the 90 m ensemble used here; the two may disagree if shown side by side (stated in the README).
11. Scenario replay depends on dated events with locations good to ~10 km and CHIRPS (~5 km) rain; results are indicative and must carry HISAAB-style "historical exposure and valuation differ" wording.

---

## 9. References
* CLIMADA Petals landslide module docs: https://climada-petals.readthedocs.io/en/latest/_modules/climada_petals/hazard/landslide.html
* UNEP GRID precipitation-triggered landslide hazard (NGI): https://preview.grid.unep.ch/index.php?preview=data&events=landslides&evcat=2&lang=eng
* JRC depth-damage functions / max damage values (Huizinga et al. 2017): https://publications.jrc.ec.europa.eu/repository/handle/JRC105688 (not opened)
* Platform plan: `Risk Assessment/CLIMADA_Risk_Assessment_Integration_Plan.md`; data registry `docs/data_registry.yaml` (D01–D40)
