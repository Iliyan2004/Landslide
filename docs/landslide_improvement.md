# Landslide platform: repositories that can improve it

Written for: the platform owner, who needs to decide which external tools to integrate and in what order.

Basis: `docs/LANDLAB_Technical_Reference.md` (limits in Ch. 40, accuracy record in Ch. 31) and the platform code under `backend/landslide/`. Repository facts were taken from each project's public page where it could be fetched. Items marked **(verify)** come from prior knowledge, or the page could not be fetched (D-Claw and TRIGRS returned HTTP 403), and must be checked before work starts.

---

## 0. Summary

### 0.1 The core problem

The platform's physics is verified (it solves its equations) but not validated (it does not predict real events well). The technical reference says so directly:

- Physics ranks landslide *places* barely better than slope alone (AUC 0.60 against 0.57). Statistical terrain models reach 0.71–0.75.
- Rain separates landslide days from ordinary days with modest skill (AUC 0.73).
- Soil strength, friction, fragility and unit cost are scenario values, not measurements.
- No slope boreholes, no mapped deposits and no damage records exist locally. The inventory has 381 events with locations uncertain by up to 25 km.

Most of the remaining uncertainty is therefore **missing data**, not missing physics. External repositories can cross-check and refine the physics. Almost none can supply the missing data. Section 9 states this plainly for each limitation.

### 0.2 Recommended order

| Priority | Repository | Role | Effort | Licence note |
|---|---|---|---|---|
| 1 | TRIGRS (USGS) | Replace or test the pore-pressure proxy | Medium | USGS, check terms (verify) |
| 2 | Landlab | Independent cross-check of the stability ensemble; terrain tools | Low | MIT |
| 3 | r.avaflow | Reference runout solver to bracket friction | Medium | Not stated on the page; check |
| 4 | D-Claw | Reference two-phase solver for pore-pressure fluidisation | High | Check (verify) |
| 5 | OpenQuake engine | Tested ground-motion models for the quake tier | Medium | **AGPL-3.0** |
| 6 | USGS groundfailure | Benchmark for Newmark results | Low | Check; GitHub copy is archived |
| 7 | MintPy + ISCE2 | Observed deformation for validation (separate project) | High | MintPy GPL-3.0+ |

Visualisation libraries are in Appendix A. Repositories assessed and not recommended are in Section 8.

---

## 1. TRIGRS (USGS)

**Repository:** https://code.usgs.gov/usgs/landslides-trigrs (page returned 403; details **(verify)**)

### 1.1 What it is

A Fortran program for transient rainfall infiltration and grid-based slope stability. It follows Iverson's (2000) solution for pressure-head response to rainfall in a soil column, coupled with an infinite-slope factor of safety. Inputs are ASCII grids (topography, soil depth, strength, hydraulic properties, rainfall time series, initial water table).

### 1.2 How it helps

The platform computes pore pressure as `m = F / (Δθ z)`, where F is the Green-Ampt wetting-front depth (`models/infiltration/green_ampt.py`, `engine/trigger.py`). The technical reference calls this "a bounded scenario proxy for pore pressure, not groundwater head at the slip surface" (Ch. 5.1, 5.8).

TRIGRS solves the pressure head as a function of depth and time. It captures:

- the delay between rain and pressure rise at depth,
- the rise of the water table at the slip surface, and
- the effect of the initial water table and of rainfall intensity relative to conductivity.

It is the closest independent model to what the platform already does.

### 1.3 What to extract

- The Iverson (2000) pressure-head solution, as a function of depth, time, conductivity, diffusivity and rainfall history.
- The way TRIGRS combines the solution with the infinite-slope FS.
- Its input and output file formats, for a wrapper.

### 1.4 Implementation: step by step

**Phase A: run TRIGRS beside the platform on one test slope (no code changes)**

1. Create an isolated directory for TRIGRS, separate from the project, and build it with the instructions in the repository. Run its bundled example first and confirm you reproduce the shipped output.
2. Choose the Gilgit test area used in the reference run (about 20 km², 22,000 cells at 30 m).
3. Export from a platform run the grids TRIGRS needs: slope (from `rasters`/`terrain`), soil depth (`trigger.soil_depth_field`), cohesion, friction, unit weight. Write them as ASCII grids in the TRIGRS layout.
4. Convert the platform's rain series (15-minute steps, `rainfall.to_step_depths`) into the TRIGRS rainfall file.
5. Set TRIGRS conductivity, diffusivity and initial water table to the same values the platform's scenario point uses (`trigger.scenario_point`). Use the same values so that differences come from the physics, not the inputs.
6. Run TRIGRS. Read its factor-of-safety grids at several times.

**Phase B: compare**

7. Write `scripts/compare_trigrs.py` that loads the platform's `arrays.npz` (minimum FS, failure time) and the TRIGRS output on the same grid.
8. Compare, cell by cell: (a) failing area, (b) failure time, (c) which cells fail. Report the agreement as a confusion matrix and the difference in failure timing.
9. Repeat for three storms: a short intense one, a long moderate one, and the 360 mm stress test. The proxy and TRIGRS should diverge most for short intense storms.

**Phase C: decide**

10. If the two agree within the platform's own uncertainty, document that in the technical reference as a verification of the Green-Ampt proxy.
11. If they differ systematically, add an optional `pressure_model: "trigrs_like"` run parameter.
    - Implement the Iverson solution in `models/infiltration/` as a new module, vectorised over cells and on the GPU path like `engine/ensemble.py`.
    - Keep Green-Ampt as the default until the new module passes tests.
12. Add tests to `backend/tests/test_physics.py`: the new module must reproduce the analytic limits (steady-state flux, infinite time) and the TRIGRS example outputs.
13. Add a validation entry in `scripts/validate_simulation.py` (the V1–V45 series).

### 1.5 Does it fill the gap?

It substantially addresses the pore-pressure proxy (Limitation L1). It does **not** fix:

- **L2 (one soil layer, failure depth = soil depth).** TRIGRS also assumes infinite slope and a single layer in its basic form.
- **L3 (uncalibrated strength).** It needs the same cohesion, friction and conductivity values.
- **L4 (uniform rain).** It takes one rainfall series per run unless you provide several.
- Running it at national scale: it is a Fortran program on ASCII grids, so it suits pilot basins, not the 90 m country product.

---

## 2. Landlab

**Repository:** https://github.com/landlab/landlab (MIT, about 11,300 commits, `pip install landlab`)

### 2.1 What it is

A Python framework for earth-surface process modelling with a grid engine and a library of process components. The README does not list landslide components specifically. Landlab is believed to include `LandslideProbability` and `BedrockLandslider` **(verify at landlab.csdms.io)**.

### 2.2 How it helps

- An independent implementation of an infinite-slope Monte Carlo, to cross-check the Latin-hypercube ensemble in `engine/ensemble.py`.
- Hydrologic terrain tools (flow routing, flow accumulation, pit filling, depression handling) that could replace hand-written pieces such as the D8 accumulation in the dam screening and the TWI in `engine/wetness.py`.
- Hydrology components that could provide a lateral-flow or topographic wetness treatment.

### 2.3 What to extract

- The `LandslideProbability` algorithm: how it samples parameters, and how it defines the probability of failure.
- Its flow-routing and flow-accumulation functions, as a test oracle for your own.

### 2.4 Implementation: step by step

1. Install Landlab in a separate virtual environment (not the platform's).
2. Open the documentation and confirm the landslide components exist and what they require.
3. Build a Landlab grid from the same DEM window used in the Gilgit test. Load slope, soil depth, cohesion, friction and rain.
4. Run `LandslideProbability` with the same prior ranges as `configs` / `pipeline.build_spec`. Landlab's probability uses its own definition, so state exactly what each tool counts as failure.
5. Compare Landlab's failure fraction with the platform's `p_fail` raster from `engine/ensemble.pfail` for the same storm. Differences in the mobilisation rule (stable before the event, ≤ 45°) are expected; apply the same rule to both.
6. For terrain: compare Landlab's flow accumulation and channel network with `engine/dam.py` and with `engine/wetness.py`. Replace the platform's code only if Landlab is faster or more correct on a test grid.
7. Record the comparison in `docs/validation/` and add a line to the accuracy record (Ch. 31).

### 2.5 Does it fill the gap?

It strengthens verification and may simplify some terrain code. It does **not** add new physics beyond infinite slope, so L1, L2, L3, L4 remain. It does not use better soil data than you have.

---

## 3. r.avaflow

**Repository / site:** https://www.landslidemodels.org/r.avaflow/ (version 4.0 revision 7, released 2 September 2025)

### 3.1 What it is

A GIS-supported open-source tool that simulates cascading mass flows of up to three phases over arbitrary terrain. Per its page it uses a NOC-TVD scheme, a Voellmy-type friction model, a simplified Pudasaini multi-phase model, entrainment, fragmentation and phase transformation. It is a GRASS GIS tool and works with GRASS raster maps. The page does not name a licence and does not mention GPU support. Both need checking.

### 3.2 How it helps

The platform's runout solver (`engine/flow.py`, `flow_torch.py`) is a single-phase depth-averaged scheme with fixed Voellmy parameters (μ = 0.12/0.20/0.30, ξ = 200–300), a fixed fluidisation λ = 0.6 and a simple entrainment rate. The technical reference states these are scenario values, not calibrated (Ch. 7.3, 29). r.avaflow is a mature, published solver of the same class with more physics, and it is the tool the reference lists as "not available on the server" (Ch. 39).

### 3.3 What to extract

- The behaviour of its multi-phase flow on the same terrain, as a reference result.
- Its treatment of entrainment, to compare with the platform's `0.0015·v·dt` rule.
- Its input conventions (release raster, frictiograph) that a user might re-use.

### 3.4 Implementation: step by step

1. Install GRASS GIS and r.avaflow in an isolated environment or container. Check the licence.
2. Run its shipped examples and confirm that you reproduce the published figures.
3. Prepare the platform's terrain for r.avaflow: export the DEM and the release depth raster (the failed soil thickness from a platform run) as GeoTIFFs, import into a GRASS location.
4. Run a single-phase case with matching Voellmy parameters (same μ, ξ) and no entrainment. Compare maximum depth, speed and deposit with the platform on the same terrain. This is a code-to-code check.
5. Enable entrainment, then the multi-phase option. Record how the runout changes.
6. Repeat on three terrain cases: (a) the synthetic channelised slopes used for the Corominas check (`scripts/check_runout_relations.py`), (b) a Gilgit gully, (c) a flat plain case.
7. Use the differences to bracket the platform: report the range of runout length across parameter sets and across solvers.
8. If the platform systematically over- or under-runs, adjust the defaults only if a real event supports it. Otherwise, document the bracketing in the technical reference as a sensitivity range.

### 3.5 Does it fill the gap?

It improves confidence in the solver and shows how sensitive the result is to the missing physics. It does **not** fix:

- **L5 (runout friction is a scenario value).** r.avaflow also needs friction parameters. Without mapped Pakistani deposits it cannot calibrate them.
- **L6 (fixed fluidisation, simple entrainment).** It offers more options, but they also need parameters you do not have.
- It runs on the CPU as far as the page says, so it cannot replace the 0.27 ms/step GPU solver.

---

## 4. D-Claw

**Site:** https://claw.code-pages.usgs.gov/dclaw (returned 403; details **(verify)**). Believed to be in the Clawpack family: https://github.com/clawpack/D-Claw and https://github.com/clawpack/geoclaw.

### 4.1 What it is

A depth-averaged two-phase (solid and fluid) debris-flow model with a dynamic pore-pressure equation and adaptive mesh refinement, from USGS. Believed to be Fortran with a Python setup layer.

### 4.2 How it helps

The platform fixes λ = 0.6 for rain-triggered flows and 0 for quake-triggered flows. D-Claw evolves the pore pressure during the flow, so the effective friction changes as the flow runs out. This is the physics behind "pore-pressure fluidisation" that the platform only approximates.

### 4.3 What to extract

- The dynamic pore-pressure and dilatancy treatment.
- Its entrainment and the way it ties release conditions to initial solid fraction.

### 4.4 Implementation: step by step

1. Install Clawpack and D-Claw in an isolated environment. Run its bundled landslide or debris-flow example.
2. Build a Gilgit gully case: a DEM clip of a few km², one release area taken from a platform run.
3. Set up the D-Claw run with the same release volume, bed friction and initial solid fraction. Run it.
4. Compare maximum depth, speed, deposit shape and runout with the platform, as in the r.avaflow plan.
5. Do a sensitivity study on the platform's fluidisation factor (0 to 0.8) and find which value reproduces D-Claw's runout. This calibrates λ against a more complete model, not against reality.
6. Document the result in the technical reference. Change the default λ only if the study supports it.

### 4.5 Does it fill the gap?

It can inform how large λ should be for a given release, but it still needs initial solid fraction, dilatancy and friction parameters. So **L5 and L6 remain** unless mapped deposits are obtained. It is also heavier to set up than r.avaflow and is not an in-pipeline tool.

---

## 5. OpenQuake engine (hazardlib)

**Repository:** https://github.com/gem/oq-engine (AGPL-3.0)

### 5.1 What it is

The GEM seismic hazard and risk engine. Its library part (hazardlib) contains a large set of ground-motion models. The page does not confirm that BSSA14 or BC Hydro can be used standalone; check the API reference. Believed class names: `openquake.hazardlib.gsim.boore_2014.BooreEtAl2014` and `abrahamson_2015.AbrahamsonEtAl2015SSlab` **(verify)**.

### 5.2 How it helps

The platform hand-codes BSSA14 and a BC Hydro intraslab model with a −0.65 ln regional adjustment in `engine/trigger.py` (`bssa14_pga_g`, `bchydro_slab_pga_g`). A tested library would remove the risk of implementation errors and offer other models that suit the region.

### 5.3 What to extract

- Tested implementations of BSSA14 and BC Hydro, to compare against the hand-coded versions.
- Alternative models for the Himalaya, Hindu Kush and Karakoram region, and their sigma values.
- Finite-fault distance metrics (Rjb, Rrup).

### 5.4 Implementation: step by step

1. Install in a separate environment. Confirm that the GSIM classes can be called without running a full hazard calculation.
2. Write `scripts/check_gmpe_oq.py` that evaluates OpenQuake's BSSA14 and BC Hydro for a grid of magnitudes, distances, Vs30 values and depths, and compares them to `trigger.bssa14_pga_g` and `bchydro_slab_pga_g`.
3. Any difference above a stated tolerance (for example 1%) is a bug in one of them. Investigate and fix.
4. If OpenQuake works well, call it from a validation script only. Do not import it into the shipped backend, because AGPL requires releasing source for network services that use it.
5. Re-run the ShakeMap comparison (`scripts/validate_pga.py`, 398 events) with the OpenQuake models and any additional ones. Record bias and scatter.
6. If a different model fits the region better, port its equations into `trigger.py` (equations are not AGPL) and cite the paper.

### 5.5 Does it fill the gap?

It improves correctness and may reduce ground-motion bias. It does **not** fix:

- **L7 (large-event under-prediction of about 25%, near-field over-prediction).** The cause is the rupture geometry, not the equations.
- **L8 (Newmark sensitivity).** Displacement goes roughly as the fourth power of PGA near the yield point, so remaining PGA error is amplified.
- The ShakeMap benchmark is itself a model, not ground truth.

---

## 6. USGS groundfailure

**Repository:** https://github.com/usgs/groundfailure (archived 26 October 2022). Active development moved to https://code.usgs.gov/ghsc/esi/groundfailure/groundfailure.

### 6.1 What it is

USGS earthquake-triggered ground-failure code. The page does not describe the models, so the content must be confirmed in the new repository.

### 6.2 How it helps

It gives an independent estimate of earthquake-triggered landslide hazard to compare with the platform's pseudostatic and Newmark results (`models/seismic/newmark.py`, `trigger.seismic_failures`).

### 6.3 Implementation: step by step

1. Clone the active GitLab repository, not the archived copy. Read its model list and input requirements.
2. Run its example for a past earthquake covered by the ShakeMap archive in `datasets/external/shakemap`.
3. Run the platform's Tier 4 for the same event. Compare the area of predicted failures and their spatial pattern.
4. Check against the 31 earthquake-triggered inventory reports (`validate_quake_landslides.py`). The reference notes this sample is too small to show skill.

### 6.4 Does it fill the gap?

It provides a benchmark, not a fix. The earthquake limitations remain: no calibration to a mapped inventory of a specific earthquake, **L8**, and **L9** (no site-specific slip surface).

---

## 7. MintPy and ISCE2 (optional, separate project)

**Repositories:** https://github.com/insarlab/MintPy (GPL-3.0+) and https://github.com/isce-framework/isce2

### 7.1 What they are

ISCE2 processes SAR data into interferograms. MintPy turns a stack of interferograms into ground-displacement time series. MintPy needs coregistered, unwrapped interferograms and geometry files (DEM, incidence angle), per its page.

### 7.2 How they help

They provide **observed** surface deformation. That is the only thing on this list that adds evidence the platform lacks:

- slow-moving landslides in the north, which can be mapped and used to test where the model predicts instability,
- a way to build dated event information that is missing from the 381-event inventory,
- seasonal deformation linked to rainfall, which could test the antecedent-wetness behaviour.

### 7.3 Implementation: step by step

1. Define the study area, a mountain valley with steep slopes (Gilgit region), and obtain Sentinel-1 SAR scenes for one or two tracks over several years. The scenes need a data account and several gigabytes of storage.
2. Process interferograms with ISCE2 (or a hosted pipeline) and produce unwrapped stacks.
3. Run MintPy's `smallbaselineApp.py` to produce velocity and time-series maps.
4. Threshold the velocity map to flag moving slopes. Check them manually against optical imagery to remove artefacts (snow, vegetation, layover and shadow in steep terrain).
5. Compare the flagged slopes with the platform's national stability layer: do the model's unstable cells coincide with observed movement? Report AUC with block cross-validation as in Ch. 26.
6. Optionally compare the seasonal deformation with the rain record to test antecedent timing.

### 7.4 Does it fill the gap?

It adds data, not physics, and it is the only route here to better validation. It does **not** fix:

- Steep mountain terrain degrades InSAR (layover, shadow, snow, decorrelation under vegetation). Many of the fastest and most dangerous slides cannot be seen.
- It sees slow creep, not the rapid debris flows the runout model simulates.
- It gives line-of-sight displacement, not slip-surface depth or strength.
- **L3 (no strength data), L2 (no slip surface depth) and L5 (no deposits)** are unchanged.

---

## 8. Assessed and not recommended for the platform

| Repository | Reason |
|---|---|
| CB-Geo MPM (https://github.com/cb-geo/mpm) | Large-deformation soil (MIT, C++/MPI, no GPU mentioned). No landslide example on its page. Too heavy for a regional 700,000-cell model, and it needs material parameters you do not have. Use only for a single-gully study if field data become available. |
| Woo (https://github.com/woodem/woo) | Discrete-element method for granular materials, CPU/OpenMP, GPL-2.0. Particle scale; cannot model million-cubic-metre flows. |
| Project Chrono (https://github.com/projectchrono/chrono) | Multibody and multiphysics library (BSD-3) with granular modules and GPU options. Built for vehicles and robots. Possible use for barrier-impact studies, but not for the core. |
| YADE (https://gitlab.com/yade-dev/trunk) | Discrete-element code, GPL-2.0+. Same scale problem as Woo. |
| ParFlow (https://github.com/parflow/parflow) | 3D watershed flow (GPL-2.1, MPI, CUDA/Kokkos builds). Real groundwater, but needs subsurface properties you lack on slopes; too heavy for regional runs. |
| Near-real-time EQIL (https://github.com/QingleCheng/Near-real-time-prompt-assessment-for-regional-EQIL) | Newmark from recorded ground motions (MIT; Python, C++, MATLAB). Needs recorded accelerograms; the platform has none. |
| LandslideHazard (https://github.com/ashokdahal/LandslideHazard) | Machine-learning notebooks (MIT). Data and weights are not in the repository (by request to the author). The platform already has a statistical layer. |

Why they fail the test: they are particle or high-resolution continuum methods. Their input needs (grain properties, soil tests, boreholes, accelerograms) match exactly the data the platform lacks, so using them would mean inventing parameters at higher resolution.

---

## 9. Remaining limitations after integrating everything above

Each limitation is stated separately, with what the repositories do and do not change.

### L1. Pore pressure is a proxy from a wetting front
- **Addressed by:** TRIGRS (partly), Landlab (cross-check only).
- **Remaining:** TRIGRS still uses infinite slope and one layer. Lateral and perched flow need ParFlow-class models, which require subsurface data.

### L2. Failure depth equals soil depth; one soil layer; no deep-seated slides
- **Addressed by:** nothing on this list.
- **Remaining:** All of it. Needs boreholes or geophysical lines on mountain slopes (seismic refraction, resistivity). GIMLi/ResIPy could process such data once collected, but the data do not exist.

### L3. Soil strength is unmeasured; the preset dominates every absolute number
- **Addressed by:** nothing on this list.
- **Remaining:** All of it. Needs shear tests, back-analysis of documented failures, or both. The six strength parameters stay as priors.

### L4. Rainfall is spatially uniform, from a point or a 0.1° reanalysis that smooths cloudbursts
- **Addressed by:** nothing here. The gridded-rain option already exists in the platform but cannot be tested on this inventory.
- **Remaining:** All of it. Needs gauge or radar rainfall at storm scale.

### L5. Runout friction (μ, ξ) is a scenario value by flow type
- **Addressed by:** r.avaflow and D-Claw for bracketing, not calibration.
- **Remaining:** Calibration to Pakistani events. Needs at least one mapped deposit with a rainfall record; the platform can already score a run against an observed extent (Ch. 30).

### L6. Single-phase model with fixed fluidisation and simple entrainment
- **Addressed by:** r.avaflow and D-Claw as reference results.
- **Remaining:** Replacing the platform solver with a two-phase one is not recommended. The GPU speed advantage would be lost, and the extra parameters have no data behind them.

### L7. Ground motion: scatter 0.40 ln units; large events low by about 25%; no directivity
- **Addressed by:** OpenQuake (correctness, alternative models).
- **Remaining:** Finite-fault geometry per event, directivity, and station data are not in the platform. ShakeMap itself is a model, not truth.

### L8. Newmark displacement is highly sensitive to PGA and to the critical displacement
- **Addressed by:** groundfailure (benchmark), OpenQuake (better PGA).
- **Remaining:** The fourth-power sensitivity is mathematical, so any PGA error is amplified. The choice of 2 cm against 5 cm changes the result from almost none to several km². Needs an earthquake with a mapped landslide inventory to calibrate.

### L9. The inventory is small and imprecise (381 events, up to 25 km position error, 269 day-resolved)
- **Addressed by:** MintPy/ISCE2 (partly, for slow movers).
- **Remaining:** Rapid events, the main hazard, are not captured by InSAR in steep terrain. A better optical or radar event catalogue would be needed.

### L10. Damage fragility, loss values and building heights are assumed
- **Addressed by:** nothing on this list.
- **Remaining:** All of it. Needs post-event damage surveys in Pakistan. Gilgit-Baltistan and Azad Kashmir have no census rows, so a national mix is used there.

### L11. Terrain resolution (SRTM 29 m)
- **Addressed by:** nothing here.
- **Remaining:** Gullies, scarps and road cuts are not resolved. A higher-resolution DEM would help; the platform already warns about coarse cells.

### L12. Average annual loss assumes a T-year storm gives the T-year loss
- **Addressed by:** nothing on this list.
- **Remaining:** CLIMADA (Appendix B) offers a standard risk framework to cross-check the integration, but the assumption comes from the data, not the code.

### L13. Rock slopes, rockfall, snow avalanche and glacial-lake outbursts are not modelled
- **Addressed by:** nothing on this list. Project Chrono might serve rockfall impact studies.
- **Remaining:** All of it; these are separate hazard models.

---

## 10. Overall assessment

| Question | Answer |
|---|---|
| Can these repositories improve the platform? | Yes, in verification, correctness and bracketing of uncertainty. |
| Can they close the physical gaps? | Only partly. TRIGRS is the one most likely to change results; the rest give cross-checks. |
| Do they fill the data gaps? | No. Only InSAR adds observations, and only for slow movers. |
| What would improve accuracy most? | A mapped deposit with its rainfall record (to calibrate runout), slope boreholes or geophysics (to constrain depth and strength), and a larger, better located inventory. |

Suggested sequence: TRIGRS comparison, then Landlab cross-check, then OpenQuake check, then reference runs in r.avaflow and D-Claw. Treat MintPy as a separate funded project. Whatever is done, keep the labels `screening_only` and `not_for_engineering_design` until validation against real events exists.

---

## Appendix A: Visualisation repositories

| Repository | Use | Licence |
|---|---|---|
| https://github.com/visgl/deck.gl | GPU layers over the Mapbox map: terrain, animated flow, extruded buildings | MIT (verify) |
| https://github.com/maplibre/maplibre-gl-js | Open fork of Mapbox GL, no token | BSD-3 (verify) |
| https://github.com/CesiumGS/cesium | Globe with 3D Tiles; time-dynamic scenes | Apache-2.0 (verify) |
| https://github.com/mrdoob/three.js | Base of the existing 3D viewer | MIT |
| https://github.com/gkjohnson/three-gpu-pathtracer | Photoreal still renders | MIT (verify) |
| https://github.com/matsuoka-601/WebGPU-Ocean | Screen-space fluid rendering for a viscous debris look; needs a WebGPU browser | check |
| https://github.com/pyvista/pyvista | Scientific 3D plots and videos for reports | MIT (verify) |
| https://github.com/developmentseed/titiler | Cloud-optimised raster tiles for the national product | MIT (verify) |

How to try them without installing: use each project's live examples (deck.gl gallery, three.js examples, Cesium Sandcastle), then a cloud notebook or sandbox.

## Appendix B: Supporting tools

| Repository | Use |
|---|---|
| https://github.com/CLIMADA-project/climada_python | Cross-check the average-annual-loss integration (GPL-3.0, verify) |
| https://github.com/Ouranosinc/xclim | Extreme-value fitting, alternative to the Gumbel IDF code |
| https://github.com/r-barnes/richdem | Slope, curvature, flow accumulation test oracle |
| https://github.com/gimli-org/gimli | Process geophysical data for slip-surface depth, once such data exist |

## Appendix C: Safety checklist before installing any repository

1. Check the licence (AGPL and GPL affect shipping a product).
2. Check last commit date and open issues.
3. Read install scripts and requirements before running them.
4. Use a separate virtual environment or container; never the platform's environment.
5. Do not place the Mapbox token (`.env`) or other credentials near a sandbox.
6. Reproduce the project's shipped example before using it on your data.
