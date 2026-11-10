# CLIMADA Risk and Loss Module for LANDLAB — Integration Plan (revision 3)

**Status:** methodology and architecture only. Nothing in the platform was changed and no platform code was run. (Read-only checks were made of file listings, run outputs, a web search for citations, and one `pip install --dry-run` — see §5.1.)
**Revision 3.1 (this edit):** the four components Tier 1/2 indicative loss, time-dependent damage, building valuation and annual loss frequencies were reviewed against the platform code and fully specified (§3.0 audit table, §3.4a, §3.5, §3.8–3.10, tests T-13…T-16). Unresolved facts are marked as checks, not assumed (JRC contents/country value, `return_period_table` output keys).
**Revision 3 changes:** literature citations checked against the publishers' pages (two were wrong and are corrected, §12); the module is **AOI-agnostic** (any user-drawn area, §1.6); the reason for a separate CLIMADA environment is now evidence-based and stated as operational, not scientific (§5.1); NDMA/PDMA records were searched and are **not used** because no usable open dataset exists (§4, §7); previously unverified questions were answered from the folder (§11).
**Platform audited:** `/home/laiba123/DGX-Shared/Iliyan/Landslide/` (LANDLAB model version 2.5.0 in `runs/*/manifest.json`).
**Source specification:** `climada_risk_assessment_MASTER_PROMPT.md` (same folder), cut down to what a landslide platform can support.
**CLIMADA facts** come from reading the `climada==6.2.0` and `climada-petals==6.2.0` wheel sources. CLIMADA is **not installed here and nothing was executed**; every API statement means "present in the 6.2.0 source", not "tested" (smoke test T-00 comes first).

---

## 0. Scope, hard rules and what changed from revision 1

### 0.1 What the module does

For the area (AOI) the user drew and the simulation the user ran on it, the module produces a loss estimate, a damage map, and risk indicators, using CLIMADA Core for the impact/uncertainty/cost-benefit machinery and Petals only where it adds something (§2.3). It covers **every tier** the platform has:

| Platform tier | Physical output available | Loss product the module may give | Strength of the result |
|---|---|---|---|
| **3 Physics** (rain run, `landslide_physics_run`) | depth `hmax`, speed `vmax`, deposit, scour, failure time, FS | **Modelled direct loss**: damage ratio per building from the platform's fragility, valued; plus existing indicators (roads blocked, access, facilities, population) | Highest; still uncalibrated (screening) |
| **4 Quake** (`mode quake/both`, same runout engine) | same as Tier 3 plus `pga_g` | Same as Tier 3, labelled with the trigger | Same; no site amplification in PGA |
| **5 Mitigate** (Tier 3 run with `params.interventions`) | same as Tier 3, changed by barriers / nature-based levers | Same as Tier 3, plus **paired avoided loss** against the matching unmitigated run | Same; effect sizes are the user's scenario inputs |
| **1 Screening** (`landslide_aoi`) | ensemble `frac_lt1`, FS percentiles, reach-angle envelope `runout_freq`, population in envelope; **no depth, no speed** | **Exposed value at risk** (always) and an **indicative loss range** (only when reference damage data exist, §3.8) | Screening upper-envelope; not damage-modelled |
| **2 Instant** (stability library) | FS maps for a ladder of 24 h rain totals, critical-rain map; **no runout, and not currently saved to disk** | Exposed value at risk and indicative loss range **per rain total**, from the same method as Tier 1 | Screening; needs one small additive save (§1.4) |

### 0.2 Hard rules (enforced in code, §5.2)

1. **No simulation, no loss.** A risk run can only be created from a finished, saved platform run (or saved Tier 2 library) whose AOI is the area the user selected. No run ⇒ the Risk & Loss controls are disabled and the API answers `409 no_completed_simulation`. The module never starts or reruns a simulation.
2. **The AOI is the run's AOI.** Exposure is clipped to the run's saved polygon (`geom.json`, `aoi_sha256`). The loss cannot be computed for a different polygon than the simulated one.
3. **Only landslide-relevant, already-supported losses.** Structure + contents loss and the platform's existing crop rule (passed through, not extended); roads and facilities as physical-impact indicators (blocked length, cut-off, hospitals/schools hit), **not** as PKR repair costs; population as exposed counts. No new road, bridge, utility, telecom, agriculture, business-interruption, supply-chain or casualty models (none exist in the platform, no data to support them).
4. **No annual figure without a stated frequency basis.** Deterministic runs get scenario losses only.
5. **Every output carries** `tier`, `run_id`, `calibration_status = not_calibrated`, `validation_status = screening_only`, `not_for_engineering_design = true`, price year and FX basis.
6. **Do not mix price years or valuation bases silently** (§3.5).

### 0.3 Corrections made in this revision (summary)

| Revision-1 problem | Fix in this revision |
|---|---|
| Plan covered roads/bridges/utilities/agriculture loss, rockfall, deep-seated, business interruption, supply chain, casualty fields | Removed (platform has none of these models). Kept only existing platform components as pass-through indicators |
| Tier 1 and Tier 2 were not handled; Tier 4/5 only implied | Per-tier method added (§0.1, §3.8, §3.9); explicit gating (§0.2, §5.2) |
| MDR raster was built from `hmax`, `vmax` **before** the platform's 3×3 maximum filter, which would not reproduce platform numbers (MDR is non-linear in h, v) | Filter `hmax` and `vmax` first, then compute damage (§3.3) |
| Exposure re-derived by nearest-centroid assignment | Reuse the run's own saved building list (`impacts.json.gz`, which stores `rr`, `cc`) and set the centroid index directly — identical exposure and cell mapping (§3.2) |
| Dynamic pressure "ρv²/1000" vs "ρv²/2" shown as an unresolved error | Interpreted: the code is `p = C_d · ½ρv²` with `C_d = 2` (= ρv²), a drag-type impact coefficient; documentation (ch. 19) is what must be corrected. Coefficient becomes an explicit, sensitivity-tested parameter (§3.3) |
| Max depth and max speed treated as simultaneous | Bracketed with a time-joint alternative from saved frames (§3.3) |
| Frequency step formula and trapezoid mixed | One clearly defined frequency model per use, both reported (§3.10) |
| Petals presented as optional extra without a decision rule | Explicit adopt/skip rule with a measurable test (§2.3) |
| Climate, adaptation, early-warning, "future exposure growth" sections had no platform support | Reduced to comparisons of runs the platform can already make (§3.11, §3.12) |
| Many speculative datasets and citations | Dataset list cut to what the module reads or genuinely lacks (§4) |

---

## 1. Existing platform assessment

### 1.1 What exists (read from code and docs)

| Component | Where | Used by the module? |
|---|---|---|
| CNN/DNN susceptibility (north only) | Tier 1 | **No** — a probability index, not a hazard intensity or an annual probability (README rule). In the inspected Tier 1 run 99.9 % of the AOI has probability > 0.5 and the Spearman correlation with physics `frac_lt1` is −0.41, so it carries almost no local information |
| Green–Ampt + infinite-slope FS(t), failure times | `engine/trigger.py` | indirectly (via run outputs) |
| Voellmy-type runout with entrainment (GPU/numba) | `engine/flow*.py` | via saved arrays |
| Earthquake PGA + Newmark → same runout | `engine/trigger.py`, `run.py` (`mode quake/both`) | via saved arrays |
| Reach-angle envelope (empirical, DEM Dijkstra) | `models/runout/empirical.py` (`reach_envelope`, `ensemble_envelope`) | Tier 1 / Tier 2 screening |
| Building fragility (dynamic pressure + burial floor + census class) | `run.py::building_damage`, `_ds_probs`, `engine/census.py` | **Reused as-is** |
| Direct loss valuation (structure, 50 % contents, crops) | `engine/loss.py` | **Reused as-is** (parity), with price-year report (§3.5) |
| Road blocking, access/isolation, facilities | `run.py::_exposure`, `engine/access.py` | **Pass-through indicators** |
| Population (WorldPop; census fallback) | `run.py::_exposure`, `pipeline.py` | **Pass-through / reuse** |
| Average annual loss (design storms, trapezoid) | `engine/aal.py`, `app/design_storm.py` | Compared with CLIMADA EAL |
| Barriers / nature-based mitigation | `engine/interventions.py`, `optimize.py` | Tier 5 paired runs |
| Climate (CMIP6 rainfall factor on design storms) | ch. 16 | hazard side only |
| GIS export | `app/exports.py` | model for the risk export |
| Rockfall, deep-seated slides, snow avalanche | — | **not modelled** (`41_limitations.md` item 2) |

### 1.2 What is on disk per tier (verified from the three run folders)

All grids are 30 m, EPSG:32642, 365 × 251 cells (91,615 cells, ≈ 61.7 km²) in the inspected runs.

**Tier 3/4/5 run** (`runs/8ff3…`, `runs/98fb…`): `manifest.json` (grid: crs, transform `[x0, dx, 0, y0, 0, −dy]`, nodata −9999, params, `aoi_sha256`, warnings, `calibration_status`, `validation_status`), `inputs.json`, `geom.json` (AOI polygon; `epsg`, `dx`, `t0_s`, `quake`), `arrays.npz` (float32: `slope, dem, hmax, vmax, deposit, scour, t_fail_h, fs_min, z`; `pga_g` for quake; `p_fail` for ensembles), `frames.npz` (`H, VX, VY` as **float16**, 120 frames every 200 s; `frame_t`, `tfail_s`, `bedchange`, `stats`, `pga`), `summary.json`, **`impacts.json.gz`** (per-building: footprint, area, height, `rr`, `cc`, `dmg`, `ds`, `loss`, centroid; per-road: class, blocked flag), `mapbox_3d.html`. (`impacts.json.gz` was identified from `runs.py::_save_impacts`, not parsed.)

**Tier 1 run** (`runs/9db2…`, model `landslide_aoi`): `arrays.npz` with `dem, slope_deg, lsm_prob, min_fs_p05/p50/p95, frac_lt1, runout_freq, risk_index`; `summary.json` with the stability scenario (20 mm/h × 24 h = 480 mm, 30 ensemble members), majority-unstable area 2.79 km², reach-envelope settings (400 source cells, α = 14–24°, volume 10⁴ m³), `reached_area_km2 = 53.48` (87 % of the AOI), and WorldPop population: 122.5 in unstable cells, 40,029 inside the envelope, 67,639 in the AOI. **It does not save buildings.** Its own note: "reach-angle envelope, not simulated depth/velocity"; `runout_freq` is "envelope frequency conditional on priors", i.e. a fraction of reach-angle scenarios, not a probability.

**Tier 2** (`app/runs.py::instant_library`): computes median-parameter FS grids for the ladder 0/25/50/100/150/200/300/450/600 mm over 24 h and the critical-rain map, returns images and numbers **to the browser, and writes no run folder**. There is nothing on disk for a risk run to read until a small save is added (§1.4).

### 1.3 Reference numbers (Tier 3 run `8ff3…`, from `summary.json`)

Design storm 120 mm / 6 h (peak 38.3 mm/h), strength preset `calibrated_reports_weak`, quantile 0.3. Failing area 2.81 km²; released volume 7.13 × 10⁶ m³; impacted area 15.28 km²; 14,909 buildings, 5,139 DS ≥ 1, 3,276 DS ≥ 3; direct loss 28.51 × 10⁹ PKR (structure 19.01, contents 9.50, crops 2.4 × 10⁻⁵ × 10⁹); 28.9 of 65.2 km road blocked; 81.5 % of assessable points cut off. Parity target for the module.
(This run's AOI is only one example; see §1.6 for how the module handles any AOI.)

### 1.4 Required additive changes to the platform (small, nothing replaced)

| # | Change | Why | Where |
|---|---|---|---|
| A1 | Save a **Tier 2 library folder** (`runs/<id>/tier2.npz` with the FS ladder array, `mob`, critical-rain map; `manifest.json` with grid and params; `geom.json`) | Without it Tier 2 has no "simulation that has run" to base a loss on (hard rule 1) | `runs.py::instant_library` (write after computing; return value unchanged) |
| A2 | Save `p_max_kpa` and `h_at_pmax` rasters computed per solver step (or per frame) | removes the max-depth/max-speed pairing issue (§3.3) | `engine/run.py` flow loop |
| A3 | Store `return_period_y` as its own field (optional convenience) | The AAL job (`/area/compute-aal`) already runs each T through `runs.execute` and `design_storm.py:148` writes the source string `design storm T=<T> y, <D> h, alternating blocks …` into each run's `manifest.rainfall.source`, so T **can be parsed today**; a field is safer than parsing. Runs made with the Tier 3 "triangular design storm" UI carry no T and cannot join a scenario set | `runs.py::execute` / design-storm job |
| A4 | Add `pressure_definition` (`rho`, `drag_coefficient`) to `manifest.params` | makes the damage input self-describing | `engine/run.py` |
| A5 | Store the buildings used in a **Tier 1** run (id + centroid + area) or let the module rebuild them with the same source and limit | Tier 1 saves no exposure list | `pipeline.py::run_aoi` |

**Completion marker (checked, no change needed):** `runs.execute` writes `summary.json` as its very last step and the platform itself treats its existence as "run finished" (the cache test `if (rdir / "summary.json").exists()`), so the gate uses `summary.json` + `manifest.json` + `arrays.npz`. The same holds for Tier 1 (`pipeline._finalize`; the inspected Tier 1 folder has `summary.json`). Tier 2 has nothing on disk (A1).
**Required:** A1 only. **Optional:** A2–A5. Without A2 the module uses the platform's independent maxima and brackets them (§3.3).

### 1.5 Platform defects that affect risk numbers (flagged, not hidden)

| ID | Finding | Evidence | Treatment in the module |
|---|---|---|---|
| F1 | Pressure `p = ρ v²/1000` kPa (code, ρ = 1800 kg/m³) vs "ρ v²/2" in ch. 19 | `run.py::building_damage`; `19_loss.md` | Code equals `C_d · ½ρv²` with `C_d = 2`; keep, expose `C_d` as sensitivity parameter, report the doc inconsistency to the platform owner |
| F2 | Unit cost = 111 EUR/m² (2010 prices, JRC) × a current-date FX (322.5 PKR/EUR), no inflation | `loss.py` | Report on platform basis **and** flag it; optional aligned basis (§3.5) |
| F3 | Height fixed at 6 m ⇒ 2 storeys ⇒ ×2 on all footprints; residential value applied to every building | `layers.py`, `loss.py` | Storey count is a ranked uncertainty (bounds 1 and 2) |
| F4 | Building list capped at 40,000 (keeps the largest) | `layers.py::buildings` | Record found / used counts; warn when truncated |
| F5 | Hazard is sampled at the centroid with a 3×3 maximum filter | `run.py::_exposure` | Parity default; footprint-statistic option as sensitivity |
| F6 | `hmax` and `vmax` are independent cell maxima | `arrays.npz` | Bracket with the time-joint alternative (§3.3) |
| F7 | Census housing mix is district-wide; no Gilgit-Baltistan / AJK row (national mix used) | `engine/census.py` | Carry the platform's flag into outputs |
| F8 | Loss frequency assumed equal to rainfall frequency in AAL | `engine/aal.py` | Stored as an explicit assumption string (§3.10) |
| F9 | Tier 1 envelope (87 % of the AOI) is far wider than the Tier 3 footprint (25 % of its AOI), for different scenarios | summaries of the two runs | Tier 1/2 loss is labelled an upper-envelope screening figure (§3.8) |
| F10 | Data paths (checked on this host): buildings `~/Desktop/DGX-Shared/Tasks/Reselli_AI/flood/global_data/buildings_pk/PK_<quadkey>.parquet` and roads `…/roads_pk/pak_roads_indexed.gpkg` **exist**; hospitals/schools shapefiles live under `4. Vector Data/`; `ASSUMED_HEIGHT_M = 6.0` confirmed. The OSM path inside `scripts/infra_data.py` is **stale and not used by the app** (the app reads the files above), so it is ignored. Open Buildings acquisition date was not inspected | file listings, `layers.py` | Module reads paths only through `app/layers.py`/`app/paths.py`; record file mtime in provenance |

### 1.6 Any user-chosen AOI (design requirement)

The platform lets any user draw any AOI (up to 1.2 × 10⁶ km², `pipeline.MAX_AOI_KM2`). It targets ≤ 1.5 × 10⁶ cells (`MAX_CELLS`) by coarsening the grid (`choose_resolution`), never finer than 30 m, and skips physics when the cell would exceed 150 m (`MAX_PHYSICS_RES_M`). Consequences the module must handle without assuming any particular area:

1. **Everything comes from the run's `manifest.grid`** (CRS, transform, resolution); nothing is hard-coded to a location, UTM zone or cell size.
2. **Resolution warning:** when `resolution_m > 30`, the 3×3-maximum sampling covers a neighbourhood of 3 × resolution (e.g. 450 m at 150 m); the module prints the effective sampling distance and marks results `coarse_grid`. Buildings are 10 m-scale objects, so loss from coarse grids is more strongly biased (direction not established; reported as sensitivity).
3. **Physics skipped (resolution > 150 m):** no Tier 3/4/5 run exists for that AOI, so only the Tier 1 screening result is available; the gate says so and the panel stays on the screening product.
4. **Building cap:** `layers.buildings` keeps at most 40,000 (largest first) per run. For large or dense AOIs the exposure is therefore truncated; the module reports `n_found` vs `n_used`, labels the loss `lower_bound_truncated_exposure`, and never extrapolates.
5. **Census coverage:** districts without a census row (Gilgit-Baltistan, AJK) use the national mix (platform behaviour) and are flagged per building.
6. **Memory scales with cells, not area:** a hazard of 1.5 × 10⁶ cells with ≈ 40,000 buildings is held as a sparse matrix per event/class; only cells within the building 3×3 neighbourhoods are needed (≤ 40,000 × 9 cells), so the module may subset to those cells and avoid whole-grid matrices for large AOIs.
7. **Concurrency:** the platform runs one heavy job at a time (`_run_lock`); risk jobs are light but must go through the same job queue so two users do not collide.

---

## 2. CLIMADA Core vs Petals

### 2.1 Core components used

| Need | Core object (6.2.0) | Notes |
|---|---|---|
| Event × centroid intensity | `Hazard(haz_type, centroids, intensity: csr_matrix, fraction, event_id, frequency, frequency_unit, event_name, date, orig, units)` | `Centroids.from_meta`, `from_pnt_bounds`, `from_geodataframe` |
| Assets | `Exposures(data, crs, ref_year, value_unit)` with `value`, `impf_<HAZ>`, `centr_<HAZ>`, optional `region_id`; `assign_centroids` | `centr_<HAZ>` can be set directly (used for exact cell mapping) |
| Damage function | `ImpactFunc(haz_type, id, intensity, mdd, paa, intensity_unit, name)`, `ImpactFuncSet` | **one intensity variable only** |
| Impact | `ImpactCalc(exp, impfset, haz).impact(save_mat=True, assign_centroids=True)` → `at_event`, `imp_mat`, `eai_exp`, `aai_agg` | |
| Exceedance / aggregation | `Impact.calc_freq_curve`, `local_exceedance_impact`, `impact_per_year`, `impact_at_reg` | only meaningful with defensible frequencies |
| Uncertainty / sensitivity | `climada.engine.unsequa` (`InputVar`, `CalcImpact`, `CalcCostBenefit`) | Kropf et al. (2022); signatures must be re-read at coding time |
| Cost-benefit | `climada.engine.cost_benefit.CostBenefit`; `climada.entity.measures` (new `measure_config.py` plus `_legacy_measures`) | measure API changed in 6.x; verify, otherwise use the NPV helper in §3.12 |
| Calibration | `climada.engine.calibration_opt` | usable only once observed damage exists |

**Why use Core at all** (honest): it provides tested event × asset impact bookkeeping, regional aggregation, exceedance curves, and — the one capability LANDLAB lacks — structured Monte-Carlo/Sobol uncertainty and sensitivity (`unsequa`). It does **not** improve the physical hazard or the loss accuracy.

### 2.2 What Petals actually contains for landslides (read from `climada_petals/hazard/landslide.py`)

| | `Landslide.from_hist(bbox, input_gdf, res=0.0083333)` | `Landslide.from_prob(bbox, path_sourcefile, corr_fact=10e6, n_years=500, dist='poisson')` |
|---|---|---|
| Input | point inventory (e.g. NASA COOLR) | UNEP/NGI annual-probability raster |
| Grid | regular grid over `bbox`, default ≈ 0.9 km | the raster's own grid |
| Intensity | binary 1 in the cell containing a point | binary 1 where a sampled event occurs |
| Events | one per record | `n_years` sampled years, each = all slides in that year |
| Frequency | `1/(date span in years)` per event; "not meaningful for incomplete datasets" (docstring) | `1/n_years` |
| Impact functions | none for landslides (Petals ships drought, river flood, crop yield only) | step function advised |

Neither routine simulates landslide physics, neither supports depth/speed/pressure, and neither improves hazard predictions (no documented evidence of such). `from_hist` writes `date` with `pd.to_datetime`, which may conflict with the Hazard date convention in 6.x (risk R-02).

### 2.3 Decision: what to take from Petals

| Petals feature | Adopt? | Use | Test that decides |
|---|---|---|---|
| `Landslide.from_hist` | **Yes, validation only** | Converts the platform's landslide inventory clipped to the AOI (the platform's inventory is local: `MERGED LANDSLIDE LAYERS/Landslide_inventories/Landslides_All.shp`, 392 points incl. NASA COOLR, GLC and local inventories, loaded by `calibration/dataset.py::load()`; plus the Pakistan records of the Unified Global Landslide Catalogue at `datasets/external/uglc/` via `load_uglc()`. Nothing is downloaded. Inventory positions are reports: of 381 cleaned records only 117 have radius ≤ 1 km and 191 ≤ 10 km (`docs/validation/inventory_summary.json`), so the ≈ 0.9 km default Petals grid matches the positional accuracy and hit rates must use each record's own radius as tolerance) into a CLIMADA `Hazard`; gives (a) recorded-event counts per cell and per district, (b) the **hit rate** of recorded landslides inside the Tier 1/2 unstable zone and reach envelope and inside Tier 3 footprints, and (c) exposed buildings at recorded-landslide cells | Adopt if it passes T-00(d) (import + `date` handling) **and** produces the same cell counts as a 15-line numpy/rasterio count on a synthetic test. If not, use the custom count — nothing else depends on it |
| `Landslide.from_prob` + UNEP/NGI raster | **Optional, benchmark only** | Regional annual-probability benchmark (order of magnitude) next to any EAL; never an input to loss | Adopt only if the raster covers the AOI and its resolution/units are checked from the file |
| Petals `osm_dataloader`, `gdp_asset`, `black_marble`, `crop_production`, `supplychain`, `cat_bonds`, `warn` | **No** | LANDLAB already has OSM buildings/roads; the others do not match building-level landslide loss | — |

Conclusion: **Core does the computation; Petals contributes an inventory/benchmark helper.** I found no Petals feature that computes landslide loss better than Core.

---

## 3. Methodology

Symbols: V asset value (PKR), MDR mean damage ratio, h flow depth (m), v speed (m/s), p pressure (kPa), f annual frequency (yr⁻¹), L loss (PKR). Each subsection lists: concept → equation → inputs → assumptions → outputs → limits → validation.

### 3.0 Audit of four components (what revision 2 had, what was wrong, what replaces it)

| Component | Revision-2 status | Defects found on review | Resolution (section) |
|---|---|---|---|
| **Tier 1/2 indicative loss** | Specified, incomplete | (1) Weight `w = runout_freq` is a fraction of reach-angle scenarios, not a hit probability, and the envelope is far wider than a simulated footprint (87 % vs 25 % of area, different scenarios), so loss is inflated by construction. (2) One pooled damage quantile ignored distance from the source, mixing near-source destruction with distal light damage. (3) Source zone S and reach zone R overlapped, so exposed value could be double counted. (4) Tier 1's source cells are the top-`MAX_SOURCES` steep unstable cells, not all unstable cells, but the plan used the latter. (5) Reference scenarios of very different release volume were pooled. (6) No test of the transfer | §3.8, §3.9: distance-band mean damage ratio estimated from eligible Tier 3 runs, disjoint zones, source rule copied from `pipeline.py`, volume-eligibility filter, per-reference spread, leave-one-out test |
| **Time-dependent damage** | One-line "time-joint" option | (1) `frames.npz` is **cropped** (`crop = r0,r1,c0,c1`); building cell indices must be shifted — omitted. (2) Frames are 200 s apart, float16, start at 780 s: arrival times are censored and peaks can be missed — not stated. (3) `VX/VY` meaning (velocity) not verified. (4) Claimed "lower bracket" without proof. (5) No damage-versus-time output | §3.4a: two explicit conventions, monotonicity proof of the ordering, crop handling, arrival times, cumulative-loss curve, tests |
| **Building valuation** | Platform formula copied | (1) Possible **double counting of contents**: it is not established that the JRC residential value excludes contents (I could not read the report tables). (2) The JRC report states country-specific maximum damage values exist; the platform says Pakistan has none and uses the Asia figure — one of them is incomplete. (3) Unit basis (floor area vs footprint) and price year of the 111 EUR/m² value unverified here. (4) One value for pakka, semi-pakka and kacha while damage ratios differ by class. (5) Residential value applied to every footprint | §3.5: explicit switches, both bases reported, verification checklist, class-split output |
| **Annual loss frequencies** | Step and trapezoid models, CLIMADA exceedance from them | (1) The left-endpoint step (`f_i = p_i − p_{i+1}`) assigns each storm's loss to a larger probability band than it represents and **biases low**. (2) Using quadrature weights as `Hazard.frequency` and then calling CLIMADA exceedance functions gives a wrong curve (weights are not event rates). (3) Design depths are annual maxima, so the result is an *expected annual maximum event loss*, not an annual total — unstated. (4) Loss need not be monotone in T. (5) Rainfall-statistics (IDF) uncertainty not propagated. (6) No minimum scenario count | §3.10: exact trapezoid weights for EAL (parity), exceedance curve from the points, monotonicity check, IDF-uncertainty propagation, minimum set rule, tests |

### 3.1 Run gate (`RunGate`)

Checks (all must pass, else a typed error and HTTP 409/422):

1. `run_id` exists under `runs/` and is finished: `summary.json` (written last by `runs.execute`; the platform's own cache test) is parseable and `manifest.json` + `arrays.npz` exist. A folder without `summary.json` is an interrupted run and is refused.
2. Tier detection: `manifest.model == "landslide_physics_run"` ⇒ Tier 3/4/5 (mode `rain` ⇒ 3; `quake` or `both` ⇒ 4; non-empty `params.interventions` ⇒ 5); `landslide_aoi` ⇒ Tier 1; presence of `tier2.npz` ⇒ Tier 2.
3. Required arrays per tier: T3–5 `hmax, vmax` (+ `impacts.json.gz`); T1 `frac_lt1, runout_freq`; T2 FS ladder.
4. Grid sanity: shape equals manifest height × width; CRS projected (metres); NaN mask equals AOI mask.
5. The selected AOI hash equals the run's `aoi_sha256` (or the run's own AOI is used, shown to the user).
6. `Tier 1 susceptibility (lsm_prob)`, `risk_index` and `p_fail` are refused as hazard input.

### 3.2 Exposure (existing sources only)

**Buildings.** Tier 3/4/5: the exact list saved in the run (`impacts.json.gz`: footprint area, height, centroid, `rr`, `cc`). Because the list and the cell indices come from the run, exposure and cell mapping are identical to the platform's. Tier 1/2: rebuilt with `layers.buildings(bbox, geom)` (same Open Buildings parquet, same 40,000 limit), recording `n_found`, `n_used`.
**Value.** Platform valuation (§3.5): `V_struct = a · n_s · c_m`, `V_cont = r_c · V_struct`; `n_s = max(1, h_b/3)` (with the assumed `h_b = 6 m`, `n_s = 2`); `c_m = 111 EUR/m² × FX`; `r_c = 0.5`.
**Class split.** Each building's district census shares `(s_pakka, s_semi, s_kacha)` (national mix where the census has no row; flagged). Exposure is split into three CLIMADA exposure sets with `value × s_c`; because the platform's expected damage ratio is linear in the shares, the three-set sum equals the platform's mix-weighted value exactly.
**Regions.** `region_id` = district (164 polygons in `datasets/national/districts.geojson`), and settlement via OSM places if available.
**Pass-through (not re-modelled, not extended):** road length blocked and total, access/isolation results, hospitals/schools impacted, crop loss (platform rule, currently negligible), population in impacted cells and in damaged buildings (Section 3.7).
**Double-counting guards:** one row per footprint; contents is a separate category (never added to `V_struct`); facilities flagged on a building are attributes of that building, not extra assets; crops not counted under footprints; indirect/access indicators never summed with PKR loss.
**Data-quality gate:** CRS, coverage of the AOI, record date, share with valid area, duplicates, share outside the run's valid mask (excluded and counted).

### 3.3 Hazard intensity and damage (Tier 3/4/5) — the multivariate problem

Depth, speed, pressure and burial have different meanings and are never added or averaged. The platform's two-variable fragility stays **outside** CLIMADA; CLIMADA receives its result as a dimensionless intensity.

**Step 1 – sampling (platform convention, default).** `h_i = maxfilter3×3(hmax)[rr, cc]`, `v_i = maxfilter3×3(vmax)[rr, cc]`, where filtering is applied to the rasters **before** computing damage (MDR is non-linear in h, v). Check how NaN outside the AOI is handled by the filter (platform behaviour must be replicated); the parity test decides.

**Step 2 – fragility (platform, reused via import of `_ds_probs` and the `IMP` constants).**
```
p = C_d · ½ ρ v² / 1000                [kPa]   (platform: C_d = 2, ρ = 1800 kg/m³)
P(DS ≥ k) = Φ( ln(p / (m_k · s_c)) / β ),   m = {5, 15, 40, 100} kPa, β = 0.6
s_c = 1.0 / 0.6 / 0.3 for pakka / semi / kacha  (assumed multipliers)
burial floor: DS ≥ k when h ≥ {0.3, 1, 2, 4} m;   h < 0.3 m ⇒ DS0
MDR_c = Σ_k P(DS = k) d_k,   d = {0, 0.05, 0.20, 0.55, 1.00}
MDR_i = Σ_c s_{i,c} MDR_c        (equals the platform's mix-weighted value)
```
**Step 3 – CLIMADA.** One `Hazard` per construction class with `intensity = MDR_c ∈ [0,1]` (`units = "1"`), one identity `ImpactFunc` (`intensity = [0,1]`, `mdd = [0,1]`, `paa = [1,1]`), three `ImpactCalc` runs, summed. No physics is hidden in the function; it is auditable in `risk/vulnerability/`.

**Bracketing the max-h/max-v inconsistency (F6).** The platform pairs independent maxima, which can overstate pressure. §3.4a computes time-resolved alternatives (cumulative-maxima and joint) from the saved frames; since the fragility is monotone, `MDR_joint ≤ MDR_run ≤ MDR_platform` and the three totals are reported as a final-state range. If A2 is implemented, per-step `p_max` replaces the frame computation.

**Other sensitivities (no extra data needed):** `C_d` ∈ {1, 2}, footprint-statistic sampling (max over footprint cells) instead of centroid+3×3, storeys {1, 2}.

**Limits.** All fragility constants are assumptions, not fitted to Pakistani damage (ch. 16.2). The 30 m grid cannot resolve building-scale flow. Burial and pressure thresholds are step rules. Quake-shaking damage to buildings is **not** included and must not be added (different hazard).

**Validation.** (i) Parity: for 1,000 random (h, v, class) triples the module's MDR equals `building_damage` to 1e-12; (ii) desk comparison of the median-state curve against published debris-flow vulnerability envelopes (Fuchs et al. 2007; Papathoma-Köhle et al. 2012; Quan Luna et al. 2011 — bibliographic details checked, §12; the curves themselves were not retrieved or digitised here, and they describe European buildings, so they are a plausibility band, not a fit); (iii) real validation needs observed building damage, which is not openly available in usable form (§7).

### 3.4 Event and loss equations (Tier 3/4/5)

```
L_{i,e}     = V_i · MDR_{i,e}                          asset loss, structure and contents separately
L_e         = Σ_i L_{i,e}  (+ platform crop term, passed through)
L_e(region) = Σ_{i∈region} L_{i,e}
```
Outputs: loss per building, per damage state, per district/settlement, per event; damaged-building counts DS ≥ 1/2/3; people in damaged buildings (platform estimate); loss-density map `PKR/km²` on the run grid.

### 3.4a Time-dependent damage (Tier 3/4/5 only; needs `frames.npz`)

**Why.** The final-state loss hides *when* damage happens. The platform already stores the flow history (`H`, `VX`, `VY`, 120 frames) and its 3D viewer colours buildings by the depth reached so far; the risk module gives the same quantity in PKR and gives a defensible lower bracket for the final loss.

**Inputs.** `frames.npz`: `H, VX, VY` (float16, shape `(n_frames, r1−r0, c1−c0)`), `frame_t` (s), `crop = (r0, r1, c0, c1)`; building cells `(rr, cc)` from `impacts.json.gz`; `arrays.npz` (`hmax`, `vmax`).
**Pre-checks (T-00/T-13):** `VX, VY` are velocity components (FlowState `vx, vy`); confirm `max_t √(VX²+VY²) ≤ vmax` (+ float16 tolerance) on the run's cells. If this fails, the time-dependent product is disabled for that run and says why.

**Procedure.**
1. Shift to crop coordinates: `(rr − r0, cc − c0)`. A building outside the crop never saw flow (the crop contains every cell with `H > 0.05` ever, plus a 12-cell margin, `runs.execute`), so its time series is zero.
2. For each frame `t` and building, take the 3×3 neighbourhood maxima (platform sampling): `h3(t) = max H`, `v3(t) = max √(VX²+VY²)`. Process buildings in chunks (`nb × 9 × n_frames` float16 ≈ 32 MB for 15 k buildings; chunk for the 40,000 cap).
3. Running maxima: `h_run(t) = max_{τ≤t} h3(τ)`, `v_run(t) = max_{τ≤t} v3(τ)`.
4. Two conventions for pressure (`C_d`, ρ from the config; `p = C_d·½ρ v²/1000`, kPa):
   - **Cumulative maxima** (platform-consistent): `p_run(t) = p(v_run(t))`.
   - **Joint** (strict): `p_joint(t) = max_{τ≤t} [ p(v3(τ)) · 1(h3(τ) ≥ 0.3 m) ]` — speed only counts at moments when the flow is deep enough to matter.
5. Damage at time `t`: `MDR_run(t) = D(h_run(t), p_run(t))` and `MDR_joint(t) = D(h_run(t), p_joint(t))`, with `D` the platform fragility (§3.3) taking `p` directly (the platform helper `_ds_probs` already takes `p`; a thin wrapper replaces its `vmax` argument). Burial uses the running depth, which needs no simultaneity.
6. Outputs per building: `t_arrive` (first frame with `h3 ≥ 0.3 m`), `t_peak_pressure`, `t_DSk` (first time the most probable state is ≥ k), `MDR(t)`. Per event: cumulative loss `L(t) = Σ_i V_i·MDR_i(t)`, buildings reached vs time, and time from the first failure in the AOI (`summary.failed_cells_vs_time`, `t_fail_h`) to arrival.

**Ordering guarantee (and test).** `D` is non-decreasing in both `h` and `p` (P(DS ≥ k) rises with `p`; the burial floor shifts probability to higher states as `h` grows; damage ratios are increasing in state). Frames are snapshots of the solver, whose `hmax/vmax` are maxima over *every* step, so frame maxima cannot exceed them (except float16 rounding). Therefore, for every building:
`MDR_joint(t_end) ≤ MDR_run(t_end) ≤ MDR_platform` (up to float16 rounding, tolerance set in config). A violation beyond tolerance is a bug or an unexpected `vmax` definition and aborts the product. The three totals are reported as **final-state range**; the platform value is the upper end.

**Resolution and limits.** Frames are 200 s apart, the window starts at 780 s (`t0_s`): arrival times have 200 s resolution and anything earlier is left-censored; short peaks between frames are missed (hence the lower bracket). Time series exist only for Tier 3/4/5; Tier 1/2 have no time dimension. Damage is treated as irreversible and independent of earlier damage to neighbours (no debris loading feedback). CLIMADA's `Hazard` holds one date per event, so time series are stored in separate tables and CLIMADA receives only the final `MDR` of the chosen convention (`intensity_pairing`).
**Validation.** Ordering inequality; `MDR_run(t_end)` totals against `summary.exposure.direct_loss_pkr` (ratio reported); arrival times against the 3D replay on three sampled buildings; monotone `L(t)`.

### 3.5 Building valuation, price year and currency

**Equations (platform parity, `engine/loss.py`).**
```
n_i        = max(1, h_i / 3 m)                     storeys (h_i = 6 m assumed ⇒ n_i = 2)
V_struct,i = a_i · n_i · c                          a_i footprint area (m²), c unit value (PKR/m²)
c          = c_EUR · FX                             c_EUR = 111 EUR/m² (platform: JRC Asia residential, 2010 prices), FX = 322.5 PKR/EUR
V_cont,i   = r_c · V_struct,i,   r_c = 0.5          (platform: FEMA HAZUS residential content ratio)
L_i        = (V_struct,i + V_cont,i) · MDR_i
```
**Review (what is and is not established).**
1. *Is the arithmetic implemented as written?* Yes — `building_structure_loss` and `CONTENT_TO_STRUCTURE_RATIO` match; the parity test (T-04/T-14) checks it.
2. *Contents double counting — NOT established either way.* If the JRC residential value already includes contents, adding 50 % counts them twice (contents are 33 % of the platform total: 9.50 of 28.51 × 10⁹ PKR in the reference run). I could not read the report's tables (the PDF host returned 403; the JRC page lists no files; secondary pages do not state it). Treatment: config `contents_mode ∈ {platform_50pct, none}`; **both totals are always reported** (with contents = platform; structure-only = lower value), so the user sees the range instead of a hidden choice.
3. *Country value.* The JRC abstract says maximum damage values were derived **per country** from construction-cost surveys and regressions on World Development Indicators; the platform uses a continental Asia figure and states that Pakistan has none. One of the two is incomplete. `value_source ∈ {platform_asia_111, jrc_country_value}`; the second is enabled only after someone reads the JRC database and records the Pakistan value, its unit basis, price year and the table/sheet name in the config. Until then the module prints `value_source = platform_asia_111 (JRC country value not checked)`.
4. *Unit basis.* It is not verified whether the JRC value is per m² of floor area or of footprint; the platform multiplies footprint by `n_i`, i.e. treats it as per floor area. Storey count is therefore a sensitivity parameter with bounds `{1, 2}` (the platform's earlier valuation used one floor); the module does **not** claim either is right.
5. *Class-independent value.* The same `c` applies to pakka, semi-pakka and kacha buildings while the damage ratio differs by class (kacha medians are 0.3× pakka). If replacement cost falls with construction quality, loss for kacha buildings is overstated; no cost data exist to set the factor. Outputs split loss by class; config `class_value_multiplier = {pakka: 1, semi: 1, kacha: 1}` (platform parity) is exposed for sensitivity and is **not** pre-filled with invented values.
6. *Asset type.* One residential value is applied to every footprint; hospitals/schools are only flagged (§3.7) and are valued as ordinary buildings if a footprint contains them. The JRC database has other building classes, but the building type is unknown here, so none is applied.
7. *Footprint area.* `a_i` is the dataset's `area_in_meters` of the footprint polygon (largest part of a multipolygon). The parquet's other columns (e.g. a detection-confidence column) were not inspected; the module records which columns exist but filters none (parity).

**Price year and currency.**
- *Platform basis (default, for parity):* `price_year = 2010`, `fx = 322.5 PKR/EUR (current-date)`, `inflation_adjusted = false`. This mixes a 2010-price EUR figure with a present-day exchange rate; every output carries these three fields and the sentence "price basis mixes years".
- *Aligned basis (optional, only if the user configures both series):* either (a) `c_t = c_EUR · FX_2010 · CPI_PK(t)/CPI_PK(2010)` (convert at the price-year rate, inflate with Pakistan's CPI) or (b) `c_t = c_EUR · HICP_EA(t)/HICP_EA(2010) · FX(t)` (inflate in EUR, convert at the date rate). They differ; when both series are configured the module reports **both** as a bracket. No series is bundled or downloaded; none is invented. If neither is configured, the aligned basis is `NOT_COMPUTED`.
- The module never adds figures with different `price_year`; a mix aborts the run.
- The value is a **replacement-type value of shell and contents**, not a market, insured or economic-activity value.

**Outputs.** Per building: `a_i, n_i, c, V_struct, V_cont, class shares, value_source, contents_mode, price_year, fx, loss_with_contents, loss_structure_only`. Per event: totals by class and basis.
**Tests.** T-04 (parity with `summary.exposure`), T-14 (storeys = 1 halves structure value; contents switch changes only the contents term; price-year guard).

### 3.6 Spatial rules for the footprint area

A building is never destroyed because a cell intersects it: loss is always `V × MDR(h, v)`. The default sample is the centroid cell with a 3×3 maximum (platform), which acts as a ~90 m neighbourhood; the alternative footprint maximum/mean/p90 is reported as sensitivity (F5).

### 3.7 Indicators passed through from the platform (no PKR)

Roads blocked (km, and share of network), people/buildings cut off, facilities cut off or with detour, hospitals/schools impacted, population in cells with `hmax ≥ 0.3 m`, population in damaged buildings (DS ≥ 2 × household size). These are exposure/consequence indicators of the platform's own calculations, shown beside the loss but never converted to PKR or added to it. Fatalities, injuries and displacement are **not** estimated.

### 3.8 Tier 1 screening loss (no depth, no speed available)

Depth and speed do not exist, so the platform fragility cannot be applied. The module reports an **exposed-value** product that is always computed, and an **indicative loss range** that is computed only from real Tier 3/4 reference runs.

**Zones (disjoint).** From the Tier 1 arrays: `Z0 = {frac_lt1 ≥ 0.5}` (the platform's "unstable" rule); `Z1 = {runout_freq > 0} \ Z0` (reached by the envelope, not unstable); outside both: unaffected by the envelope. Release cells for the envelope are **not** all of `Z0`; reproduce the platform rule exactly (`pipeline.run_aoi`): `src = unstable & slope > 20°`, and if more than `MAX_SOURCES`, keep the lowest-`min_fs_p50` cells. (`slope_deg`, `min_fs_p50`, `frac_lt1` are saved in the Tier 1 arrays.)

**(a) Exposed value (always).** `EVaR_Z = Σ_{i∈Z} (V_struct,i + V_cont,i)` for `Z0`, `Z1` separately, plus building counts and the platform's population numbers. This is a count of assets in zones, **not** a loss.

**(b) Indicative loss (only with eligible references).**
```
d_i   = Euclidean distance from building i's cell to the nearest release cell   (m; EDT on the run grid; same metric for references)
b(d)  = distance band (config edges; default 0–50, 50–100, 100–200, 200–400, 400–800, >800 m — bin choices, not physics)
m_r(b)= mean over ALL buildings of reference run r in band b of the stored expected damage ratio `dmg` (zeros included)
L_T1,r = Σ_i V_i · m_r(b(d_i))               over buildings with band covered by r
```
- A reference run `r` supplies, for its own buildings, `d` (from its release cells = finite `t_fail_h`), `dmg` (from `impacts.json.gz`). Using unconditional means (hits and misses together) avoids multiplying a hit probability by a damage ratio and avoids the non-probability `runout_freq`.
- **Eligibility of a reference run:** Tier 3 or 4 run, finished; mean released volume per release cell within a factor `f_vol` (config, default 5) of Tier 1's per-source volume (`summary.runout.volume_m3`, 10⁴ m³ here); in the example run 7.13 × 10⁶ m³ over 3,117 cells ≈ 2.3 × 10³ m³ per cell, a factor 4.4 below 10⁴, so it would just qualify. Band `b` is used only if `r` has ≥ `n_min` buildings in it (config); buildings in uncovered bands are excluded from the loss, counted, and still appear in `EVaR`.
- **Preference order:** references with the same `aoi_sha256`, then other areas (labelled `transfer_from_other_area`).
- **Reported range:** minimum, median, maximum of `L_T1,r` over eligible references. With a single reference no range is given and the label says `single_reference`. With none: `NOT_COMPUTED: no eligible reference runs` and only (a) is shown. No numbers are invented.
- **Meaning and bias.** This is "what the platform's own Tier 3 results imply for buildings at these distances from release cells" — a transfer, not a Tier 1 simulation. It still inherits the Tier 1 envelope's extent (the envelope can place buildings in distance bands that real flows did not reach, in which case the reference mean in that band is small — this is the intended correction), release-volume differences, terrain differences when the references are from another area, and every assumption in the fragility and valuation.
- **Check against Tier 3 where both exist for the same AOI and scenario:** report `ρ = L_T1 / L_T3` and footprint-area ratio; this is the only direct measure of the screening error.
- **Leave-one-run-out test (when ≥ 3 eligible references):** predict each reference run's Tier 3 loss from its release cells using the others' band means; report relative error. This tests the distance-band transfer, **not** the Tier 1 envelope.
- No frequency, no EAL, no exceedance curve for Tier 1.

### 3.9 Tier 2 loss by rain total

After change A1 the library stores `fs_stack` (ladder 0/25/50/100/150/200/300/450/600 mm over 24 h), `mob`, `crit`, the grid and parameters.
For each rung `j`:
1. Release cells `S_j = {FS_j < 1} ∩ mob ∩ {slope > 20°}`; if more than `MAX_SOURCES`, keep the lowest FS (the Tier 1 rule, with FS in place of `min_fs_p50`).
2. Reach envelope from `S_j` with the platform's `ensemble_envelope` at the Tier 1 settings (α range 14–24°, per-source volume = the config default equal to Tier 1's 10⁴ m³ because Tier 2 has no volume); distances `d_i` as in §3.8.
3. `EVaR_j` (zones as in §3.8) and `L_T2,j` from the same reference band means.
Output: loss-versus-rain curve (9 points) with the min/median/max over references, plus the values at the two design depths the page computes (2-year and 100-year, 24 h) by linear interpolation **within** the ladder (no extrapolation). Tier 2 uses median soil parameters, not an ensemble, and labels itself so. **No EAL** (a rain depth is not an event frequency without the Tier 3 assumption, and the reach and transfer steps add more).

### 3.10 Annual loss frequencies (Tier 3/5 scenario sets only)

**What the number is.** The platform's design depths come from a Gumbel fit to *annual maxima* of rainfall (`design_storm.py`), so for a design storm of return period `T` the annual exceedance probability of the annual-maximum storm is exactly `p = 1/T`. The integral below is therefore the expected **annual-maximum event loss** (EAMEL; the platform calls it EAL). It is *not* an expected annual total: it ignores further loss-producing storms in the same year (this biases low) and it assumes the annual-maximum storm always triggers the simulated landslide event, ignoring antecedent state and the many storms that cause none (this biases high; `q_trig` below). The net sign is unknown, so the figure is labelled an order of magnitude for comparing places and options.

**What frequency information exists:** only `T`. Susceptibility, `frac_lt1`, `p_fail`, `runout_freq` are not frequencies; inventories are incomplete.

**Scenario set rules (gate).** Runs from the AAL job (`/area/compute-aal`) with `manifest.rainfall.source = "design storm T=<T> y, <D> h, …"` (or the A3 field), identical AOI, parameters, strength preset/quantile, duration and climate factor; **at least 4 return periods** (config) covering a stated range; runs differing in anything but the storm are rejected. Fewer than 4 ⇒ scenario losses only, no EAL.

**Loss–probability curve.** Sort scenarios by probability ascending (`p_0 < … < p_{n−1}`, i.e. `T` descending) with losses `L_k`.

**Primary integral (platform parity, `engine/aal.py`):**
```
EAL = L_0·p_0                                              rare tail: loss held at the rarest scenario  (biases LOW if loss keeps rising)
    + Σ_{k=0}^{n−2} ½ (L_k + L_{k+1}) (p_{k+1} − p_k)     body: trapezoid in p
    + ½ L_{n−1} (1 − p_{n−1})                              frequent end: loss falls linearly to 0 at p = 1  (an assumption)
Equivalent weights w_k:  w_0 = p_0 + ½(p_1 − p_0);  w_k = ½(p_{k+1} − p_{k−1});  w_{n−1} = ½(p_{n−1} − p_{n−2}) + ½(1 − p_{n−1});   EAL = Σ w_k L_k
```
`q_trig ∈ (0,1]` multiplies the result: `EAL_q = q_trig · EAL` (default 1, flagged: upper-end, unvalidated; a storm-size-dependent `q(p)` is allowed only if supplied with its source). Reported parts: rare tail, body, frequent end.

**Sensitivity variants (always reported with the primary):**
- *No frequent tail:* drop the last term (lower value; the platform's linear-to-zero tail is an assumption).
- *Monotone envelope:* `L'_k = running maximum of L` over decreasing `p` (loss should not fall as storms grow; discrete building thresholds can make single runs non-monotone, as the platform's ch. 21 notes). Flag how many points were altered.
- *Strength scenarios:* if sets exist for several strength presets/quantiles, report one EAL per set; **no averaging** without weights.

**Rainfall-statistics uncertainty (no new simulations).** If `return_period_table` returns bootstrap depth quantiles (`n_boot` is an argument; its output keys were not inspected, so verify), build `L(D)` from the set (monotone interpolation of loss on storm total depth, **no extrapolation** beyond the simulated depth range), draw bootstrap depth curves `D_b(T)`, recompute EAL for each, and report the spread. It covers rainfall-fit uncertainty only (not soil, friction, fragility, valuation) and holds duration and hyetograph shape fixed.

**CLIMADA representation.**
- *For EAL:* one `Hazard` event per scenario with `frequency = w_k` (trapezoid weights), `frequency_unit = "quadrature weight (not an event rate)"`; then `Impact.aai_agg` reproduces the primary EAL exactly and `eai_exp` gives the per-asset share of it. **Do not** call `calc_freq_curve`, `local_exceedance_impact` or `impact_per_year` on this hazard — weights are not event rates and these functions would return a wrong exceedance curve.
- *For the exceedance curve:* plot the points `(p_k, L_k)` (with the interpolation and tails stated above) directly; this is a custom plot, not a CLIMADA call.
- *Optional event-rate form (for CLIMADA exceedance and `unsequa`):* bin probabilities between geometric mid-points, in ascending-`p` order `E_{−1} = 0`, `E_k = √(p_k p_{k+1})` for `k = 0 … n−2`, `E_{n−1} = 1`, `f_k = E_k − E_{k−1}`, loss `L_k` assigned to bin `k`. This is a different model form (it extends the rarest loss to p → 0 and the most frequent loss to p = 1) and is shown only as a comparison; the difference to the primary is reported as model-form uncertainty.
**Quake:** scenario losses only (no source model with rates is in the platform).
**Optional benchmark:** Petals `from_prob` regional annual-probability field next to the EAL as an order-of-magnitude plausibility check only, if its raster covers the AOI and its units are verified from the file.
**Display gate:** the page shows the per-return-period loss table by default; EAL appears after the user acknowledges the assumption text above.
**Tests.** T-09/T-16: `Σ w_k L_k` equals the integral of the interpolated curve with the stated tails; exact agreement with `engine/aal.py::eal` on random inputs (< 1e-9 relative); constant-loss case equals `L(p_{n−1} + ½(1−p_{n−1}))`; zero loss ⇒ zero; more loss ⇒ more; monotone-envelope flag; set-gate refusals; `aai_agg` equals the primary EAL.

### 3.11 Climate comparison

Climate enters through rainfall forcing already in the platform (CMIP6 factor on design storms). The module compares two risk sets (baseline vs climate-adjusted) with the same exposure and vulnerability: `ΔL = L_future − L_baseline`, reported as hazard change only. No exposure growth, land-use or asset-value projections are modelled (no platform support). The platform's own demo showed a factor of 1.016 within a model spread of 0.90–1.32, i.e. no detectable change; the page must show ranges, not point forecasts.

### 3.12 Risk reduction (Tier 5)

Mitigation effects are produced by **re-simulation** (barriers raise the bed in the solver; nature-based levers change cohesion/drainage). Avoided loss therefore comes from **paired runs** with identical AOI, hazard parameters and exposure, differing only in `interventions`; the gate finds the baseline by parameter hash and refuses if it does not exist (nothing is fabricated, and no percentage reduction is applied).
```
ΔL_e   = L_e(baseline) − L_e(mitigated)
ΔEAL   = Σ_i f_i ΔL_i                               (only for matching risk sets with a frequency model)
B      = Σ_{t=1..N} ΔEAL_t /(1+r)^t     (benefit; if EAL unavailable, report ΔL_e only, no B)
C      = I_0 + Σ_{t=1..N} M_t /(1+r)^t
NPV = B − C,   BCR = B / C
```
`I_0`, `M_t`, `r`, `N` are **user inputs** (the platform has no cost data, ch. 24); BCR is not shown if any is empty. `CostBenefit` is used only if the 6.x measure API accepts externally produced `Impact` objects; otherwise the helper above is used. Null results are shown: the platform's own test with two barriers lowered loss by 0.5 %.

### 3.13 Uncertainty and sensitivity

- **Hazard-side** uncertainty (strength preset, quantile, friction) is propagated by **saved run ensembles** (`ensemble`, scenario presets), not by sampling in the loss layer; the physics is not rerun by the module.
- **Loss-side** parameters sampled with `unsequa` (Monte-Carlo + Sobol): fragility median scale, β, class multipliers, `C_d`, storeys {1, 2}, unit cost, contents ratio, `q_trig`, sampling method. Ranges are **sensitivity bounds chosen by the user**, with defaults from the platform's own alternative values (e.g. storeys 1 vs 2, C_d 1 vs 2). Because defaults are not statistical estimates, the output is a **driver ranking and a sensitivity band**, not a confidence interval about real losses. Credible predictive intervals require observed damage (§7).

---

## 4. Datasets

Only items the module reads or that are genuinely missing.

| Dataset | Purpose | Source | Existing/New | Status |
|---|---|---|---|---|
| Finished run folders | hazard, AOI, tier | `runs/<id>/` | Existing | gate input |
| Saved building list | exposure (T3–5) | `runs/<id>/impacts.json.gz` | Existing | |
| Open Buildings parquet | exposure (T1–2) | `layers.BUILD_DIR` | Existing | confirm coverage and date |
| PBS 2023 census | class mix, household size | `datasets/external/pbs/` | Existing | none for GB/AJK |
| WorldPop / census density | population | `paths.POPULATION`, `engine/census.py` | Existing | |
| District boundaries | region totals | `datasets/national/districts.geojson` | Existing | |
| OSM places / roads / POIs | settlements, access, facilities (pass-through) | local OSM extract (path to confirm, F10) | Existing | |
| Landslide inventory | Petals/hit-rate validation | `Landslides_All.shp` + `datasets/external/uglc/` (via `calibration/dataset.py`) | Existing (verified) | UGLC is CC-BY-NC 4.0: non-commercial use only; NASA COOLR bulk download was blocked/404 when tried (`GILGIT_SMALL_SCALE_METHODOLOGY.md`), so use the local copy |
| JRC max damage values | valuation | encoded in `loss.py` | Existing | price-year caveat |
| Design-storm run sets | frequency basis | platform job | Existing (compute-heavy, on request) | needs A3 |
| Pakistan CPI and FX series | aligned valuation | PBS / State Bank of Pakistan | **New (small)** | optional, user-chosen |
| NDMA / PDMA / GBDMA damage records | calibration | searched 2026-11-09 | **Not used** | What is openly online (news reports and NDMA situation-report figures) gives province- or district-level totals of houses damaged, mixes floods, landslides and other monsoon hazards, is cumulative and revised between editions, and has no building location, hazard intensity or event polygon. I found no downloadable landslide damage dataset (no `ndma.gov.pk` page was returned by the search, so the NDMA site itself was not inspected). Without intensity and location, a fragility function cannot be fitted or tested, so these figures are not used and no request is made |
| UNEP/NGI probability raster | Petals benchmark | UNEP/GRID-Europe | New, optional | clip to AOI only |

**Not obtainable from free GIS data** (stated, not worked around): building material, storeys, use class, replacement cost, observed damage costs. Fallbacks: census class mix and storey bounds {1, 2}; results stay labelled uncalibrated.

---

## 5. Integration architecture

### 5.1 Principle

`risk/` **reads** finished run folders and shared datasets; it imports only pure helpers and constants from `engine/` (fragility, valuation, reach envelope, AAL) to guarantee parity, and it never launches a simulation. CLIMADA runs in its own environment and is called as a subprocess (`python -m landslide.risk.cli`) that exchanges only files with the Flask app.

**Why a separate environment (operational reasons, not scientific ones).** CLIMADA does not need one to be correct; it needs one because installing it into the environment the app uses is unsafe or impossible here:
1. **It does not install by `pip` on this host.** A resolver dry-run of `pip install climada==6.2.0` into `~/lai_venv` (the only venv found with rasterio/geopandas) stopped at `fiona`: no wheel was used, the source build failed with "A GDAL API version must be specified … gdal-config" because the host has no system GDAL (`which gdal-config` finds nothing).
2. **It brings ≈ 35 hard dependencies** (including `gdal`, `fiona`, `cartopy`, `numba`, `h5py`, `salib`, `statsmodels`, `pathos`, `peewee`, `overpy`, `contextily`) into the environment that also serves SAILAB (README: the app runs on SAILAB's venv). Upgrades of shared `numpy/pandas/shapely/rasterio/pyproj` could break the flood product; `~/lai_venv` already holds very new versions (numpy 2.5.4, pandas 3.1.0) whose compatibility with CLIMADA 6.2.0 is untested.
3. **The platform's declared interpreter `~/flood/venv` does not exist on this host**, so there is no known-good environment to modify.
4. CLIMADA's documented install route is conda-forge, and `/opt/miniconda3/condabin/conda` is present, which brings GDAL as a binary package.
Recommended: a conda-forge environment (Python 3.11–3.12) containing CLIMADA 6.2.0; Petals added with `--no-deps` (Petals requires Python < 3.13 and otherwise pulls `xesmf`, `boario`, `pymrio`, `cdsapi`). If the owners prefer a single environment, the same code runs in-process after the platform environment is rebuilt with these packages and T-00 passes; the file-based interface makes either choice possible. Cost of the separation: one subprocess call per risk job and a duplicated copy of numpy/pandas/geopandas.

```
 existing: engine → runs/<id>/ (arrays, manifest, summary, impacts)  ──(read only)──┐
                                                                                     ▼
 api/RunGate ─► adapters/SimulationOutputAdapter ─► tier router ──────────────────────────────────┐
   (no run ⇒ 409)         │                                                                        │
                          ├─ T3/4/5: hazard/MDRHazardBuilder ─► exposure/ExposureBuilder           │
                          │          ─► vulnerability/VulnerabilityManager ─► direct_loss/AssetLossCalculator (CLIMADA)
                          ├─ T1/T2:  screening/ScreeningLossEstimator (EVaR, indicative range)     │
                          └─ sets:   probabilistic_risk/ProbabilisticRiskEngine, adaptation/AdaptationAnalyzer
                                                         ▼
               reporting/RiskReportGenerator ─► runs/<id>/risk/<risk_id>/ (CSV, GPKG, GeoTIFF, JSON, report, provenance)
                                                         ▼
                                   dashboard "Risk & Loss" panel (read-only via /risk/...)
```

### 5.2 Layout (matches the repo)

```text
backend/landslide/risk/
    config/            defaults.yaml, schema.py, profiles/{parity.yaml, aligned_price.yaml}
    gate.py            RunGate, TierRouter
    adapters/          simulation_output.py
    hazard/            mdr_hazard.py (CLIMADA Hazard), events.py, frequency_models.py
    exposure/          builder.py, buildings.py, population.py, passthrough.py
    vulnerability/     manager.py, debris_building.py (imports platform fragility)
    direct_loss/       calculator.py, valuation.py, price_basis.py
    screening/         estimator.py  (Tier 1/2: EVaR, reference MDR transfer)
    probabilistic_risk/ engine.py, unsequa_setup.py, petals_inventory.py
    adaptation/        analyzer.py
    validation/        parity.py, gates.py, hit_rate.py   (observed_loss.py only if an open damage dataset appears)
    reporting/         generator.py
    api/               blueprint.py
    cli.py
    tests/
```

### 5.3 Classes

| Class | Duty | CLIMADA? |
|---|---|---|
| `RunGate` / `TierRouter` | hard rules 1–2; tier detection; required-array check | no |
| `SimulationOutputAdapter` | load arrays/manifest/summary/impacts; validate grid, NaN mask, units | no |
| `MDRHazardBuilder` | filtered h, v → MDR per class → `Centroids`, sparse `Hazard` (+ time-joint variant) | `Hazard`, `Centroids` |
| `ExposureBuilder` | saved or rebuilt buildings → three `Exposures` (class shares), `region_id`, flags | `Exposures` |
| `VulnerabilityManager` | registry of the platform fragility with `not_calibrated` status; builds identity `ImpactFuncSet` | `ImpactFunc` |
| `AssetLossCalculator` | `ImpactCalc` per class, sum; tables by asset/state/district | `ImpactCalc`, `Impact` |
| `ScreeningLossEstimator` | Tier 1/2 EVaR and indicative range | no |
| `ProbabilisticRiskEngine` | scenario sets, frequency models, EAL, curves, `unsequa` | `Impact`, `unsequa` |
| `AdaptationAnalyzer` | paired runs, ΔL, NPV, BCR | optional `CostBenefit` |
| `RiskReportGenerator` | CSV/GPKG/GeoTIFF/JSON/report, provenance | no |

### 5.4 Schemas

`risk_config.yaml` (key fields): `profile` (`parity` | `aligned_price`), `currency: PKR`, `price_year`, `fx_basis`, `pressure: {rho: 1800, drag_coefficient: 2.0, min_depth_m: 0.3}`, `sampling: centroid_3x3max | footprint_{max,mean,p90}`, `intensity_pairing: independent_maxima | time_joint`, `valuation: {storeys: {from_height: true, height_m: 6, bounds: [1,2]}, contents_ratio: 0.5}`, `frequency_model: none | step | trapezoid`, `trigger_probability_q: 1.0`, `screening: {reference_runs: auto, min_reference_buildings: <set>}`, `uncertainty: {n_samples, parameters, ranges}`.
`events.csv`: `event_id, event_name, run_id, tier, trigger (rain|quake|both), return_period_y, frequency, frequency_basis, q_trig, date, strength_preset, strength_quantile, rain_total_mm, model_version, aoi_sha256, params_sha256`.
`asset_loss.csv` / GPKG `assets`: `asset_id, class, geometry, region_id, value_struct_pkr, value_cont_pkr, h_m, v_ms, pressure_kpa, mdr, ds_mode, loss_pkr, loss_pkr_lower_bracket, price_year, quality_flag`.
`provenance.json`: run id and file SHA-256, library versions (climada, climada-petals, numpy, rasterio, geopandas), config hash, assumption strings, warnings, statuses.

### 5.5 API (Flask blueprint)

| Method | Path | Behaviour |
|---|---|---|
| GET | `/risk/eligibility?run_id=` | returns tier and whether a loss can be computed; **false if no finished run** |
| POST | `/risk/run` `{run_id, profile, options}` | starts a risk job for that run only; 409 if gate fails |
| GET | `/risk/<rid>/status` / `/summary` / `/assets` / `/provenance` | read results |
| GET | `/risk/<rid>/curve` | exceedance/loss-rain curves; refused for `frequency_basis = none` |
| POST | `/risk/set` `{run_ids:[…]}` | builds a validated scenario set (T3/5) |
| POST | `/risk/adaptation` `{baseline_rid, mitigated_rid, costs, r, N}` | paired avoided loss, NPV, BCR |
| GET | `/risk/<rid>/export.zip` | GPKG, CSV, GeoTIFF, JSON, report |

Errors reuse `GateError`/`InsufficientData`; progress uses the `progress(stage, fraction)` callback of `run.py`; results cached by `model_version + run sha + config hash + climada version`.

### 5.6 Dependencies

`climada==6.2.0` (pinned), Python 3.12, `geopandas`, `rasterio`, `shapely`, `scipy`, `duckdb` (already used); Petals `==6.2.0 --no-deps` (optional); CPU only.

---

## 6. Implementation blueprint

> Illustrative; signatures checked against the 6.2.0 source, nothing executed.

### 6.1 Smoke tests (T-00, run before any code)
(a) `Hazard.check()` with a deterministic event; (b) `Centroids.from_meta` ordering equals row-major array order; (c) `ImpactCalc.impact` on a 5 × 5 synthetic grid with `centr_LS` set directly; (d) `import climada_petals.hazard.landslide` and `Landslide.from_hist` on five synthetic points (checks the `date` issue).

### 6.2 Hazard per class (with the pre-filter)

```python
import numpy as np
from scipy import ndimage, sparse
from climada.hazard import Hazard, Centroids

def mdr_class_raster(hmax, vmax, scale, damage_fn):
    h3 = ndimage.maximum_filter(np.nan_to_num(hmax), size=3)   # platform: filter first (NaN handling to be matched by parity test)
    v3 = ndimage.maximum_filter(np.nan_to_num(vmax), size=3)
    out = np.zeros_like(h3)
    idx = h3 >= 0.3
    out[idx] = [damage_fn(h, v, scale) for h, v in zip(h3[idx], v3[idx])]   # damage_fn wraps platform _ds_probs/IMP
    return out

def build_hazard(mdr_stack, meta, event_meta):
    n = mdr_stack.shape[0]
    centr = Centroids.from_meta(meta)                      # meta: crs, transform, width, height (verify keys at T-00)
    inten = sparse.csr_matrix(mdr_stack.reshape(n, -1))
    return Hazard(haz_type="LS", centroids=centr, intensity=inten, fraction=inten.sign(),
                  event_id=np.asarray(event_meta["id"]), event_name=event_meta["name"],
                  date=np.asarray(event_meta["ordinal_date"]), orig=np.ones(n, bool),
                  frequency=np.ones(n), frequency_unit="scenario (not annual)", units="1")
```
Deterministic events carry a sentinel frequency; the wrapper class `ScenarioImpact` exposes `at_event`, `imp_mat` only and raises on `aai_agg`/`calc_freq_curve`.

### 6.3 Exposure from the run's own building list, impact function, impact

```python
import geopandas as gpd, numpy as np
from climada.entity import Exposures, ImpactFunc, ImpactFuncSet
from climada.engine import ImpactCalc

def exposures_for_class(gdf, share_col, width, crs, ref_year):
    g = gdf.copy()
    g["value"] = g["value_total_pkr"] * g[share_col]          # structure+contents rows kept as separate Exposures upstream
    g["impf_LS"] = 1
    g["centr_LS"] = g["rr"] * width + g["cc"]                 # exact platform cell index (row-major)
    return Exposures(g, crs=crs, ref_year=ref_year, value_unit="PKR")

impf = ImpactFunc(haz_type="LS", id=1, intensity=np.array([0., 1.]), mdd=np.array([0., 1.]),
                  paa=np.array([1., 1.]), intensity_unit="1", name="identity on MDR")
imp = ImpactCalc(exp, ImpactFuncSet([impf]), haz).impact(save_mat=True, assign_centroids=False)   # use at_event / imp_mat
```
Totals over the three class hazards are summed; parity target is `summary.exposure.direct_loss_pkr` (§T-04).

### 6.4 Annual-loss weights (only for validated sets, n ≥ 4)
```python
def trapezoid_weights(T):
    """Weights w_k with EAL = sum(w_k * L_k); k ordered by ascending p = 1/T (rare -> frequent). Equals engine.aal.eal."""
    order = np.argsort(-np.asarray(T, float))            # T descending = p ascending
    p = 1.0 / np.asarray(T, float)[order]
    w = np.empty_like(p)
    w[1:-1] = 0.5 * (p[2:] - p[:-2])
    w[0] = p[0] + 0.5 * (p[1] - p[0])
    w[-1] = 0.5 * (p[-1] - p[-2]) + 0.5 * (1.0 - p[-1])
    out = np.empty_like(w); out[order] = w               # back to the caller's order
    return out
# EAL = q_trig * sum(trapezoid_weights(T) * L); assert it equals engine.aal.eal(T, L)["eal"] (test T-16)
# hazard.frequency = trapezoid_weights(T), frequency_unit = "quadrature weight (not an event rate)"; never call calc_freq_curve on it
```

### 6.5 Tests (all offline, small synthetic grid)

| ID | Test | Pass criterion |
|---|---|---|
| T-00 | smoke tests §6.1 | all pass |
| T-01 | 20×20 grid, a known block of (h, v), three buildings | MDR equals hand value; outside block = 0 |
| T-02 | centroid ordering | `rr*width+cc` returns the intended cell |
| T-03 | deterministic event | `aai_agg` / exceedance raise; `at_event` works |
| T-04 | **parity** on a saved Tier 3 run (total, structure, contents) | relative error < 1e-6 (else the NaN-filter or sampling difference is found and fixed) |
| T-05 | double-counting | duplicates removed; contents not inside `V_struct` |
| T-06 | gate | no run / unfinished run / wrong AOI / Tier-1 susceptibility as input ⇒ refused |
| T-07 | NoData | assets outside the valid mask are excluded and counted, never zero-loss |
| T-08 | price-year guard | mixed price years abort |
| T-09 | EAL formulas | analytic constants; fewer than 4 scenarios ⇒ no EAL; trapezoid vs bin-form difference reported |
| T-10 | NPV/BCR | hand example; refuses with empty costs; refuses without matching baseline |
| T-11 | Tier 1/2 | with no reference runs ⇒ `NOT_COMPUTED`; with a synthetic reference ⇒ loss = hand calculation |
| T-12 | `unsequa` smoke (N = 50) | reproducible with a seed |
| T-13 | time-dependent damage | `MDR_joint ≤ MDR_run ≤ MDR_platform` per building (float16 tolerance); crop offset correct (known cell); `max_t|V| ≤ vmax`; `L(t)` monotone; arrival times censored below the first frame |
| T-14 | valuation | storeys = 1 halves structure value; `contents_mode = none` changes only the contents term; both totals reported; mixed price years abort |
| T-15 | Tier 1/2 distance bands | synthetic references ⇒ hand-computed `m(b)` and loss; uncovered bands excluded and counted; volume-ineligible references rejected; zones Z0/Z1 disjoint; `NOT_COMPUTED` when no reference |
| T-16 | annual-loss weights | `trapezoid_weights` · L equals `engine.aal.eal` (< 1e-9); `aai_agg` of the weight-hazard equals the primary EAL; `calc_freq_curve` on it is blocked |

---

## 7. Validation and calibration

The platform has **no observed damage or loss data**, and openly available NDMA/PDMA figures are aggregate and not attributable to a hazard intensity or location (§4), so loss-side validation and calibration are **not performed**. Every loss figure stays `screening_only`. The table lists what could be validated now and what is blocked.

| Layer | Metric | Data | Status |
|---|---|---|---|
| Hazard occurrence | AUC, precision/recall on held-out spatial blocks | inventory | exists (`scripts/validate_spatial.py`); reuse |
| Hazard footprint | hit rate of recorded landslides inside Tier 1/2 zone/envelope and Tier 3 footprints (Petals `from_hist` if adopted, else custom) | inventory | feasible now |
| Hazard intensity | depth/speed vs measured deposits | field | likely unavailable |
| Exposure | footprint completeness/precision on a hand-digitised sample (≥ 200 buildings per AOI); position error | imagery | to do |
| Vulnerability | predicted vs observed damage-state distribution per class; MDR bias | observed building damage with intensity | **blocked** (no open source) |
| Vulnerability (desk) | envelope comparison with published debris-flow curves | literature | feasible |
| Financial | bias, MAE, RMSE, relative error, rank correlation per event/village | observed costs | **missing** |
| Probabilistic | EAL vs inventory-implied order of magnitude; completeness analysis of the inventory; sensitivity of EAL to T-set and `q_trig` | inventory | limited |
| Tier 1/2 transfer | compare the indicative loss with the Tier 3 loss where both exist for one AOI/scenario | runs | feasible |

**Calibration vs validation:** split observed events by event (preferably by valley or district), never by random buildings. Calibrate only a few identifiable parameters (fragility median scale, class multipliers); keep β from the literature unless ≥ 30 damaged buildings per class exist; re-score on held-out events; only then label any interval as predictive. `calibration_opt` may be used for the fit. **Sensitivity:** Sobol ranking from §3.13; the dominant drivers are a hypothesis to be tested (expected: unit cost, storeys, fragility medians, class mix, frequency model), and hazard-side strength uncertainty is already known to dominate absolute numbers (ch. 21).
Code-level gates: parity test in CI; `validation_status` copied from the run.

---

## 8. Dashboard specification (new "Risk & Loss" panel only)

- **Entry:** the panel is disabled, with the message "Run a simulation for this area first", until `/risk/eligibility` returns true for the selected AOI. The panel shows the tier of the selected run and the method that follows from it (modelled loss for Tier 3/4/5; screening range for Tier 1/2).
- **Overview:** run id, tier, trigger, AOI, assets affected, direct loss with parts (structure/contents/crops pass-through), exposed population, roads blocked, facilities impacted, banner with `not_calibrated`, price year and FX.
- **Map (existing Mapbox GL):** footprint, buildings by expected damage state, loss-density raster, blocked roads (pass-through), per-building popup (h, v, pressure, MDR, value, loss, lower/upper bracket). Tier 1/2: zones S and R and exposed buildings, no damage colouring.
- **Loss tables:** by damage state, district, settlement; high-loss building ranking.
- **Range display:** platform-default upper bracket, time-joint lower bracket, and sensitivity band from `unsequa` (labelled "model sensitivity", not confidence).
- **Frequency items** (EAL, exceedance) only for a validated scenario set and after acknowledgement of the assumption.
- **Compare:** two runs of the same AOI (rain vs quake, storm sizes, baseline vs climate, unmitigated vs mitigated), with the same exposure enforced.
- **Adaptation:** user enters costs, `r`, `N`; shows ΔL, NPV, BCR, or the reason they cannot be computed.
- **Provenance link** on every number; **export** GPKG, CSV, GeoTIFF, JSON, report.
Compute stays in `risk/`; the page only renders `/risk/...` responses.

---

## 9. Roadmap

| Phase | Objective | Contents | Done when |
|---|---|---|---|
| 0 | Environment, additive platform changes | conda-forge CLIMADA env; T-00 smoke tests; A1 (required), A2–A5 (optional) | smoke tests recorded; Tier 2 saves a library |
| 1 | Tier 3/4/5 modelled loss | gate, adapter, MDR hazards, exposure from saved buildings, parity (T-04), CSV/GPKG, panel | parity < 1e-6 on ≥ 2 runs |
| 2 | Brackets, sensitivity, validation scaffolding | time-joint variant, footprint-statistic option, `unsequa` driver ranking, Petals/custom hit-rate | driver ranking and brackets reported |
| 3 | Tier 1 and Tier 2 screening loss | EVaR, reference-MDR transfer, loss-versus-rain curve | works for a Tier 1 run and a saved Tier 2 library; `NOT_COMPUTED` path tested |
| 4 | Scenario sets, EAL | frequency models, exceedance, comparison with platform EAL, Petals benchmark (optional) | both EAL models reported with assumption text |
| 5 | Paired mitigation, climate comparison | avoided loss, NPV/BCR, null results | BCR only with costs and matching baseline |
| 6 | Calibration — **only if** an open or supplied dataset with building damage, location and intensity appears | fit, held-out scoring | independent validation reported; otherwise not done |

**Compute (sizes only, not benchmarks):** a 61.7 km² AOI at 30 m has 91.6 k cells; with ≈ 15 k buildings the sparse hazard (≈ 17 k non-zeros per class and event) is well under 1 MB per event and the impact matrix is small; CPU-only; measure at T-04. The risk module never reruns physics; design-storm sets reuse saved runs.

---

## 10. Risk and limitation register

| ID | Risk / limitation | Mitigation |
|---|---|---|
| R-01 | CLIMADA/Petals Python and dependency limits (xesmf, boario) | separate conda-forge environment (§5.1); Petals `--no-deps`; pin 6.2.0 |
| R-02 | Petals `from_hist` date handling and frequency idiom may conflict with Hazard 6.x | T-00(d); custom count fallback |
| R-03 | `CostBenefit`/`Measure` API changed in 6.x | verify; NPV helper |
| R-04 | `unsequa` signatures drift | read 6.2.0 source at coding time |
| R-05 | Fragility, class multipliers, β, damage ratios are assumptions | label; sensitivity; desk envelope; calibration when survey data exist |
| R-06 | Unit cost 2010 EUR × current FX; residential value for all; storeys assumed | price-basis report; optional aligned basis; storey bounds |
| R-07 | Pressure definition in docs vs code (F1) | `C_d` explicit; fix ch. 19 text |
| R-08 | Max-h/max-v pairing | bracket (§3.3); A2 |
| R-09 | 30 m grid vs building scale | footprint-statistic sensitivity |
| R-10 | Building cap 40,000 | record counts; warn |
| R-11 | Census mix district-wide; none for GB/AJK | flag; village survey |
| R-12 | Tier 1/2 have no h or v; envelope too wide (F9); reference MDR is a transfer | EVaR always; loss range only with references; upper-envelope label; prefer Tier 3 |
| R-13 | Tier 2 not saved today | A1 |
| R-14 | Frequencies exist only for rainfall; loss frequency = rainfall frequency | explicit assumption; `q_trig`; gate; both EAL models |
| R-15 | Quake EAL impossible; PGA lacks site amplification | scenario losses only |
| R-16 | Susceptibility / `p_fail` / `runout_freq` misread as probabilities | gate refuses them as hazard; labels |
| R-17 | Inventory incompleteness and reporting bias | validation use only |
| R-18 | Double-counting (duplicates, contents, facility in building, indicators vs PKR) | §3.2 rules; T-05 |
| R-19 | Centroid-order mismatch or NaN-filter difference | T-02, T-04 |
| R-20 | NoData treated as zero hazard | T-07 |
| R-21 | Data paths exist on this host (F10) but depend on `~/Desktop/DGX-Shared`; `~/flood/venv` is absent; pip install of CLIMADA fails without system GDAL (§5.1) | read paths only via `app/layers.py`/`app/paths.py`; conda-forge env; T-00 |
| R-27 | AOI of any size and resolution (up to 1.5 M cells, coarsened grids, building cap 40,000) | resolution warning, `lower_bound_truncated_exposure` label, subset-to-building-cells storage (§1.6) |
| R-28 | Inventory positions mostly 1–50 km; UGLC licence is non-commercial | per-record radius tolerance; Petals grid ≈ 0.9 km; licence note in outputs |
| R-29 | Open damage records (NDMA/PDMA news and sitreps) are aggregate, cumulative, hazard-mixed | not used for calibration; loss stays uncalibrated |
| R-22 | Design-storm sets are compute-heavy | reuse saved runs; run on request |
| R-23 | Mitigation effects are user inputs; real benefit may be small (0.5 % in the platform test) | show null results; costs from user |
| R-24 | Outputs misused for design or insurance | persistent banner and flags |
| R-25 | Out-of-scope processes (rockfall, deep-seated, utilities, crops beyond the platform rule, roads cost, indirect loss, casualties) | explicitly not computed; no zero placeholders |

---

## 11. Questions previously open, and how they were answered

| Earlier question | Answer (source) |
|---|---|
| Which AOIs are the pilot? | None. Users draw any AOI; the design is AOI-agnostic (§1.6) |
| Which inventory does the platform use; is COOLR local? | `Landslides_All.shp` (392 points: NASA COOLR, GLC, local inventories) and the UGLC Pakistan records, both local (`calibration/dataset.py`); UGLC is CC-BY-NC 4.0 (§4) |
| Do data paths exist? | Buildings and roads exist at `~/Desktop/DGX-Shared/Tasks/Reselli_AI/flood/global_data/…`; hospital/school shapefiles under `4. Vector Data/`; the OSM path in `scripts/infra_data.py` is stale and unused (F10) |
| Is a completion marker needed? | No: `summary.json` is written last and is the platform's own "finished" test (§1.4) |
| Can return periods be recovered for scenario sets? | Yes, for AAL-job runs: `manifest.rainfall.source` contains `design storm T=<T> y …`; the triangular-storm UI runs carry no T (§1.4, §3.10) |
| Are NDMA/PDMA records usable? | No open dataset with location and intensity was found; aggregate figures only; not used (§4) |
| Why a separate environment? | Operational: pip install fails without system GDAL, large dependency set, shared SAILAB environment, platform venv absent (§5.1) |

**Still open (cannot be settled from the folder or the web, needs the platform owners):**
1. Is `C_d = 2` in `building_damage` intended (F1)? Chapter 19 should be corrected either way.
2. Which CPI and FX series define the official price year (optional aligned basis, §3.5)? Without a choice the module reports the platform basis only.
3. Is a single environment preferred over the conda-forge environment recommended in §5.1?

## 12. References and verification log

Checked 2026-11-09 by web search of publisher/repository pages (abstract and bibliographic record only; full texts were not read, and the vulnerability curves were not retrieved).

| Reference | Result of check |
|---|---|
| Aznar-Siguan, G., Bresch, D.N. (2019) CLIMADA v1: a global weather and climate risk assessment platform. *Geosci. Model Dev.* 12, 3085–3097, doi:10.5194/gmd-12-3085-2019 | **Confirmed** ([gmd.copernicus.org](https://gmd.copernicus.org/articles/12/3085/2019/)) |
| Kropf, C.M. et al. (2022) Uncertainty and sensitivity analysis for probabilistic weather and climate-risk modelling: an implementation in CLIMADA v.3.1.0. *Geosci. Model Dev.* 15, 7177–7201, doi:10.5194/gmd-15-7177-2022 | **Confirmed** ([gmd.copernicus.org](https://gmd.copernicus.org/articles/15/7177/2022/gmd-15-7177-2022.pdf)) |
| Huizinga, J., de Moel, H., Szewczyk, W. (2017) *Global flood depth-damage functions: methodology and the database with guidelines*. JRC Technical Report EUR 28552 EN, doi:10.2760/16510 | **Confirmed**, incl. that country values come from maximum damage values ([JRC repository](https://publications.jrc.ec.europa.eu/repository/handle/JRC105688)). The specific "Table 3-21, Asia residential, 111 EUR/m²" value is taken from the platform's own `loss.py`/ch. 19 and was **not** re-read in the JRC report |
| Fuchs, S., Heiss, K., Hübl, J. (2007) Towards an empirical vulnerability function for use in debris flow risk assessment. *Nat. Hazards Earth Syst. Sci.* 7, 495–506, doi:10.5194/nhess-7-495-2007 | **Confirmed**; derived from one Austrian Alps event, second-order polynomial, depends strongly on construction material ([NHESS](https://nhess.copernicus.org/articles/7/495/2007/)) |
| Papathoma-Köhle, M., Keiler, M., Totschnig, R., Glade, T. (2012) Improvement of vulnerability curves using data from extreme events: debris flow event in South Tyrol. ***Natural Hazards* 64(3), 2083–2105**, doi:10.1007/s11069-012-0105-9 | **Corrected.** Revision 2 wrongly gave *NHESS* 12 |
| Quan Luna, B. et al. (2011) The application of numerical debris flow modelling for the generation of physical vulnerability curves. ***Nat. Hazards Earth Syst. Sci.* 11, 2047–2060**, doi:10.5194/nhess-11-2047-2011 | **Corrected.** Revision 2 cited a different paper (*Eng. Geol.* 2011, entrainment run-out model); the NHESS paper is the vulnerability-curve one. |
| Corominas, J. et al. (2014) Recommendations for the quantitative analysis of landslide risk. *Bull. Eng. Geol. Environ.* 73, 209–263, doi:10.1007/s10064-013-0538-8 | **Confirmed** ([record](https://ccs.upm.es/?p=3424)) |
| Kirschbaum, D.B. et al. (2015), *Geomorphology* (NASA Global Landslide Catalog) | Only the instruction on NASA's data page to cite this paper was seen in search results; volume/pages **not verified**. Cite only if COOLR/GLC data are redistributed |
| CLIMADA / Petals documentation and source | Read directly from the 6.2.0 wheels (§2); docs sites https://climada-python.readthedocs.io/ and https://climada-petals.readthedocs.io/ |

Removed because the module does not use them: Ermini & Casagli (2003) and Jibson (2007) (they underpin platform components, not this module).
Platform documents used: `README.md`, `docs/landlab/{11,16,18,19,20,21,23,24,41}_*.md`, `docs/validation/inventory_summary.json`, `docs/GILGIT_SMALL_SCALE_METHODOLOGY.md`.
