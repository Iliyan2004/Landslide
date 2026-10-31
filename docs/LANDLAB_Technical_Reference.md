# 1. Executive Summary

LANDLAB models landslides in Pakistan: where slopes can fail, when rain or an earthquake makes them fail, how far the failed mass travels, and what it hits. It is built the way SAILAB is built (draw an area, choose a tier, watch an animated 3D result) but it is a separate product with a separate physics engine. **Flooding is not part of LANDLAB and nothing in it is coupled to SAILAB's flood solver.** The only things shared are the server's data files and the look of the interface.

## 1.1 What LANDLAB computes

| Tier | Question | Method | Time |
|---|---|---|---|
| 1 Screening | Which slopes are prone? | National CNN-DNN susceptibility (north), terrain, stability ensemble, exposure | seconds |
| 2 Instant | How much rain does each slope need to fail? | Library of factor-of-safety maps over a rain ladder, critical-rain map | about 1 s |
| 3 Physics run | What happens in this storm? | Green-Ampt infiltration, infinite-slope FS(t), failure timing, time-stepped Voellmy runout, impacts | tens of seconds |
| 4 Earthquake | What happens in this earthquake? | Joyner-Boore PGA from a rupture on the nearest fault, Newmark displacement, the same runout engine | tens of seconds |

A **national product** (all of Pakistan, 90 m, 164 districts) is built from the same stability physics, tile by tile, on the GPU.

## 1.2 Status of every feature

| Feature | Status |
|---|---|
| Tiers 1 to 4, national product, districts, basins | Implemented and tested (121 unit tests) |
| Rainfall sources: design storm, forecast, recent, ERA5, CHIRPS, CSV | Implemented |
| Impacts: buildings, roads, hospitals and schools, direct loss | Implemented (all thresholds assumed, Ch. 18) |
| Live monitoring with webhook, compare runs, PDF report, MP4 export | Implemented |
| Rainfall-threshold validation against the inventory | **Done** (Ch. 26) |
| Spatial validation, physics and ground calibration, runout check, ShakeMap comparison, quake-landslide check | **Run** (Ch. 27 to 30, 6.2, 32) |
| Design storms from observed IDF, climate multiplier, average annual loss | Implemented and **run once on a 57 km2 Gilgit area** (Ch. 21); the climate signal is within model spread, and the loss is an order of magnitude |
| Nature-based levers, barriers, ranking, automatic barrier placement | Implemented and **run once on the same area** (Ch. 23, 24); this exposed a counting artefact for planting and a placement bug, both fixed |
| Landslide-dam screening, rainfall hotspots, scoring against an observed extent | Implemented (dam screening and hotspots run on real data; observed scoring needs a supplied extent) |
| Rockfall simulation (GPU Monte Carlo, barriers, impacts) | Implemented and run on a Hunza area; friction set against published shadow angles, **not calibrated to Pakistani deposits** (none exist on the server; Ch. 14) |
| Debris, earthquake and rockfall visualisation | Rebuilt and checked by rendering (Ch. 33) |
| Spatially varying ground, access and isolation impacts, GIS export, token and rate limit, run clean-up, IMERG rainfall | Implemented |
| Physics, ground, runout and PGA calibration and validation | **Run** on the real inventory, ShakeMaps and synthetic slopes; results and their weak points in Ch. 27 to 32 |


> **Honest summary of accuracy today.** Every strength, friction, fragility and cost value is a scenario value. The only validation completed is the temporal one: ERA5 rainfall separates reported rain-triggered landslide days from same-place, same-season controls with an AUC of 0.73 (95% interval 0.71 to 0.76). That is real but modest skill. Nothing in this system is validated against mapped deposits, because none exist on the server.

## 1.3 Principles

- **Nothing invented.** Missing data stays missing (NODATA is never "low risk"); unknown soil strength is an explicit range, never a silent default.
- **Screening grade.** Every run carries `calibration_status`, `validation_status` and `not_for_engineering_design`.
- **GPU first, then RAM, then CPU.** The runout solver and the stability ensembles run on CUDA; arrays live in host RAM; NumPy/numba is the automatic fallback (Ch. 8).
- **Numbers from files.** This document reads its results from `docs/validation/*.json` when it is built.


# 2. System Architecture

## 2.1 Components

| Component | Where | Role |
|---|---|---|
| Web app | `backend/landslide/app/server.py`, `routes.py` | Flask, port 5070, serves the page, tiles, jobs, runs |
| Page | `app/static/app.html` | SAILAB-style layout: 2D map over a 3D pane, right-column panels, four tier tabs |
| Pipeline (Tier 1) | `app/pipeline.py` | AOI to arrays: terrain, ML layer, stability ensemble, exposure |
| Engine (Tiers 3 and 4) | `engine/trigger.py`, `flow.py`, `flow_torch.py`, `run.py` | Failure timing, runout solver (numba and CUDA), impacts |
| Run packaging | `app/runs.py`, `app/viewer.py` | Persist artefacts, build the 3D scene, Tier 2 library |
| Rainfall and layers | `app/rainfall.py`, `app/layers.py` | Rain sources, buildings, roads, facilities |
| Physics core (older) | `models/`, `data/preprocessing/`, `gates.py` | Infinite slope, Green-Ampt, Newmark, empirical runout, acceptance gates |
| Calibration | `calibration/` | Inventory, rain features, spatial validation, statistics |
| Scripts | `scripts/` | National builder, district statistics, slope raster, validation experiments, this document |

It runs on SAILAB's Python environment (`~/flood/venv`), which already has xarray, zarr, duckdb, weasyprint and CUDA torch. Only the environment is shared; no SAILAB code is imported.

## 2.2 Jobs, caching and idempotence

A heavy request starts a background thread and returns a job id; the page polls `/runs/<job>/progress.json`. One heavy job runs at a time because the server is shared. A run's id is the hash of its polygon, parameters and code version, so identical requests return the stored result. Each run directory holds `summary.json`, `manifest.json` (sources, grid, parameters, warnings), `arrays.npz`, `frames.npz` and `mapbox_3d.html`.

## 2.3 Hardware

The machine is an NVIDIA GB10 with unified memory shared by about ten users, often with only 1 to 2 GB of GPU memory free. The code therefore falls back to the CPU on any GPU failure, and releases cached GPU memory after each job. No temperature guard is applied, by the owner's decision; `LANDSLIDE_TEMP_GUARD=1` re-enables one.

## 2.4 Separation from flooding

LANDLAB has no flood tiers, no flood solver, no discharge or inundation outputs. Debris flows are modelled as a dense granular-fluid mixture with Coulomb-turbulent resistance (Ch. 7), not as water. River basins and districts appear only as ways to choose an area.


# 3. Data Sources

All paths are in `backend/landslide/app/paths.py` (one place, checked at `/api/data-status`) and can be overridden by `LANDSLIDE_<NAME>` environment variables.

| Dataset | Detail | Used for |
|---|---|---|
| SRTM DEM | `Pak_srtm.tif`, 29.16 m, EPSG:32642, 52,189 x 64,499 cells | Slope, runout terrain, national product |
| National ML susceptibility | CNN-DNN + RF ensemble, 90 m, EPSG:32643, north only (about 31.1 N and up) | Tier 1, district statistics |
| Risk stack | `05_risk`: hazard, exposure, vulnerability, population (WorldPop 2025 constrained, people per 90 m cell), built fraction | Exposure, tiles |
| ERA5-Land hourly precipitation | zarr, 1980-01-01 to 2026-05-20, 0.1 degree, mm per hour | Hindcast storms, threshold validation |
| CHIRPS daily | 5 km GeoTIFFs from 1981 | Daily hindcasts (spread evenly over 24 h) |
| Open-Meteo | hourly forecast and recent observed, live | Forecast runs, monitoring, context |
| Buildings | Google Open Buildings, 7 local parquet tiles (5.85 GB), queried with DuckDB | Building damage, 3D |
| Roads | HOTOSM Pakistan roads, indexed GeoPackage | Blocked-road length, 3D |
| Facilities | Hospitals and Schools shapefiles | Facilities hit |
| Faults | `Fault_lines.shp` | Earthquake scenarios |
| Boundaries | Pakistan border, 164 districts | National mask, district statistics |
| Basins | HydroSHEDS level 8, 1,131 basins | Choosing an area |
| Landslide inventory | `Landslides_All.shp`, 392 points (NASA COOLR reports, GLC rainfall catalogue, AJK/GB/KP local inventories) | Validation only |
| Predictor stack | `01_layers`: slope, elevation, curvature, geology, land cover, TWI, SPI, distances, rainfall climatology | Validation only |

## 3.1 What the inventory is, and is not

After cleaning, the inventory has 381 unique events. Positions are reports: the stated accuracy ranges from 0.5 km to 50 km, and for many records it is 25 km or worse. Dates are kept at the precision they were given: a bare year is never turned into 1 January. There are no deposit polygons, no measured volumes (one record), no soil measurements and no depth of failure. This caps what any validation can show (Ch. 25).

## 3.2 Known coverage gaps

- The ML susceptibility layer ends near 31 N; elsewhere it is NODATA and is never read as "low".
- The 05_risk population layer follows the same extent.
- ERA5-Land ends on 20 May 2026.


# 4. Terrain, Soil Depth and the Parameter Model

## 4.1 Terrain

Slope is the Horn (1981) 3 x 3 gradient of the DEM on a grid in the AOI's UTM zone. The analysis cell is 30 m for areas up to the interactive budget and is coarsened in 10 m steps above it so a run stays within 1.5 million cells (Tier 1) or 700,000 cells (Tiers 3 and 4). Slope is resolution dependent: coarse cells smooth steep ground away. For that reason physics is **skipped, with a message,** when cells would be coarser than 150 m (Tier 1) or 120 m (Tiers 3 and 4). A whole-country interactive run at 820 m found 0.07% of area unstable, which is an artefact of smoothing, not a result.

## 4.2 Explicit parameter ranges

Every geotechnical input is a range (`gates.check_geotech` refuses a run if one is missing). Three strength presets are provided:

| Preset | Soil depth (m) | Cohesion (kPa) | Friction (deg) |
|---|---|---|---|
| colluvium_shallow | 0.5 to 2.0 | 1 to 8 | 26 to 36 |
| residual_soil | 1.0 to 4.0 | 3 to 15 | 22 to 34 |
| weak_clayey | 1.0 to 3.0 | 2 to 10 | 15 to 26 |

Other priors: unit weight 18 kN/m3, root cohesion 0 to 5 kPa (maximum adjustable), water table 2 to 10 m, initial moisture 0.25 (capped at porosity minus 0.02). Green-Ampt parameters come from the soil texture class (Rawls-type class averages): saturated conductivity Ks, suction head and porosity, with Ks given a factor-of-10 range. All of these are **scenario priors, not measurements.**

## 4.3 Choosing one parameter set

A physics run uses one scenario point inside the ranges, chosen by a *strength quantile* q between 0 (pessimistic end) and 1 (strong end):

```
value = lo + q (hi - lo)              (Ks log-uniform)
soil depth uses the opposite end:     depth = lo + (1 - q)(hi - lo)         (weak scenario = deeper soil)
```

Tier 1 and the national product instead sample the whole range (Latin hypercube) and report the spread across members.

## 4.4 Soil depth varies with slope

By default soil thins as slope steepens (an assumption, switchable):

```
z(slope) = z_max - (z_max - z_min) * clip(slope / 50 deg, 0, 1)
```

## 4.5 Who can fail: the mobilisation rule

A rain or earthquake event can only mobilise a cell that (a) carries soil, meaning slope at most 45 degrees (steeper ground is treated as bare rock, a separate rockfall problem), and (b) was **stable before the event**, meaning FS at least 1 at the baseline water table. Cells that fail the second test would already have failed under ordinary conditions. Without this rule the model labels bare rock and perennially unstable cells as storm failures: with the weakest strength preset, 48% of the Gilgit test area was "unstable" with zero rain. The run reports the counts it excluded (`trigger.mobilisable`).


# 5. Rainfall-Triggered Failure

## 5.1 Infiltration: Green-Ampt

The wetting front depth F(t) follows Green and Ampt (1911), with infiltration equal to the smaller of rain rate and capacity:

```
f_c = Ks [ 1 + psi_f (theta_s - theta_i) / F ]
```

F does not depend on the slip depth, so it is computed once per scenario (20 sub-steps per input step). The saturated fraction of the slip layer in each cell is

```
m(t) = max( m0 , clip( F(t) / ((theta_s - theta_i) z) , 0 , 1 ) )
m0   = clip( (z - water table depth) / z , 0 , 1 )
```

This is a bounded scenario proxy for pore pressure, not groundwater head at the slip surface; rain that exceeds capacity leaves as runoff (no ponding), which is conservative for pore pressure.

## 5.2 Stability: infinite slope

```
FS = [ c' + c_r + (gamma z cos^2 b - u) tan(phi') ] / ( gamma z sin b cos b )
u  = m gamma_w z cos^2 b
```

Negative effective normal stress is clipped to zero; invalid inputs give NaN, never FS = 0; slopes under 0.5 degrees are non-failure. The saturation m at which FS = 1 is

```
m_crit = [ (c' + c_r)/(gamma z cos^2 b) + tan(phi') - tan(b) ] * gamma / ( gamma_w tan(phi') )
```

## 5.3 Failure timing

Each 15-minute step, FS is evaluated for every mobilisable cell; the first step with FS below 1 is the cell's failure time. Isolated failures smaller than 3 connected cells are dropped (pixel noise). The run records the number of failed cells against time.

## 5.4 Ensembles (Tier 1 and the national product)

For each of n members (40 by default), parameters are sampled from the ranges (Latin hypercube, Ks log-uniform) and FS is evaluated at the member's final saturation. This is exact, not an approximation: FS never increases with m, and the wetting front only advances, so the minimum over time is the value at the final m. A unit test checks it against the original time-stepped ensemble to 1e-6. The reported "share of members with FS below 1" is **conditional on the stated priors; it is not a probability.**

## 5.5 Antecedent wetness

A soil does not start every storm at the same moisture, and a front that only advances (no drainage) would otherwise treat 30 days of rain as one storm. The physics run therefore splits the rain: the storm itself drives the Green-Ampt front, and the 30 days before it set the starting state through the antecedent precipitation index

```
API = sum_i P_i k^i          daily totals before the storm, i = 1 for the day before; k = 0.90 (a ~10 day memory)
w   = clip( API / API_wet , 0 , 1 )                      API_wet = 120 mm
theta_i     = theta_r + (theta_s - theta_r) ( S_dry + (S_wet - S_dry) w )       S_dry 0.25, S_wet 0.90, theta_r 0.05
water table = water table_0 ( 1 - f_wt w )                f_wt = 0.5
```

The 30 days come from ERA5-Land (server zarr) for the same point, whichever source drives the storm (ERA5, IMERG or CHIRPS). Design storms and forecasts carry no antecedent unless the user supplies one. The constants are scenario values (`engine/antecedent.py`); `scripts/calibrate_physics.py` fits them against the event inventory with matched control days, and the fit is reported in Ch. 28 (a calibrated set is adopted only if it beats the defaults on held-out data). The main run and the mitigation evaluation build their scenario in one function (`run._scenario`) so that a paired run with a barrier or a planting always starts from the same soil as the unmitigated run.

## 5.6 Parameter-uncertainty ensemble

The single scenario moves every parameter together to one end of its prior range (the strength quantile). Setting `ensemble: n` in a run additionally draws n members by Latin hypercube with EVERY prior varied independently (cohesion, friction, depth, conductivity, water table, root cohesion), applies the same spatial-ground and antecedent adjustments to each member, and evaluates failure with the exact end-of-storm shortcut of Ch. 5.4. The outputs are a failure-probability raster (share of members in which the cell is mobilisable and fails) and the 5th, 50th and 95th percentile of the failing area. The probability is conditional on the priors and on independence between them (cohesion and friction are in fact negatively correlated in real soils); it is not a frequency of landslides. It runs on the GPU first.

## 5.7 Limits

Uniform rain over the area; no lateral flow or perched water table; no unsaturated suction strength; one soil layer; depth of failure is the soil depth, not a mapped slip surface; no rock slopes (Ch. 40).


# 6. Earthquake-Triggered Failure

## 6.1 Ground motion

The user gives a magnitude, a focal depth, an epicentre and a time. If a mapped fault lies within 25 km, the epicentre snaps to it and a rupture segment is centred on that point along the trace; otherwise the rupture is a point. The rupture length follows Wells and Coppersmith (1994): `log10 L = -2.44 + 0.59 M`. Two ground-motion models are used, chosen by depth (`SLAB_DEPTH_KM` = 40 km):

| Event | Model | Distance used | Site term |
|---|---|---|---|
| Shallow crustal, depth up to 40 km | Boore, Stewart, Seyhan and Atkinson (2014), NGA-West2, PGA, median RotD50 | Rjb: distance from each cell to the surface projection of the rupture line | Vs30 (linear and non-linear terms) |
| Intermediate depth, deeper than 40 km (Hindu Kush, Pamir) | Abrahamson et al. (2016) BC Hydro intraslab, PGA, with a regional adjustment of `SLAB_REGIONAL_LN` = -0.65 ln units | Hypocentral distance `sqrt(d_epi^2 + depth^2)` (point source) | Vs30 |

The 1981 Joyner and Boore relation is kept as `gmpe: "jb81"` for comparison only (it saturates poorly: it gives 0.56 g at 10 km for M 7.6 on rock, where NGA-West2 gives about 0.28 g).

**Site amplification.** Vs30 comes from the USGS global grid (Heath et al. 2020, 30 arc seconds; `datasets/external/vs30/vs30_pk.tif`), with a slope-based fallback (Wald and Allen 2007) where the grid has no value. Valley fill amplifies (a soil site of Vs30 300 m/s shakes about 1.4 to 1.7 times a rock site at moderate distance), so the same earthquake now shakes a river terrace harder than the ridge above it. The model name and Vs30 source are written into every quake run's summary.

## 6.2 Validation against USGS ShakeMaps

The archive holds 398 ShakeMaps (M 5.5 and above since 1973, in and around Pakistan, 4,642,259 grid cells), of which 120 are intermediate-depth events. The comparison is with the USGS product, which is itself a model (a ground-motion equation, adjusted to station data where there are stations and to site amplification), so it tests agreement with the standard product, not with ground truth. Errors are `ln(model) - ln(ShakeMap)`.

| Events | Model | Bias (ln units) | Scatter (ln units) |
|---|---|---|---|
| Shallow, up to 40 km | Joyner and Boore 1981 | 0.01 | 0.43 |
| Shallow, up to 40 km | NGA-West2 (platform default) | -0.11 | 0.43 |
| Deeper than 40 km | Joyner and Boore 1981 | 0.39 | 0.82 |
| Deeper than 40 km | NGA-West2 (wrong physics for a slab event) | 0.21 | 0.74 |
| Deeper than 40 km | BC Hydro intraslab with the regional adjustment (platform default) | -0.00 | 0.33 |
| All events | platform default model (`auto`) | -0.07 | 0.40 |

What this shows, plainly:

- For shallow events the two relations agree with ShakeMap about equally in aggregate (scatter about 0.43 ln units, a factor of 1.5). The NGA-West2 model is kept because it is the standard, has correct magnitude scaling and carries the site term. For M 7 and above both under-predict ShakeMap (see below).
- The global BC Hydro intraslab model over-predicts the Hindu Kush ShakeMaps by 0.65 ln units (a factor of 1.9) almost independently of distance, so a single regional factor is fitted. After removing it the scatter is 0.33. The factor is fitted to the ShakeMap product on all 120 events (in sample); the three magnitude and depth classes give 0.33 to 0.73, so it is not constant, only typical.
- Near-field cells (under 15 km) are over-predicted by both shallow models (about +0.5 ln units) because the rupture here is a centred line of the Wells and Coppersmith length with an unknown orientation and the distance is the distance to that line; real ShakeMaps use the mapped finite fault and, near it, station data. Large events (M 7 and above) are under-predicted by about 0.4 ln units for the same reason: a long fault puts more of the area close to the rupture than a centred line assumes. Where the finite fault is known, its trace should replace the centred line.

**Does a mapped fault trace help?** The platform already snaps the epicentre to a mapped fault within 25 km and centres the rupture segment on it (the validation script now does the same, `rupture_distance`). Comparing that with the plain centred-point distance on the 742,059 shallow-event cells that have a mapped fault within 25 km:

| Cells | Distance used | Bias (ln) | Scatter (ln) |
|---|---|---|---|
| Near field, under 15 km | centred point | 0.57 | 0.42 |
| Near field, under 15 km | fault trace | 0.17 | 0.56 |
| M 6.5 and above | centred point | -0.05 | 0.35 |
| M 6.5 and above | fault trace | -0.24 | 0.35 |

The fault trace removes most of the near-field over-prediction (+0.57 to +0.17) but widens the scatter, and for M 6.5 and above it makes the under-prediction worse (-0.05 to -0.24). So the large-event under-prediction is not a fault-geometry problem: the Wells and Coppersmith length is the subsurface rupture length, while ShakeMap uses the finite fault of each event, and the equation's own saturation also matters. Nothing was tuned to this: the model keeps snapping to a mapped fault, and the large-event bias (about a quarter lower than ShakeMap) is stated as a known limit.

> **Reading the numbers.** A scatter of 0.43 ln units means the model is within a factor of 1.5 of ShakeMap about two times in three. Newmark displacement is very sensitive to PGA (roughly the fourth power near the yield acceleration), so an error of this size is the largest uncertainty in the earthquake chapters (Ch. 13).

## 6.3 Newmark displacement

The yield coefficient of a dry slope (Ch. 5 formula with m = 0) is converted to displacement by the Jibson (2007) regression

```
log10 Dn(cm) = 0.215 + log10 [ (1 - ky/PGA)^2.341 (ky/PGA)^-1.438 ]       (sigma = 0.51 log units)
```

A cell fails if Dn is at least a critical displacement (5 cm by default; user-set). The same mobilisation rule applies (Ch. 4.5), so slopes already unstable when dry are excluded, not counted as quake failures. An optional preceding rain series can be combined with the quake (mode "both"). Released masses start moving at the quake time.

> A magnitude 6.8 earthquake on top of the Gilgit test area now gives a different picture from the 1981 relation, because the shaking depends on site conditions. The criterion matters as much as the shaking: with the 5 cm default few cells fail, while a 2 cm criterion at M 7.2 fails several square kilometres. The Gilgit example numbers are in Ch. 13.


# 7. The Runout Solver

## 7.1 Scheme

The failed soil becomes a depth-averaged flow. The solver is the local-inertial shallow-water scheme of Bates et al. (2010) on a staggered grid (discharge per unit width q on cell faces) with a Voellmy basal resistance, applied semi-implicitly. It is the scheme that the platform's earlier in-browser solver verified (docs/VALIDATION_REPORT tests V4 to V7), now in compiled code.

```
face depth        h_f = max(eta_A, eta_B) - max(z_A, z_B),   eta = z + h        (no flux if h_f <= 0.02 m)
momentum          q* = q - g h_f dt (eta_B - eta_A)/dx
Voellmy friction  m  = |q*| / (1 + dt g |q*| / (xi h_f^2))                     turbulent term
Coulomb           m  = max(0, m - h_f mu_eff g cos(theta) dt)                  dry friction on the slope
                  q  = sign(q*) min(m, 25 h_f)
mu_eff            = mu (1 - 0.6 lambda)                                         pore-pressure fluidisation
limiter           outflow of a cell is scaled so it cannot lose more than it holds
continuity        h_new = h - dt/dx (net flux)
```

Velocity is the average of face velocities (faces deeper than 5 cm), capped at 30 m/s; only cells deeper than 0.3 m report a velocity.

## 7.2 Release, entrainment and fluidisation

- **Release:** a failing cell's soil thickness (times a user factor, default 1) is moved from the bed to the flow: the bed drops by the thickness and the flow gains it, so no mass is created.
- **Entrainment:** where depth exceeds 0.5 m and speed exceeds 2 m/s, the bed gives up soil at `0.0015 v dt min(1, h/2)` until a user-set erodible depth (default 0.5 m, cells that did not fail) is exhausted. The bed lowers by what the flow gains.
- **Fluidisation:** rain-triggered flows use a pore-pressure ratio lambda of 0.6, which lowers the friction coefficient by 36%; earthquake-triggered flows use zero.

## 7.3 Flow types

The friction parameters are **scenario values by flow type, not calibrated to any event** (calibration is planned, Ch. 30):

| Type | mu | xi (m/s2) |
|---|---|---|
| Debris flow / mudflow | 0.12 | 200 |
| Earth / soil flow | 0.20 | 250 |
| Shallow slide, short runout | 0.30 | 300 |

## 7.4 Time stepping and frames

The step is the smaller of the CFL step and 0.2 s. The cap matters: the semi-implicit friction is first order in time, and at 0.5 s the steady speed on a uniform slope was 12% low (12.2 against 13.9 m/s), at 0.1 s it is 2.4% low. Releases happen at their failure times; the solver advances only while something is moving and jumps over quiet periods (after 300 s at rest). The animation window runs from two minutes before the first failure to 30 minutes after the last, sampled at 120 evenly spaced frames.

## 7.5 Verification (not validation)

| Check | Result |
|---|---|
| Closed-domain mass conservation | drift 0 to machine precision |
| Lake at rest over rough ground | flux exactly 0 |
| Steady speed on a 0.5 slope, mu 0.2, xi 400, h 1.5 m | within 5% of sqrt(xi h (tan b - mu cos b)) at dt 0.1 s |
| Rest below the friction slope | interior flux 0 |
| Entrainment | bed loss plus flow gain sums to 0 |
| GPU against CPU | agree to 1e-15 (float64) and 2e-6 m (float32) |

These show the code solves its equations. They do not show it predicts real runout; see Ch. 30.


# 8. GPU Implementation and Numerical Findings

## 8.1 Backends

Compute order is GPU, then RAM, then CPU.

| Work | GPU path | Fallback |
|---|---|---|
| Runout solver | `flow_torch.FlowStateGPU`: whole-domain tensor ops, float32 with the DEM offset removed (about 1e-4 m resolution) | numba parallel kernels |
| Stability ensemble (Tier 1, national) | torch, one tensor pass per member, percentiles by sorting along the member axis | NumPy |
| Frames, rasters | host RAM (float16 frames) | n/a |

Both solver backends give the same dynamics (unit test). The page shows which backend ran.

## 8.2 Making the GPU worth using

A step is about 100 small tensor operations, so a naive GPU loop is launch-bound. Measured on the 640,000-cell grid (800 x 800):

| Variant | ms per step |
|---|---|
| numba, 20 cores | 2.66 |
| CUDA, float64, graph | 7.2 |
| CUDA, float32, graph | 1.38 |
| CUDA, float32, `torch.compile` fused kernels, graph | **0.27** |

The solver captures a CUDA graph (one launch per step; the time step is a device scalar so the graph is reused) and, for grids of 300,000 cells or more, fuses the elementwise operations with `torch.compile` (about 20 s of compilation per grid shape, cached). Small grids use the plain graph path: on a 22,000-cell area the CPU is actually faster (0.11 ms per step) than the GPU (0.3 ms), but the platform follows the owner's GPU-first rule.

## 8.3 Findings

- **Thread overhead.** With 20 numba threads a 22,000-cell grid took 8.8 ms per step against 0.11 ms with one thread; the thread count is now chosen from the grid size (one thread per 60,000 cells, at most 8).
- **Shared GPU memory.** Free GPU memory has been 1.4 to 1.9 GB of 131 GB because other users hold the rest; context creation has failed with out-of-memory. Every GPU entry point catches this and falls back to the CPU, and cached blocks are released after each job.
- **National build.** The 90 m national stability product took about 2 minutes per tile on the CPU and about 10 s per tile on the GPU (90 tiles, 49 with land).
- **Mass check.** Reported with every run: released plus entrained minus final volume was 2.8 m3 on a 1.0 million m3 flow.


# 9. The Tiered Workflow

The page follows SAILAB's pattern: an area is chosen once (drawn, uploaded as a shapefile or GeoJSON, or taken from a district or a HydroSHEDS basin) and stays visible above four tier tabs. Each tier answers a question at a different cost.

| | Area limit | Output | Needs rainfall series |
|---|---|---|---|
| 1 Screening | up to the whole country (physics only below 150 m cells) | susceptibility, stability share, exposure | rain intensity and duration only |
| 2 Instant | up to about 1,350 km2 | critical-rain map, failing area against rain | no |
| 3 Physics | up to about 700,000 cells (at most 120 m) | failure times, flow over time, impacts, loss | yes |
| 4 Earthquake | same as Tier 3 | PGA, failures, flow over time, impacts | optional |

A sixth tab, **Rockfall**, runs the separate rock simulation (Ch. 14). A fifth tab, **Mitigate**, holds nature-based levers, barriers (drawn on the map, optionally auto-placed) and average annual loss (Ch. 23, 24, 21). The right-hand column also holds area discovery (district ranking by national metrics, basins), a rainfall context panel, live monitoring, layer pickers for the finished run, run history, comparison and the PDF report.


# 10. Tier 1: Screening and the National Layers

## 10.1 National layers

The map offers four national layers as XYZ tiles read straight from the rasters (reprojected to Web Mercator per tile): the ML susceptibility (north only), the risk index, the national physics share (share of ensemble members with FS below 1 under 20 mm/h for 24 h on the colluvium preset), and slope at 90 m. The physics layer is built by `scripts/build_national.py`: EPSG:32642, 90 m, 2048-cell tiles, resumable, GPU first, only mobilisable cells counted. Slope from a 90 m average understates local slope, so it is a regional screen.

## 10.2 District statistics

`scripts/build_districts.py` summarises the 164 districts: area share and population above susceptibility 0.7, mean risk index, and the physics share on the physics product's own country-wide grid (the susceptibility grid covers only the north). Districts can be ranked by any of these and used as an area.

## 10.3 Area screening

For a drawn area, Tier 1 reads the DEM at 30 m (or coarser), the ML layer, runs the stability ensemble for the chosen rain, optionally Newmark with a scenario PGA, and a reach-angle run-out envelope (Corominas-style H/L, not a simulated depth), then reports population in the area and in unstable and reached cells. Population is people per 90 m cell and is rescaled by cell area when resampled; reading it bilinearly onto a 30 m grid had counted each person nine times (Ch. 38).

> The ML layer is an external product trained on these reports with a random split and flat-ground negatives. It ranks slope proneness; it does not describe a specific storm.


# 11. Tier 2: Instant Stability Library

Tier 2 is the landslide counterpart of an instant preview. For one area it computes median-parameter factor-of-safety maps for a ladder of 24-hour rain totals (0, 25, 50, 100, 150, 200, 300, 450 and 600 mm, uniform over 24 h) under the chosen texture, preset and strength quantile. The browser then interpolates between rungs as the slider moves, with no server call.

The **critical-rain map** assigns each mobilisable cell the rain at which FS first falls below 1, interpolating FS linearly between rungs (cells that never fail within 600 mm stay empty). The page also gives the failing area against rain and the median critical rain.

Example (Gilgit test area, colluvium preset, sandy loam, strength quantile 0.3): nothing fails at 100 mm, 5.3 km2 fail at 300 mm, and the median critical rain is about 170 mm. The same area under the weakest preset leaves 48% of cells already unstable when dry, so they are excluded (Ch. 4.5) and the library reports the excluded count.


# 12. Tier 3: The Physics Run

## 12.1 Stages

| Stage | What happens | Where |
|---|---|---|
| terrain | DEM at 30 to 120 m, slope, valid mask | `engine/run.py` |
| trigger | parameter point, soil-depth field, mobilisation mask, FS(t), failure times | `engine/trigger.py` |
| flow | event-ordered runout on the GPU, frames sampled every 30 s or more | `engine/flow_torch.py` |
| impact | buildings, roads, facilities, population, loss | `engine/run.py` |
| save | arrays, frames, manifest, 3D scene | `app/runs.py`, `app/viewer.py` |

## 12.2 The event loop

Failures are grouped by failure time. The loop alternates between the next release and the next frame time, advancing the flow only while mass is moving. A run with no failures says so and explains why instead of returning an empty map.

## 12.3 What a run returns

Failing area and soil depth; released, entrained and final volume with a mass check; impacted area, maximum depth, maximum speed and runout from the source; counts of failed cells against time; maximum depth, speed, deposit, scar, failure-time, minimum-FS and slope rasters; impacts (Ch. 18 and 17); the 3D scene.

## 12.4 Reference run (a stress test, not a design storm)

Gilgit test area (about 20 km2, 22,000 cells at 30 m), triangular storm of 60 mm/h peak for 12 h (360 mm), colluvium preset, strength quantile 0.3, debris flow, entrainment on: 1,329 failing cells (1.20 km2), 0.96 million m3 released plus 65,000 m3 entrained, 3.6 km2 impacted, maximum depth 7.1 m, maximum speed 11.9 m/s, runout 1.3 km, 24 s end to end on the GPU. A 70 mm/h peak storm on the same area impacts 3.9 km2 (maximum depth 7.3 m), only slightly more than the 60 mm/h run, whereas an M 7.2 earthquake with a 2 cm Newmark criterion on the same area impacts 12.4 km2 with depths up to 19.7 m. Outcomes are very sensitive to the trigger and to the strength scenario (Ch. 4.3).


# 13. Tier 4: Earthquake Scenario

The tab takes a magnitude, a focal depth, an epicentre (clicked on the map or the area centre), the time after the start of the animation, the Newmark criterion, an option to snap to the nearest mapped fault, and an optional preceding rainfall series. It previews the rupture length and mean PGA at 0 to 150 km, then runs the same pipeline as Tier 3 with the failures set by Newmark displacement (Ch. 6). Outputs add the PGA raster. Faults can be drawn on the map.

The shaking now carries a site term (Vs30 from the USGS global grid) and a separate intermediate-depth model for the Hindu Kush and Pamir earthquakes (a focal depth over 40 km switches to it). Both were compared with 398 USGS ShakeMaps (Ch. 6.2): the scatter against ShakeMap is 0.40 ln units over all events. There is still no calibration to a recorded landslide inventory of a specific earthquake, so the result is a scenario of pattern and order of magnitude, not a forecast for a specific earthquake.


# 14. Rockfall Simulation

Rockfall is a separate hazard from debris flow: the mass is a set of discrete rocks that fly, bounce and roll, not a continuum. LANDLAB simulates it with a three-dimensional Monte Carlo on the DEM, on the GPU first (`engine/rockfall.py`, `rock_run.py`).

## Release

Rocks start at rest on **steep rock faces**: cells at least 50 degrees (adjustable), the same slopes the soil model excludes as bare rock (Ch. 4). Up to 150 release cells are chosen, weighted toward the steepest; each releases 40 rocks (adjustable, 60,000 rocks at most). Alternatives: user-drawn source polygons, or an earthquake, where cells with PGA of at least 0.10 g are weighted by shaking and slope. Diameter is lognormal (median 0.8 m, sigma 0.35 in ln units, clamped 0.2 to 6 m); density 2,600 kg/m3, so the median rock weighs about one tonne. Release times are staggered over 20 s for the animation only; the physics of each rock is independent.

## Motion

Time step 0.04 s. Each rock is a sphere with position and velocity:

```
flight:     vz -= g dt                                    (no air drag)
contact:    the centre reaches ground + radius -> the rock is put back on the surface and an impulse is applied
  fast (normal speed > 1.5 m/s):  tilt the normal by a random sub-grid roughness angle, then
                                  v_n' = -Rn v_n,   v_t' = Rt v_t
  slow (sliding or rolling):      v_n' = 0,   |v_t| -= mu |v_n|        (Coulomb / rolling resistance per step)
stop:       |v| < 0.2 m/s for 1 s;  also stop if it leaves the area or t > 100 s
```

Surface properties come from the land-cover raster and are **scenario values**, with friction scaled by 0.45 after a check against published runout statistics (Ch. 14.9):

| Surface | Rn | Rt | mu |
|---|---|---|---|
| Bedrock | 0.46 | 0.86 | 0.30 |
| Talus | 0.32 | 0.76 | 0.45 |
| Soil | 0.22 | 0.60 | 0.60 |
| Forest | 0.17 | 0.52 | 0.66 |
| Snow / ice | 0.15 | 0.50 | 0.22 |

Each is multiplied by shape factors (round 1, angular 0.8/0.9/1.25, platy 0.6/0.8/1.5, assumed) and jittered by 15% (Rn) and 10% (Rt) per impact. The **sub-grid roughness angle** (default 9 degrees) stands in for terrain detail that a 30 m DEM does not carry; it is the most sensitive parameter and is not yet calibrated.

## Barriers (rockfall fences)

A fence is a line of cells with a height and an energy capacity. A rock reaching it below the fence height with energy under the capacity **stops there**; above the capacity it passes with the capacity removed from its energy; above the fence height it passes unchanged. Nothing else is assumed.

## Outputs

Per cell: the share of released rocks that passed (reach probability), the maximum translational energy (0.5 m v2), the maximum bounce height above ground. Per rock: stop point and **reach (travel) angle**, the angle of the line from release to stop, which can be compared with the shadow angles of 22 to 32 degrees in the literature. A set of 250 tracked rocks is recorded every 0.12 s for the animation. Translational energy omits rotation, which can add up to 40% for a rolling sphere.

## Impacts

A building or road is reached if at least 1% of released rocks pass its cell (3 x 3 neighbourhood). Buildings and road lengths are classified by the worst energy class reaching them: below 10 kJ, 10 to 50, 50 to 300, 300 to 1000 and above 1000 kJ (the classes used to specify fences). Facilities and population in reached cells are reported. **No damage ratio or loss is computed for rockfall, because no rockfall fragility is available here.**

## Tests

Five synthetic-terrain tests: rocks start on the cliff, run down and stop on the flat with a reach angle below the slope angle; translational energy never exceeds the released potential energy (energy is dissipated, never created); a soft surface shortens the runout; a strong high fence stops everything above it and the stops are counted at the fence; the same seed gives the same result.

## Reference run

Hunza (Karimabad), 6 x 5.5 km, about 8% of cells at 50 degrees or steeper: 120 release cells, 4,800 rocks (median 1.0 t), 68 s end to end on the GPU. 95% of rocks stop, 5% leave the area, the median reach angle is 46 degrees and the 10th percentile 39 degrees. Only 0.5% of rocks have a reach angle below 27.5 degrees, so these rocks are **stopping much sooner than the literature shadow angle suggests**: with the uncalibrated surface and roughness values the model is probably too dissipative on this terrain. The peak translational energy is 38 MJ, the 95th percentile bounce height 4.7 m, and 1.8 km of road is reached, mostly above 1,000 kJ. These numbers are an uncalibrated first look, not a hazard assessment.


## 14.9 Check against published shadow angles

No Pakistani rockfall deposits are on the server, so the dissipation was checked on a synthetic profile (250 m cliff at 60 degrees, 700 m talus at 36 degrees, flat floor, 30 m cells). With the original friction the first percentile of the reach angle was 36 degrees; the literature shadow angle (the angle to the farthest 1% of rocks) is 27 to 32 degrees, and the median reach angle of rocks that stop on a 36 degree talus is 33 to 42. A sweep of roughness (5 to 13 degrees), restitution (0.8 to 1.25 times) and friction (0.15 to 1 times) showed that only friction moves the result materially: a factor of 0.4 to 0.5 gives a first percentile of 29 to 31 degrees and a median of 34 to 35 (`docs/validation/rockfall_shadow.json`). A factor of 0.45 is applied. This sets the order of magnitude of the dissipation from the literature; it is not a field calibration, and the Hunza reference numbers above predate it.


# 15. Rainfall Sources

| Source | Resolution | Notes |
|---|---|---|
| Design storm | 15 min | Triangular (peak at mid-storm, SAILAB convention) or constant; user peak and duration |
| Open-Meteo forecast | hourly | Next 1 to 7 days; the same service SAILAB uses |
| Open-Meteo recent | hourly | Observed past days |
| ERA5-Land hindcast | hourly, 0.1 degree | Pick dates, or take the wettest 72 h at the location since a chosen year |
| IMERG half-hourly | 30 min, 0.1 degree | NASA GPM IMERG V07 from 2000 (monthly files on the server); each slot is a depth, returned as mm/h. Resolves short bursts better than hourly ERA5-Land; not yet compared with it for landslide skill |
| CHIRPS daily | daily, 5 km | A daily total is spread evenly over 24 h, because CHIRPS has no sub-daily information; intensities are therefore understated |
| Uploaded CSV | any | A time column (ISO or elapsed hours) and a rainfall column; unit is mm/h or mm per interval; negative, non-numeric or non-increasing times are rejected |

Rain is applied uniformly over the area. Every series is resampled to 15-minute steps with mass preserved (`to_step_depths`), and carries its source, start time, total, peak and duration into the run manifest. A series longer than 14 days is refused.

> ERA5-Land is a model reanalysis on a 0.1 degree grid: it smooths convective cloudbursts, which dominate Pakistani landslide triggers. Hindcasts with ERA5 therefore understate peak intensities at a point. This affects the validation in Ch. 26 equally for events and controls, but it lowers the achievable skill.


# 16. Design Storms and Climate Scaling

## Source data

A per-cell rainfall-indices cube already on the server (built by another task, read-only): ERA5-Land hourly precipitation 1980 to 2025 (0.1 degree) reduced to the annual maximum accumulation over running windows of 1, 2, 3, 6, 12 and 24 h, and a GPM IMERG V07 30-minute product (2000 to 2026) giving annual maxima of intensity over 30, 60, 90, 120 and 180 minutes. The IMERG variable is an **intensity in mm per hour** (checked in the file's attributes); the depth for a duration is intensity times duration. Using it as a depth would have inflated sub-hourly storms (found when the 1 h hyetograph summed to 9.1 mm instead of 8.0 mm).

## Return-period depths

For each duration, a Gumbel (EV1) distribution is fitted by L-moments to the 46 annual maxima, which is stable at that sample size where a three-parameter GEV is not:

```
alpha = l2 / ln 2,   xi = l1 - 0.5772 alpha
depth(T, D) = xi - alpha ln( -ln(1 - 1/T) ),    T = 2, 5, 10, 25, 50, 100, 200 years
```

Depth is forced non-decreasing in duration. A 90% interval comes from 100 parametric-bootstrap refits. A synthetic test recovers known parameters (xi 39.8 against 40, alpha 12.0 against 12). The record is 46 years, so 100- and 200-year values are extrapolations and the interval says so.

## The hyetograph

An alternating-block hyetograph: the incremental depths of the cumulative curve P(D) are sorted and the largest block is placed at the middle, the next either side, and so on. P(D) is interpolated log-log between the fitted durations. Below one hour the shape comes from the IMERG ratio of depth at D to depth at 60 minutes (median over years) and the level from ERA5; without IMERG the 1 to 3 h power law is extended. The total depth equals the fitted IDF depth exactly (tested at 3, 6 and 24 h; checked at Gilgit: 17.85, 28.03 and 65.93 mm for T = 100). Storms are limited to 24 h, the longest window of the record. **Point rainfall is used: no areal reduction factor is applied**, which is conservative for the areas this platform runs.

> At Gilgit the observed 100-year, 24 h depth is only 66 mm, whereas the reference test storm of Ch. 12 (360 mm) is five times that. It is an extreme stress test, not a design storm. Elsewhere, such as the Kashmir monsoon belt, the 24 h depths are several times larger. ERA5-Land smooths cloudbursts, so every depth here is a lower bound for short durations.

## Climate scaling

The delta-change method with the NASA NEX-GDDP-CMIP6 daily precipitation archive on the server: for up to eight models, the Gumbel T-year daily value is fitted to 1985 to 2014 (historical) and to the chosen future window (2036 to 2065 or 2071 to 2100, SSP2-4.5 or SSP5-8.5); the ratio of the two is taken per model and the **median ratio** is used as a multiplier on the design storm. Taking the ratio cancels each model's own bias against observation. Reading the yearly files (about 30 MB each, up to 480 files) takes minutes, so it runs only when asked and is cached by location, scenario, period and return period. Only daily data exist, so the multiplier is applied uniformly to all durations; sub-daily intensification is probably stronger than daily and is not represented. **Not yet run on real data.**


# 17. Intensity-Duration Thresholds and Live Monitoring

## 15.1 Global thresholds

For the watch tier the platform uses published global curves, not a Pakistan-specific fit (Ch. 26 shows a fit does no better on the available data):

```
Caine (1980):             I = 14.82 D^-0.39    (mm/h, D in hours, 0.167 to 500 h)
Guzzetti et al. (2008):   I = 2.20  D^-0.44    (mm/h, D in hours, 0.1 to 1000 h)
```

For a rain series the maximum mean intensity over 1, 3, 6, 12, 24, 48 and 72 h is compared with the curve; exceedance at any duration is reported. The status is always `experimental_unvalidated`, and the page says a threshold exceedance is a watch, never a prediction. An antecedent precipitation index (k = 0.98 per hour on the last three days) is shown beside it.

## 15.2 Live monitoring

A watch stores an area, a forecast-intensity threshold (default 10 mm/h), a check interval and an optional webhook. A scheduler thread wakes every 60 s and checks the watches that are due: it fetches the Open-Meteo forecast for the area centre, and when the forecast peak crosses the threshold (and the previous check had not) it starts a Tier 3 run on that forecast and posts to the webhook. Watches are stored in `datasets/state/watches.json`.

> Monitoring uses a point forecast and uniform rain, and the Tier 3 physics is screening grade; an automatic run is an early look, not a warning.


# 18. Exposure and Damage

## 16.1 Exposure layers

| Layer | Source | Rule |
|---|---|---|
| Buildings | Google Open Buildings, local parquet tiles via DuckDB | Footprints whose centroid is inside the area; each takes the 3 x 3 cell maximum of flow depth and speed at its centroid; assumed height 6 m (3D only) |
| Roads | HOTOSM roads | A segment is blocked if flow depth at a vertex or at the segment midpoint is at least 0.5 m; blocked length is summed |
| Hospitals, schools | government shapefiles | Impacted if depth at the point is at least 0.3 m |
| Population | WorldPop 2025 via 05_risk | People per 90 m cell, rescaled by cell area; people in cells reached at 0.3 m or more |

## 16.2 Building damage

Dynamic pressure from the flow, a lognormal fragility for four damage states, and a floor from burial depth:

```
p (kPa) = rho v^2 / 1000,   rho = 1800 kg/m3
P(DS >= k) = Phi( ln(p / median_k) / 0.6 ),   medians 5, 15, 40, 100 kPa for DS1 to DS4
burial floor: depth >= 0.3 / 1 / 2 / 4 m  ->  at least DS1 / DS2 / DS3 / DS4
damage ratio by state: 0, 0.05, 0.20, 0.55, 1.00
```

The expected damage ratio is the probability-weighted ratio. Buildings in cells that never reach 0.3 m are DS0. **Every threshold above is an assumption inherited from the earlier prototype; none is calibrated to observed damage in Pakistan.**

## 16.3 3D colouring

The 3D viewer colours buildings by the expected damage from the depth reached so far (a curve of 0, 0.05, 0.20, 0.55 and 1.00 at 0, 0.3, 1, 2 and 4 m), so a building changes colour as the flow arrives. Roads turn when blocked.


# 19. Estimated Direct Loss

Direct loss is, for each building, expected damage ratio x footprint area x 35,000 PKR per square metre x 1 floor, summed. This is an order-of-magnitude figure for comparing scenarios: the unit cost, the single floor and the use of footprint area are assumptions, and indirect losses (road closure days, business interruption, crops, lives) are **not** estimated. The Gilgit reference run (Ch. 12.4) gives a direct loss of about PKR 2.4 billion for 14,400 buildings in the area, with 2,469 buildings damaged at DS1 or above and 648 at DS3 or above.

> Average annual loss, which needs a defensible event-frequency model, is planned (Ch. 1.2). Rainfall return period would be the frequency proxy, and that assumption (storm frequency equals landslide frequency) will be stated where it is used.


# 20. Access and Isolation Impacts, and GIS Export

## Access

A blocked road is a poor measure of consequence on its own. After a debris-flow run the platform builds a network from the HOTOSM roads in the area (vertices snapped to a 5 m grid), removes segments blocked at 0.5 m depth, and asks which buildings and facilities lose road access.

- A point is **cut off** when its nearest road node is in the largest connected component before the event but not after. Components that were already disconnected are not blamed on the event (a test checks this).
- Points farther than 400 m from any road are not assessed.
- For hospitals and schools, the shortest path to a central node of the network is compared before and after, giving the extra distance or a cut-off flag.

Gilgit reference (3.6 km2 flow, 14,458 points): 39% of buildings were cut off; the largest road component fell from 88% to 46% of nodes; of the 58 hospitals and schools assessed, several were cut off and a few faced detours of 70 to 230 m. Limits: the network ends at the area boundary, so connection through the outside world is unseen; distance only, no speeds or capacity; missing OpenStreetMap roads make isolation overestimated.

## Spatially varying ground

By default one strength set applies to the whole area. With **spatially varying ground** (off by default) the platform reads land cover and geology rasters. Root cohesion comes from land cover (trees 6 kPa, crops 1.5, rangeland 0.5, flooded vegetation 2, bare, built, snow and water 0; mid-range assumptions) and replaces the scenario root cohesion where the land cover is known. **Geology multipliers on cohesion and friction are all 1.0:** the national geology raster has 16 colour-coded units whose lithology is only guessed from map colours, so strength values for them would be invented. The mechanism exists so calibration can fit multipliers on held-out data (Ch. 28). In the Gilgit reference storm, switching it on raised the failing area from 1.2 to 4.4 km2, because land-cover root cohesion is mostly zero on the steep slopes (the default scenario assumed 0 to 5 kPa everywhere). Land cover is a strong lever, and it is an assumption.

## GIS export

`/runs/<id>/export.zip` gives: GeoTIFF rasters in the analysis CRS (DEM, slope, maximum depth and speed, deposit, scour, failure time, minimum FS, PGA, rock reach, energy and bounce height as available); GeoJSON polygons of the failure zones and the debris or rock-reach extent; GeoJSON and CSV of buildings with damage state, loss and rock energy class; affected roads; the manifest with all parameters and warnings; the summary. Nodata is -9999.


# 21. Average Annual Loss

Average annual loss (AAL) is the expected loss per year from landslides triggered by storms. The platform runs design storms of the chosen return periods (Ch. 16), each a full Tier 3 simulation with the same ground and strength settings, and takes the direct loss of each (Ch. 19).

```
p = 1 / T                                       annual exceedance probability
AAL = integral of loss over p
  between the rarest and most frequent scenario:  trapezoid in p
  beyond the rarest (p < 1/Tmax):                 loss held at the rarest scenario's value
  between the most frequent scenario and p = 1:   loss falls linearly to zero at p = 1
```

A test checks the trapezoid against an analytic integral, and that zero loss gives zero AAL and more loss gives more.

> **The assumption that carries the number:** a T-year storm gives the T-year loss. That ignores antecedent wetness, the spatial pattern of rain, and the fact that most storms of a given depth cause no landslide at all; it also depends on the strength scenario, which is uncalibrated (Ch. 28). Treat AAL as an order of magnitude for comparing places or options, not as an insurance figure. It also inherits every assumption in the damage and cost model.

Each return period is an expensive simulation, so the page asks for confirmation.

## First run on a real area

Gilgit, a 57 km2 area (7.8 by 7.3 km) around the test site (`scripts/run_area_demo.py`, `docs/validation/area_demo.json`), strength preset "calibrated_reports", six return periods from 2 to 100 years, 6 hour storms from the observed IDF cube:

| Return period (y) | Storm depth (mm) | Failing area (km2) | Direct loss today (PKR M) | Direct loss, SSP5-8.5 (PKR M) |
|---|---|---|---|---|
| 2 | 15 | 0.09 | 160 | 296 |
| 5 | 18 | 0.14 | 559 | 675 |
| 10 | 21 | 0.17 | 836 | 861 |
| 25 | 24 | 0.22 | 1,142 | 1,194 |
| 50 | 26 | 0.27 | 1,399 | 1,406 |
| 100 | 28 | 0.33 | 1,713 | 1,754 |
| **Average annual loss** | | | **334,966,325 PKR** | **417,545,325 PKR** |

The climate factor for the 50 year, 24 hour rainfall under SSP5-8.5, 2036 to 2065, is 1.016 (ensemble median over 8 CMIP6 models whose individual ratios range from 0.90 to 1.32). A factor that close to 1 with that spread is **no detectable change**, not a prediction of none.

Cautions that apply to these numbers:

- The loss rises faster than the failing area (the 2 year loss is 160 M for 0.09 km2, the 5 year 559 M for 0.14 km2): the loss depends on which buildings the flow happens to reach, so it moves in steps. The SSP5-8.5 column is higher mainly at the frequent end (296 against 160 M at 2 years) because a 1.6% deeper storm tips a few more buildings into damage; that is a threshold effect of the building layer, not a doubling of hazard.
- The AAL adds a frequent tail (storms more frequent than the 2 year, linear to zero at p = 1) that contributes 39,909,663 PKR of the total; the result is therefore sensitive to the 2 year loss.
- Every caveat above in this chapter applies: loss frequency is taken equal to rainfall frequency, with no antecedent wetness. Read the figure as an order of magnitude for this area, not a budget.


# 22. Landslide-Dam Screening

Where a runout deposit blocks a drainage line, a lake can form. The screening answers three questions about each blocking deposit: how big is the dam, how big a lake would it hold, and is it likely to be stable. It does **not** route a breach flood downstream: that is flood modelling, which is outside this product (the breach peak is given as a single number).

1. **Channels:** D8 flow accumulation on the pre-event DEM (pits filled); cells draining at least 0.5 km2 are channels. The drainage area is truncated at the edge of the analysed area, so it is a lower bound.
2. **Dams:** connected deposit of at least 2 m (3 x 3 neighbourhood) that sits on a channel. Height Hd is the greatest deposit thickness on the channel cells; volume Vd is the connected deposit volume.
3. **Stability:** the dimensionless blockage index of Ermini and Casagli (2003)

```
DBI = log10( Ab Hd / Vd )          Ab in m2, Hd in m, Vd in m3
likely stable if DBI < 2.75,  likely unstable if DBI > 3.08,  uncertain between
```

4. **Lake:** the crest is the highest post-event bed on the channel cells of the dam; the lake is the connected region upstream with pre-event bed below the crest, and its volume is the sum of (crest minus bed) times cell area.
5. **Breach peak:** `Qp = 0.607 V^0.295 h^1.24` (Froehlich 1995, an embankment relation, used here only as a screening number), with V the lake volume and h the crest minus thalweg height.

A synthetic valley test checks that a deposit across the channel is found, that DBI equals the formula and the lake is positive, that a deposit up the valley wall is not a dam, and that the Froehlich value reproduces the earlier prototype's 9,014 m3/s test case. Lake fill time needs an inflow, which is not known here, so it is not estimated.


# 23. Nature-Based Solutions

Three levers act on the stability inputs inside the whole area (an optional zone polygon is supported by the model; the page applies the whole area). They are **scenario levers: the size of each effect is the user's input, with plausible defaults, not a measured performance.** The platform reports the change against the unmitigated run under the same storm and strength scenario.

| Lever | What it changes | Default |
|---|---|---|
| Planting | adds root cohesion to the stability equation (Pa) | +5 kPa |
| Regrading / terracing | caps the slope used for stability at an angle | 30 degrees |
| Subsurface drainage | scales the saturated fraction m and deepens the baseline water table | m x 0.6, water table +2 m |

The mobilisation rule (Ch. 4) uses the mitigated inputs too, so cells made stable are not counted. Regrading changes the slope in the stability calculation only, not the terrain the flow runs over; a regraded slope that still fails therefore runs out over the original relief, which is a simplification.

## Ranking the combinations

The page can rank all seven non-empty combinations of the three levers by the failing area they remove. This is a **stability-only** evaluation (no flow, about a second each), so it ranks the benefit to initiation, not to runout. A full mitigated run (below) then gives the change in impacted area, blocked roads, buildings damaged and loss.

Tests: each lever never increases failure; a 25 degree cap on a 33 degree slope removes failure; the ranking returns seven options ordered by reduction.

## First run on a real area, and a counting artefact that was fixed

On the 57 km2 Gilgit area (60 mm/h triangular storm for 12 h, strength preset "calibrated_reports") the first ranking, by the area that is *stable before the storm and fails in it*, put planting alone at 23% **more** failure than the baseline. That is not physical. The model counts only slopes that were stable before the storm (Ch. 4.5), because a slope that is already unstable would have failed earlier. Extra root cohesion turns slopes that were unstable (not counted) into slopes that are stable before the storm and then fail in it (counted), so the "failing" area could rise while the instability fell.

The ranking now uses the **unstable area at the end of the storm, including slopes that were already unstable** (`unstable_km2`, `failing_area` in `engine/run.py`). Every lever is compared on the same cells, so a lever can only remove instability. The "failing" figure is still reported for reference. A unit test checks that planting never increases the unstable area.

| Levers | Unstable area (km2) | Change against the baseline (22.0 km2) |
|---|---|---|
| planting + regrading | 0.0 | 100% less |
| planting + regrading + drainage | 0.0 | 100% less |
| planting + drainage | 8.4 | 62% less |
| planting | 13.4 | 39% less |
| drainage | 18.6 | 15% less |
| regrading + drainage | 18.6 | 15% less |
| regrading | 22.0 | 0% less |

How to read it: planting is the strongest single lever here (the fitted soil is weak, 0.9 kPa cohesion, so added root cohesion matters most), and planting with regrading removes all instability. Regrading to the default 25 degree cap on its own does nothing for the saturated storm: a soil of friction angle 30 degrees with a fully saturated slip layer has a factor of safety below 1 even at 25 degrees, so a lower slope alone is not enough. These effect sizes (6 kPa root cohesion, 25 degree cap, drainage lowering saturation) are user inputs, not measurements, and the ranking is a stability-only comparison; the runout benefit needs a full mitigated run.


# 24. Barriers and Automatic Placement

## The barrier model

A barrier (check dam, retaining wall) is a polyline drawn across the flow path with a height and width. It is applied by raising the bed under the wall in the runout solver, so the flow stops against it, ponds, or overtops it as the physics decides; no special rule makes it hold.

**Height is measured above the ground immediately upslope of the wall.** On a grid the bed falls by tan(slope) x cell size across one cell, so the wall cell is raised by `height + tan(slope) x cell`. Without this a wall lower than the ground drop across one cell does not even stand above its upslope neighbour: a test with a "6 m wall" on a 0.35 slope and 20 m cells let 90% of a flow pass before the rule was added. With it, the 6 m wall holds back more than 80% of a 2 m deep, 11 m/s slug and a 12 m wall holds back more than a 6 m wall. Overtopping by momentum (run-up v2/2g is about 6 m at 11 m/s) is physical and is not suppressed.

A wall narrower than a cell is widened to one cell. Barriers are not drawn in the 3D scene; they appear on the 2D map, and their effect shows in the flow.

## Automatic placement

The optimiser searches the position along the main flow corridor, the height (2 to 12 m) and the length (40 to 400 m) of up to four barriers with differential evolution, under a hard limit on the number of simulations.

- The corridor is the steepest-descent path from the failing cell nearest the centroid of the baseline run's failing cells, followed while the baseline flow reached 0.3 m.
- **There is no surrogate model:** every candidate is a full simulation (about 24 s on the GPU for the reference area), so 30 simulations take about 12 minutes. The result is a good option under the budget, not a proven optimum.
- The objective is direct loss plus a blocked-road penalty plus a wall cost; **the wall cost is a user input because no cost data exist here.** With a zero cost the optimiser will pick the largest walls, and the page says so.

Tested on a synthetic valley with a toy objective: the corridor follows the downhill path, the budget is respected, and the optimiser lowers the objective.

## First run on a real area

The same 57 km2 Gilgit area, 60 mm/h triangular storm for 12 h, 2 barriers, a budget of 16 simulations (`area_demo.json`, 37 minutes). The first attempt returned barriers of zero length: cells outside the area had been filled with a high elevation, so the pit-filling step flooded the whole area flat and no flow path existed. That bug is fixed (`flow_corridor` now leaves outside cells empty so they act as outlets; the corridor is 7 cells, 210 m). The result:

| | Baseline | With the best 2 barriers |
|---|---|---|
| Direct loss (PKR M) | 21,537,329,605 | 20,964,246,479 |
| Buildings with damage state 3 or worse | 6,155 | 5,965 |
| Impacted area (km2) | 25.8 | 25.7 |

Two barriers (one 11 m high and about 400 m long, one 3 m high) cut the loss by about 2.7%. That is small because the slide here is 8.6 km2 of failing hillside sending 21 million m3 across a 26 km2 area: the failure is spread over thousands of release cells, so a barrier on one flow path intercepts only a share of it. The optimiser works as a tool, but this storm scenario is too large for barriers to matter; it is meant for one gully-sized failure, and the scenario is useful mainly as a limit on what barriers can do. With a 16 simulation budget the result is "a better option", not an optimum.


# 25. Calibration and Validation Protocol

## 18.1 What can and cannot be validated

| Question | Can it be checked here? | How |
|---|---|---|
| Does the code solve its own equations? | Yes | Unit tests and analytic checks (verification, Ch. 7.5) |
| When does rain trigger landslides in Pakistan? | Partly | Dated rain-triggered reports against matched control days (Ch. 26) |
| Where are slopes prone? | Partly | Reports against random places, scored over each report's accuracy disc (Ch. 27) |
| Are soil strength parameters right? | Only through their effect on the two items above | Calibration against reports with block cross-validation (Ch. 28) |
| Is simulated runout and depth right? | Only against published empirical relations | No mapped deposits exist locally (Ch. 30) |
| Is building damage or loss right? | **No** | No damage records exist locally |

## 18.2 Rules that apply to every experiment

1. **Controls are matched, not convenient.** Temporal controls are the same place on other days of the same season; spatial controls are scored over discs with the same radius distribution as the events, so a large location uncertainty cannot manufacture skill.
2. **Positional uncertainty is carried, not ignored.** A report with a stated accuracy of r km only says the slide lies somewhere within r km.
3. **Honest cross-validation.** Temporal models are cross-validated leaving one year out; spatial models leave out whole 1 degree blocks, repeated with different fold assignments. A random split lets neighbouring points leak between train and test and inflates AUC.
4. **No leakage.** The national ML susceptibility map was trained on these reports; it is never used as a feature in a cross-validated model, and its own scores on them are labelled optimistic.
5. **Uncertainty is shown.** AUC intervals come from a cluster bootstrap (an event and its controls resample together).
6. **No absolute probabilities.** Reports depend on population and roads. Outputs are relative likelihoods, not annual probabilities.
7. **Results are written to JSON** (`docs/validation/*.json`) and this document reads them, so numbers cannot drift.

## 18.3 The inventory after cleaning

Duplicates (same place within 5 km and the same day, or the same stated year for undated records) are merged keeping the most precisely located record. Day-resolved dates are used for temporal work; year-only and month-only strings are not promoted to a day. Trigger classes (rain, earthquake, GLOF, snow, anthropogenic, unknown) come from the cause fields. Location accuracy is parsed from the stated accuracy text, and a record with none is given 25 km and flagged.

| | Count |
|---|---|
| Unique events | 381 |
| With a day-resolved date | 269 |
| Rain-triggered, day-resolved | 111 |
| Accurate to 1 km or better | 117 |
| Accurate to 5 km or better | 166 |


# 26. Validation 1: Rainfall Skill (completed)

## 19.1 Design

Every day-resolved, rain-triggered report from 1981 to 2026 is an event (373 events). For each, 20 controls were drawn at the same location on other days within 30 days of the same day of the year (any year 1981 to 2025), never within 7 days of a report within 25 km (7,460 controls). Features are computed identically from ERA5-Land hourly rain: the maximum mean intensity over D hours ending within the event day (D = 1 to 168), the day total, and antecedent rain over 3, 7, 14 and 30 days before the day.

## 19.2 Single-feature skill

| Feature | AUC | 95% interval |
|---|---|---|
| Intensity 1 h | 0.690 | 0.664 to 0.717 |
| Intensity 3 h | 0.702 | 0.677 to 0.728 |
| Intensity 6 h | 0.710 | 0.685 to 0.738 |
| Intensity 12 h | 0.719 | 0.693 to 0.746 |
| Intensity 24 h | 0.733 | 0.709 to 0.759 |
| Intensity 48 h | 0.730 | 0.706 to 0.755 |
| Intensity 72 h | 0.726 | 0.703 to 0.748 |
| Day total | 0.705 | 0.678 to 0.732 |
| Antecedent 7 days | 0.652 | 0.630 to 0.677 |
| Antecedent 30 days | 0.604 | 0.583 to 0.626 |
| Antecedent precipitation index | 0.649 | 0.625 to 0.674 |

AUC 0.5 is no skill. Skill is flat across durations from 1 to 72 h and the antecedent measures add nothing.

## 19.3 Combined models (leave-one-year-out)

| Inputs (logistic) | AUC | 95% interval |
|---|---|---|
| 24 h intensity | 0.728 | 0.704 to 0.754 |
| 1 h and 24 h | 0.725 | 0.701 to 0.753 |
| 3 h, 24 h, antecedent 7 d | 0.732 | 0.711 to 0.755 |
| 24 h intensity and API | 0.731 | 0.709 to 0.755 |

Adding inputs does not beat the 24 h intensity alone.

## 19.4 Thresholds

| Threshold | Share of events above | Share of control days above | TSS |
|---|---|---|---|
| Guzzetti et al. (2008), as published | 58% | 27% | 0.32 |
| Caine (1980), as published | 3% | 0% | 0.03 |
| Curve fitted here, in sample | | | 0.35 |
| Curve fitted here, leave-one-year-out | 56% | 33% | 0.23 |

The fitted curve (1.417 D^-0.275) is close to Guzzetti's and does **not** generalise better out of sample, so the platform keeps the published Guzzetti curve for the watch tier. Caine's curve is too high to be useful in Pakistan: it flags almost nothing.

## 19.5 Reading this result

> Rain discriminates event days from ordinary days with modest skill. The ceiling is set by the data, not by the physics: ERA5-Land at 0.1 degree smooths convective bursts, report locations are uncertain by kilometres (so the grid cell may be wrong), and only 269 of the 381 cleaned reports carry a day-resolved date (the rest cannot be used here). Satellite rainfall at sub-daily resolution (IMERG is on the server) might raise this; that has not been tested.


# 27. Validation 2: Spatial Skill

## 20.1 Design

Events are the unique inventory reports inside the northern study area (rain, unknown and earthquake triggers). Controls are ten uniformly random points per event over the valid mask, each scored over a disc with a radius drawn from the events' radius distribution. A point's score aggregates 160 random cells in its disc (mean, 90th percentile, maximum and area share of slope between 15 and 45 degrees, terrain and land-cover composition). Terrain comes from a 30 m slope raster built from the SRTM DEM.

Predictors compared, all cross-validated by 1 degree spatial blocks (5 folds, repeated 5 times):

| Predictor | Notes |
|---|---|
| Slope only | the baseline any model must beat |
| Physical instability index | infinite-slope critical saturation with default parameters, no fitting |
| Terrain | slope, elevation, curvature, relief, roughness |
| Hazard-only boosted trees | terrain, TWI, SPI, drainage, geology, land cover, rainfall climatology, fault distance |
| Hazard-only plus physics | adds the physical index |
| Report-aware | adds distance to roads and cities, which encode *reporting* bias |

Results are also split by location accuracy (1 km or better, 1 to 5 km, over 5 km).

## 20.2 Result

624 events, 6,112 random controls; AUC on held-out 1 degree blocks, interval by bootstrap over blocks.

| Predictor | AUC | 95% interval |
|---|---|---|
| Slope only | 0.574 | 0.503 to 0.656 |
| Physical instability index, shipped parameters | 0.596 | 0.528 to 0.668 |
| Terrain (boosted trees) | 0.714 | 0.664 to 0.754 |
| Hazard-only (terrain, hydrology, geology, land cover, rain) | 0.753 | 0.708 to 0.799 |
| Hazard-only plus physics | 0.752 | 0.708 to 0.799 |
| Hazard-only plus the new ground layers (GLiM, texture, bedrock, Vs30) | 0.733 | 0.675 to 0.793 |
| Report-aware (adds distance to roads and cities) | 0.763 | 0.720 to 0.805 |

What this says:

- The infinite-slope physics ranks reported landslide places only a little better than slope itself (0.60 against 0.57; the intervals overlap). On this inventory the physical model, with its generic parameters, is not a strong locator.
- Statistical models using terrain, hydrology and land cover do clearly better (0.71 to 0.75). Physics adds nothing to them (0.752 against 0.753).
- The new ground layers did **not** help; they lowered the score (0.733) because the extra inputs over-fit the 600 events. This agrees with Ch. 29.
- Adding road and city distance gives 0.763: reporting bias is small compared with the terrain signal, but not zero.
- Skill falls with location uncertainty: AUC 0.82 for reports located within 1 km, 0.83 for 1 to 5 km, 0.73 beyond 5 km, as expected when a report's position is only known to its accuracy radius.

> The existing national ML map reports AUC 0.88 to 0.90 (and 0.80 here on mean probability, with the caveat that it was trained on these reports). Its negatives are half flat ground, at least 5 km from any landslide, and its test split is random. This experiment uses random negatives and block cross-validation, so the numbers are lower and the two are not comparable.

The physics model's job in the platform is runout, impacts and scenario testing, where the statistical models cannot help; for *where* landslides are likely, the national ML susceptibility layer (Tier 1) is the better guide, and the physics run should be read as "if this slope fails".


# 28. Calibration of the Physical Parameters

## 21.1 Idea

The infinite-slope plus Green-Ampt model has few parameters that matter: cohesion, friction angle, soil depth, saturated conductivity, root cohesion and the baseline water table. They are unmeasured, so they are calibrated: choose the values that make the model's predicted instability best separate reported events from controls, using the real ERA5 rain of each event day and the real terrain in each report's accuracy disc, then test on terrain and years that were held out.

## 21.2 Method

For each event and control, K = 256 random cells in the accuracy disc supply slopes; the preceding 14 days of ERA5 hourly rain give the Green-Ampt wetting front once per sample (it does not depend on the cell); each cell's FS at the final saturation follows from the closed form (Ch. 5.4); the score is minus the 10th percentile of FS over mobilisable cells. All samples are evaluated in one GPU batch, so thousands of parameter sets can be tried by differential evolution. Block cross-validation (spatial) and leave-one-year-out (temporal) guard against over-fitting; parameters are constrained to physically plausible ranges (the same bounds as `validate_ranges`).

## 21.3 Extension: spatially varying parameters

The server holds lithology (GLiM), soil texture (SoilGrids), land cover and NDVI. A lookup of cohesion and friction multipliers by lithology class, and of root cohesion by land cover, can be added, with the multipliers shrunk toward 1 so that a few reports cannot fit noise. This is only worth keeping if it improves the held-out score.

## 21.4 Result

144 rain-triggered reports located to within 10 km, each with matched control days at the same place and season, scored on 34 days of ERA5-Land rain (31 days of antecedent rain plus a 3-day storm window). Differential evolution fitted eleven parameters (the six strength and hydraulic values plus the five antecedent-wetness constants of Ch. 5.5) on four fifths of the spatial blocks and scored the fifth held out, five times.

| Quantity | Value |
|---|---|
| Held-out AUC, shipped defaults | 0.593 |
| Held-out AUC, defaults plus antecedent wetness at its initial constants | 0.593 |
| Held-out AUC, calibrated | 0.683 |
| Calibrated values (median over folds) | c=916, phi=29.9, cr=444, z=2.54, wt=6.74, ks=7.3e-05, api_wet=54.9, k=0.955, s_dry=0.318, s_wet=0.955, f_wt=0.202 |

The calibrated set beat the defaults by more than the 0.02 adoption margin, so the antecedent constants are the platform's defaults now (`engine/antecedent.py`) and a strength preset "calibrated_reports" carries the fitted soil depth (2.5 m), cohesion (0.9 kPa) and friction (29.9 degrees).

Read this with care:

- Most of the gain comes from the fitted strength being weak (cohesion near the bottom of its allowed range) and from the antecedent terms together; the antecedent wetness at its initial constants added nothing on its own. The fit says what makes the model rank *reported* landslide days above ordinary days, not what the true soil strength is. The fitted conductivity, water table and root cohesion sit at the edges of their ranges and are not carried into the presets: they are partly absorbing errors elsewhere (ERA5 smoothing the bursts, report bias).
- Held-out folds differ a lot (0.58 to 0.72 for the first two folds) because there are only 144 events, so the 0.68 has a wide interval.
- The skill is relative: it ranks days, it does not predict how many landslides occur.


# 29. Calibration of the Spatial Ground

## 22.1 Data

Four layers were downloaded for this chapter (`datasets/external/`, `scripts/download_ground_data.py`, `build_glim_pk.py`, `build_vs30_pk.py`):

| Layer | Source | Use |
|---|---|---|
| Lithology | GLiM v1.1 (Hartmann and Moosdorf 2012), 16 first-level classes, grouped into six strength groups | cohesion and friction multipliers |
| Soil texture | SoilGrids 2.0, clay, sand and coarse fragments, mean of 5 to 60 cm, 250 m | cohesion and friction multipliers |
| Depth to bedrock | SoilGrids 2017 (BDTICM), 250 m (median 39 m over Pakistan) | slip-depth cap |
| Vs30 | USGS global grid (Heath et al. 2020) | earthquake site term (Ch. 6) |

## 22.2 Method

Events are the 625 inventory reports (rain, unknown and earthquake triggers) in the northern study area; controls are ten random points per event with the same location-accuracy radii. Each point is scored on 160 cells of its disc by the 90th percentile of the physical instability index (how little saturation brings the cell to FS = 1) computed with that cell's own cohesion, friction, depth and roots. Variants add one layer at a time to a three-parameter base fit (c, phi, z). Every variant is fitted by differential evolution on four fifths of the 1 degree blocks and scored on the fifth, five times; ground coefficients are shrunk toward neutral by a small penalty.

## 22.3 Result

| Variant | Held-out AUC |
|---|---|
| Mean slope, no fit | 0.590 |
| Base physics, shipped values | 0.541 |
| Base physics, fitted | 0.563 |
| plus lithology | 0.592 |
| plus soil texture | 0.652 |
| plus bedrock-depth cap | 0.592 |
| plus land-cover roots | 0.568 |
| all layers | 0.645 |

Soil texture is the only layer that clearly helps (0.65 against 0.56 for the base fit), adding all layers does worse than texture alone (it over-fits), and the folds disagree widely (texture ranges from 0.57 to 0.72). The fitted texture coefficients put *more* clay with *lower* cohesion (a_c about -1.5, at its bound) and more sand with higher friction: that is a statistical association with reported landslide places, which sit in particular valleys and road corridors, and it is not a soil-mechanics result. Texture is therefore left **off** by default (`configs/ground_classes.yaml` is still neutral). The fitted values are in `ground_calibration.json` for a user who wants to enable them as a sensitivity run.

Lithology (0.59) and the bedrock-depth cap (0.59) each add about 0.03 over the base fit, with folds that disagree (lithology 0.50 to 0.71), which is within the noise of 600 events. Neither is adopted. The inventory has no records on several lithology groups, so their weights cannot be estimated.


# 30. Check of the Runout Parameters

## 22.1 What data exists

The inventory has almost no volumes (one record) and no runout lengths or deposit areas, so the friction coefficients mu and xi cannot be fitted to Pakistani events. What can be done:

1. **Match published empirical relations.** The Corominas (1996) fits of height drop H against runout length L, H = a L^b, with debris flows 1.109 L^0.857, landslides 2.606 L^0.669, rock avalanches 1.758 L^0.859 and rockfalls 1.999 L^0.803, give an expected travel angle for a given volume class. mu and xi per flow type are tuned so simulated reach angles over synthetic and real slopes fall inside the scatter of these relations.
2. **Earthquake ground motion** can be checked against USGS ShakeMaps of past Pakistani earthquakes (done, Ch. 6.2).
3. **Deposit shape** can be scored (IoU, depth error) only if the owner supplies mapped deposits, for example from field surveys or high-resolution imagery.

## 22.2 Result

Synthetic channelised slopes (V-shaped valley, concave profile, heights 500, 800 and 1200 m, volumes 10^4, 10^5 and 10^6 m3) were released as a slab and run to rest on the GPU. For each, H is the elevation drop from the source to the furthest cell with depth over 0.3 m, L the path length, and the ratio is H(simulated) divided by the Corominas H for that L. A ratio of 1 reproduces the relation; the published scatter is about a factor of 2.

| Flow type, as shipped | mu, xi | Median ratio | Range over the 9 cases |
|---|---|---|---|
| Debris flow | 0.12, 200 | 0.71 | 0.43 to 1.03 |
| Landslide (shallow slide) | 0.30, 300 | 1.56 | 1.03 to 2.22 |

Both medians and all nine cases of each type lie inside a factor of 2.3 of the relation, but the two types sit on opposite sides: the debris flow is somewhat too long for its drop in the wettest sense (ratio below 1) and the shallow slide too short, and the shallow-slide ratio grows with volume (1.0 at 10^4 m3, about 2.1 at 10^6). So **mu and xi were left unchanged**: the synthetic valley is not a Pakistani valley, the Corominas relations are for a world sample with their own factor-of-2 scatter, and tuning two coefficients to one synthetic geometry would give false precision. The result says the solver's runouts are in the right range, not that they are calibrated. Any real calibration needs mapped deposits from the owner.

Rockfall is the same: no recorded Pakistani rock paths exist on the server, so its dissipation was only set against published shadow angles (Ch. 14.9).


# 31. Scoring a Run Against an Observed Extent

Any finished run can be scored against an observed deposit or affected area supplied by the user (GeoJSON or zipped shapefile polygons, or a 0/1 GeoTIFF), for the same event. The model extent is the cells where the flow reached at least a chosen depth (default 0.3 m). On the run's own grid, inside the analysed area:

```
hits = model and observed;  false alarms = model, not observed;  misses = observed, not model
CSI = hits / (hits + false alarms + misses)        POD = hits / (hits + misses)
FAR = false alarms / (hits + false alarms)         F1 = 2 hits / (2 hits + false alarms + misses)        bias = (hits + false alarms)/(hits + misses)
```

A perfect match gives CSI 1 and disjoint extents give 0 (tested). This is the only route to validating runout extent. No mapped Pakistani deposit is on the server, so **no real score exists yet**; one supplied event, with a rainfall record, would allow calibrating the friction parameters against it (Ch. 30).


# 32. Accuracy Record

| Claim | Evidence | Status |
|---|---|---|
| The code solves its equations | 121 unit tests; mass conservation, rest, Voellmy speed, entrainment, GPU equals CPU, fast ensemble equals the reference ensemble | **Verified** |
| Rainfall separates landslide days from ordinary days | AUC 0.73 (0.71 to 0.76) for 24 h intensity, leave-one-year-out | **Validated, modest** |
| Published Guzzetti threshold is usable as a watch | TSS 0.32 on the same data | **Validated, weak** |
| Slopes flagged by the physics are the slopes that fail | Ground calibration, held-out blocks: base physics 0.56, with soil texture 0.65; mean slope 0.59 | **Weak** |
| Calibrated parameters are better than the defaults | Held-out AUC 0.59 to 0.68 (144 events) | **Improved, wide interval** |
| Runout lengths are realistic | Corominas relations on synthetic slopes (Ch. 30) | **Right order of magnitude, within a factor of about 2** |
| Earthquake PGA is realistic | 398 ShakeMaps: scatter 0.40 ln units (Ch. 6.2) | **Agrees with ShakeMap, which is itself a model** |
| Shaking locates earthquake-triggered landslide reports | 31 reports, 7 earthquakes: PGA AUC 0.61, Newmark 0.57, slope 0.63 | **Not shown (n too small, reports cluster at roads)** |
| Observed design storms are right | Gumbel fits recover known parameters; hyetograph depth equals the IDF depth; ERA5-Land smooths bursts | **Verified arithmetic; depths are lower bounds** |
| Mitigation levers and barriers behave sensibly | Directional and mass tests on synthetic cases | **Verified; effect sizes are user inputs, not validated** |
| Dam screening classes and formulas | Formula and synthetic-valley tests; no observed Pakistani dam used | **Verified; not validated** |
| Annual average loss is realistic | Integration verified; assumes loss frequency equals rainfall frequency | **Verified arithmetic; not validated** |
| Rockfall reach and energy are realistic | Synthetic-terrain physics checks pass; first Hunza run has reach angles above literature shadow angles | **Verified code; not validated; probably too dissipative** |
| Access and isolation analysis is right | Synthetic network tests; no observed closures | **Verified logic; not validated** |
| Building damage and loss are realistic | No data | **Not validated, assumed** |
| Flow depth and deposit extent are right | No mapped deposits | **Not validated** |

## 23.1 What the accuracy depends on

The largest controllable limits are data: report locations good to 5 to 50 km, no deposit maps, no soil measurements, no damage records, and rainfall reanalysis that smooths bursts. What would raise accuracy most is, in order, mapped deposits and scars for a handful of Pakistani events (to calibrate friction and the failure depth), field strength and soil-depth measurements in a few catchments, a landslide inventory with surveyed positions and times, and a damage survey after one event. If you can provide any of these, the calibration chapters can use them directly.


# 33. 3D Visualization

Three scenes share SAILAB's viewer stylesheet, controls, timeline, probe and export, but each draws its own hazard. The scene files are built from saved arrays (`frames.npz`, `impacts.json.gz`, `rocks.npz`), so the look can change and every run be re-rendered without re-simulating (`rebuild_scene`).

## Debris flow and landslide

SAILAB's water surface (blue, glossy) is gone. Three things replace it:

1. **A rubble body.** A displaced mesh (three.js, standing on Mapbox's own terrain) follows the flow depth, with a per-pixel material in metres: dark wet mud while moving, pale cracked mud at rest, cobbles and boulders from noise thresholds, gravel grain, a warm sheen on the fast front. The mesh normals come from the displaced surface itself, so the lobes read as relief. A first version extruded stacked depth contours and produced stepped pillars; a second used rounded contours and produced smooth blobs; only the displaced surface with a rubble material read as debris.
2. **A scar layer.** Each cell remembers when it failed. It flashes red-orange at that moment and then stays as pale exposed earth with a ragged darker rim (the failed mask is blurred and thresholded with noise, so the outline is not a blocky grid).
3. **A terrain-change mode.** Net bed change from the solver: blue where soil was lost (scar and scour), brown where it was gained (deposit), lit as relief.

Other changes: the flow-speed mode uses a blue-to-dark-red ramp; contact shadows fall beside the flow; buildings change colour with the depth reached so far (damage curve of Ch. 18); the loop is 24 s instead of 9 so events can be followed; the camera is placed below the deposit looking up the slope toward the source.

## Earthquake

For earthquake runs the scene adds the epicentre (red marker), the rupture trace along the fault (glowing line), expanding wavefront rings, a **Ground shaking** map of PGA, and a brief damped shake of the camera as the wave passes. Failures begin at the quake time with the same flash and scar. **The wavefront speed is not physical:** the real S wave crosses a 5 km area in about a second, far shorter than any animation window, so the rings run at a time-scaled speed for visibility. The shaking map is the Joyner-Boore field of Ch. 6, without site amplification.

## Rockfall

Individual rocks are drawn as faceted instanced meshes coloured by their current energy (dark grey once stopped), with fading trails from their recent positions, dust puffs at fast impacts and a chart of rocks moving and stopped. Release cells are small grey dots; map modes show the reach probability, peak energy and bounce height; clicking the map reports all three. Buildings and roads are coloured by energy class. The camera looks up the slope from where the rocks stop.

## Checking the renders

Scenes were rendered in headless Chromium through the DevTools protocol (`scripts/shot.py`), which waits for the scene to settle and reports JavaScript errors, and judged by eye at several moments of the event. This found real faults: the animation controls were blank because of a script error that only the page's own error hook revealed; rocks were invisible because three.js's lit instanced material did not accept a hand-made colour buffer; the rocks were too small to see at the default zoom. A software GL renderer is used, so real-GPU frame rate is not measured.

## Export

PNG of the current view and an MP4 recorded from the canvas, transcoded on the server (`/export-video`).


# 34. User Interface

The page follows SAILAB's design system (colours, Barlow Condensed headings, Public Sans text, IBM Plex Mono numbers, glass panels), re-tinted amber so the two products are not confused. Layout: header with the hardware line, a 2D Mapbox map with layer buttons (national susceptibility, national physics, risk index, districts, faults, PNG export), a draggable divider, the 3D pane, a draggable column divider, and the right column.

Right-column panels, top to bottom: draw or upload an area; district discovery (ranked by a national metric); river basins; rainfall and triggers (Open-Meteo, antecedent index, ERA5 wettest 72 h, threshold check); live monitoring; six tabs (screening, instant, physics, earthquake, mitigate, rockfall); layers of the current run with the PDF report link, landslide-dam screening, scoring against an observed extent and a batch PDF; GIS export, run history and comparison. Discovery also offers national rainfall hotspots. Barrier lines are drawn with the same drawing tool as the area polygon (the polygon is the area, lines are barriers). Every panel states what it is and is not, and the footer repeats that results are screening grade.

Interface checks (after the mitigation tab and run tools were added): the page and the 3D scene load in headless Chromium without JavaScript errors, and the inline script passes `node --check`. Individual controls have been exercised through the API, not clicked through in a real browser.


# 35. Access Control, Run Management and Operations Additions

- **Token and rate limit.** If `LANDLAB_TOKEN` is set, every write (POST, DELETE) needs it as `Authorization: Bearer`, `X-Token` or `?token=`; reads stay open on the network, as in SAILAB. A per-address limit of 40 POST requests per minute applies (`LANDLAB_RATE`). This is a guard against accidents and casual abuse on a shared network, not real authentication: the token travels in clear text over HTTP. Set it before exposing the port beyond the lab.
- **Run management.** `DELETE /runs/<id>` removes a run; `POST /runs/cleanup` lists (dry run by default) or deletes runs older than N days that are not among the 30 most recent; `GET /api/queue` lists running and queued jobs. One heavy job runs at a time.
- **API tests.** Flask test-client tests cover the page, area validation, design-storm validation, refusal of runs with missing inputs, the token and the rate limit, unknown runs returning 404, and the dry-run default of cleanup. They run no simulations.


# 36. Discovery Tools

Three aids for choosing where to look, all independent of any run:

- **Districts.** The 164 districts ranked by a national metric: area share and population above ML susceptibility 0.7, mean risk index, and the physics share from the national product (which covers all districts; the ML layer covers the north). Any district can become the area.
- **River basins.** The 1,131 HydroSHEDS level-8 basins by region, ranked by area, usable as the area (basins are used only as shapes).
- **Rainfall hotspots.** The highest individually recorded cells, never averaged, for a metric (RX1day, RX5day, R99p, peak hourly, days of at least 20 mm, trend of RX1day) and season, from the ERA5-Land indices cube, each with its district and a Go button. A neighbourhood of 2 cells keeps one hit.

> Values are those of the source dataset. The largest RX1day values (several hundred millimetres in a day in places such as Balochistan) come from ERA5-Land and were not independently checked here; the source's own README documents that ERA5-Land misses localised convective extremes in other places, so the dataset can both overstate and understate at a point.


# 37. Reports, Comparison and Exports

- **PDF report** (`/runs/<id>/report.pdf`): trigger, runout and exposure tables, the loss note and every warning and assumption, rendered with WeasyPrint.
- **Compare two runs** (same polygon and grid): impacted area in A only, B only and both, maximum depth, mean depth change, direct loss. Example: a 70 mm/h storm against an M 7.2 earthquake on the Gilgit test area impacts 3.9 and 12.4 km2, with 3.0 and 11.1 billion PKR direct loss.
- **Run manifest**: model and version, sources, grid, parameters, rainfall provenance, warnings, calibration and validation status.
- **Summary JSON**, **map layers** (maximum depth and speed, deposit, scour, failure time, minimum FS, PGA, slope) as georeferenced PNG overlays, **MP4 and PNG** from the 3D scene.
- **Batch PDF** (`/batch-report.pdf?ids=...`): a table of selected runs with rain, failing area, released volume, impacted area, depth, buildings at DS3 or above and direct loss.
- **Mitigation comparison**: unmitigated against mitigated run, with the change in failing area, impacted area, loss, blocked road length and buildings at DS3 or above (Ch. 23, 24).


# 38. Chronicle of Findings and Bugs

Each entry was found by checking a result against something known, not by inspection of the code.

| # | Finding | How it was caught | Fix |
|---|---|---|---|
| 1 | Population was counted about 9 times at 30 m | Gilgit showed 570,000 people in 120 km2 | Resample per-cell counts by averaging and scale by cell area |
| 2 | A whole-country run at 820 m cells found 0.07% unstable | Result implausibly low | Physics is skipped above 150 m cells with an explicit message; the national product is built tile by tile at 90 m instead |
| 3 | Bare rock and perennially unstable cells appeared as storm failures (48% of an area unstable at zero rain) | The Tier 2 library showed failure at 0 mm | Mobilisation rule: soil-bearing (at most 45 degrees) and stable before the event (Ch. 4.5); the national product was rebuilt with it |
| 4 | Time step 0.5 s gave a steady speed 12% low | Compared with the Voellmy analytic speed | Time step capped at 0.2 s |
| 5 | numba with 20 threads was 80 times slower than 1 thread on a small grid | Profiling a 24 s run that should have taken 2 s | Thread count chosen from grid size |
| 6 | GPU solver slower than the CPU | Timing | CUDA graphs, then `torch.compile` fusion for large grids (Ch. 8.2) |
| 7 | Out-of-memory when creating a CUDA context on the shared GPU | A second process failed in the tests | Fall back to CPU on any GPU failure; release cached memory after jobs; tests skip rather than fail |
| 8 | An in-memory result cache lacked the grid transform, so overlays returned errors after a restart | Overlay request failed | Results are always reloaded from the saved run |
| 9 | Year-only dates (such as "2010") parsed as 1 January | Date histogram showed 1929 to 2026 | Only full dates are day-resolved; precision is tracked; undated duplicates need the same stated year |
| 10 | The fast ensemble indexed some sampled parameters wrongly (harmless only because those parameters were constant) | Code review while adding the GPU path | Every sampled parameter is indexed per member; a test compares against the reference ensemble |
| 11 | Slab front slumped, failing a "rest" test | Test failed | The check now covers the interior, where friction holds; the front slumping is correct physics |
| 12 | A boundary polygon of 985,000 km2 exceeded the area cap | Whole-country request rejected | Cap set to 1.2 million km2 (the border file includes disputed territory) |
| 13 | `pgrep -f` and `pkill -f` with a plain pattern killed the tool's own shell | Shell exited with code 144 | Anchored patterns |
| 14 | Chart of an animation window began at "0:00" although it started hours into the storm | Reading a screenshot | Legend states the window start; calendar time is shown when a start date exists |
| 15 | The earthquake run's numbers had been quoted for a storm run in a draft of this document | Checking the figures against the stored comparison | Corrected in Ch. 12.4 |
| 16 | A "6 m barrier" on a steep slope let 90% of a flow through | The new barrier test | A wall's height is measured above the ground upslope: the wall cell is raised by height plus the ground drop across a cell (Ch. 24) |
| 17 | IMERG sub-hourly values were intensities, not depths, so a 1 h design storm summed to 9.1 mm instead of 8.0 mm | Mass check of the hyetograph against the IDF depth | Convert intensity to depth by multiplying by duration before taking the shape (Ch. 16) |
| 18 | `np.interp` rejected an array `left` argument in the sub-hourly branch | First hyetograph call | Handle the shortest-window extrapolation explicitly |
| 19 | The reference storm (360 mm) is five times the observed 100-year 24 h depth at Gilgit | Compared with the new IDF table | Described as a stress test; use the observed design storms for realistic runs |
| 20 | The first debris viewer drew stacked depth contours: stepped pillars, then smooth blobs | Rendering and looking at it | Replaced by a displaced surface mesh with a rubble material (Ch. 33) |
| 21 | The new viewer's controls were blank | A render showed an empty timeline; no console message | An in-page error hook exposed a `const` used before its definition; the block was moved earlier |
| 22 | Rocks were invisible | Render showed only release markers | The lit instanced material rejected a hand-made colour buffer; colours are now set through three.js and rocks are drawn larger |
| 23 | A rockfall fence counted nothing as stopped | The barrier test | Stops at a fence were not added to the stop map |
| 24 | The deposit rebuild failed when the geometry helper arrays were cropped twice | Rebuilding a scene from saved frames | `viewer.build` takes already-cropped arrays; the crop only locates them |
| 25 | A patch list for the viewer applied in the wrong order and failed loudly (three times) | The build raised "patch target missing" | Patches that touch the same text were merged; the failing check is kept on purpose so a changed SAILAB viewer cannot silently break the scene |
| 26 | My own document builder deleted the new visualisation chapter | Two chapter files shared a slug | Rewritten; chapter slugs must be unique |
| 27 | With land-cover root cohesion the Gilgit failing area rose from 1.2 to 4.4 km2 | Comparing runs | Reported as a sensitivity, not hidden (Ch. 20) |


# 39. Considered and Declined

- **Coupling with flood modelling.** Declined by the owner: LANDLAB and SAILAB stay separate products. Debris flows are not run through a water solver.
- **Using the national ML susceptibility as a predictor in the validation models.** It was trained on the inventory; using it would leak the answer. It is shown as a labelled optimistic reference only.
- **Bilinear resampling of population.** Counts are not intensities; see Ch. 38 (#1).
- **Promoting year-only dates to a day.** Invents precision that would corrupt the rainfall validation.
- **A Pakistan-specific I-D threshold.** Fitted, but no better out of sample than the published Guzzetti curve (Ch. 26.4), so not adopted.
- **Absolute landslide probabilities.** Not identifiable from a report inventory.
- **A temperature guard on GPU jobs.** Dropped by the owner's decision (Ch. 2.3).
- **Interactive whole-country physics.** Meaningless at the needed cell size (Ch. 4.1); replaced by the tiled national product.
- **External multiphase runout engines (r.avaflow and similar).** Not available on the server; the in-house solver is verified but uncalibrated, and this is stated wherever it is used.
- **Raising the inventory with downloaded catalogues.** No further catalogue was found on the server, and none was downloaded without the owner's say-so.
- **Routing a landslide-dam breach flood downstream.** That is flood modelling; the dam screening stops at formation, stability, lake volume and a breach peak (Ch. 22).
- **An areal reduction factor on design storms.** The constants are not available from a source on the server; point rainfall is used and is conservative for the areas run.
- **A surrogate model for barrier placement.** Not trusted at this sample size; every candidate is a real simulation under a hard budget.
- **Default wall costs.** No cost data exist here; the optimiser takes the cost from the user and says what happens at zero.
- **Filling in geology strength values from intuition.** The 16 geology units are colour classes with guessed lithology; invented values would look like data. Multipliers stay 1.0 until calibration.
- **Rockfall damage and loss.** No fragility for rock impact is available; only energy classes are reported.
- **Real-time seismic wave speed in the animation.** Physically correct and invisible; the rings are time-scaled and say so.


# 40. Known Limitations

1. **Not calibrated, mostly not validated.** See Ch. 32 for exactly what has and has not been checked.
2. **One soil layer, infinite slope.** No deep-seated slides, no rock-slope kinematics, no rockfall, no snow avalanche, no glacial-lake outbursts.
3. **Rain is spatially uniform** over the area and comes from a point (ERA5, CHIRPS, forecast) or a design storm.
4. **Pore pressure is a proxy** from a wetting front, not groundwater flow.
5. **Failure depth equals soil depth**, thinned with slope by an assumption; real slip surfaces are not mapped.
6. **Earthquake ground motion** has no site amplification, no directivity, a single empirical model valid for M 5.0 to 7.7.
7. **Runout friction is a scenario value by flow type;** the single-phase depth-averaged model does not separate solid and fluid phases.
8. **Impacts** use assumed fragility medians and a single unit cost; no indirect loss, no lives.
9. **Building heights** are assumed 6 m (display only); footprints come from a satellite-derived dataset with its own errors.
10. **ML susceptibility** covers the north only.
11. **Terrain** is SRTM at 29 m: gullies, small scarps and road cuts are not resolved.
12. **Spatial misregistration** of the 3D canvas (lon/lat rectangle over a UTM grid) is small for tens of kilometres and grows with area.
13. **Design storms** are point depths from 46 years of ERA5-Land annual maxima: 100- and 200-year values are extrapolations, short durations are lower bounds, and storms are limited to 24 h.
14. **Mitigation effects** (root cohesion, regrading, drainage, barrier height) are the user's scenario inputs; regrading changes stability only, not the terrain the flow crosses; barriers are not drawn in the 3D scene.
15. **Average annual loss** assumes a T-year storm gives the T-year loss.
16. **Dam screening** uses a drainage area truncated at the analysed edge and an embankment breach formula for the peak; there is no downstream routing.
17. **Rockfall** uses scenario restitution, friction and roughness; the first run gave reach angles steeper than literature shadow angles, so it is probably too dissipative; energy is translational only; no damage or loss is estimated.
18. **Geology** strength multipliers are neutral (1.0) because the geology raster's lithology is only guessed from colours.
19. **Earthquake animation** wavefronts are time-scaled; the shaking field has no site amplification.
20. **Access analysis** sees only roads inside the area and ignores speeds.


# 41. Operations and Testing

## 30.1 Running

```
~/flood/venv/bin/python landslide_app.py                    # http://<host>:5070 (Flask, token in .env)
nice ~/flood/venv/bin/python scripts/build_national.py      # national 90 m product, GPU first, resumable
~/flood/venv/bin/python scripts/build_districts.py          # after the national build prints DONE
~/flood/venv/bin/python scripts/build_landlab_techref.py    # rebuilds this document from docs/landlab and docs/validation
```

Compute-heavy validation and calibration scripts are run only on request: `validate_rain_threshold.py` (done), `validate_spatial.py` (written), later `calibrate_physics.py` and the runout and PGA checks. `scripts/calibrate_physics.py`, `check_runout_relations.py` and `validate_pga.py` are written and not run. Also compute heavy and run only on request: the CMIP6 climate multiplier, average annual loss, automatic barrier placement and mitigated-versus-unmitigated pairs (each is one or more full simulations).

## 30.2 Tests

`cd backend && PYTHONPATH=. ~/flood/venv/bin/python -m unittest discover -s tests -t .` runs 121 tests: the original physics and integrity tests, the app layer (fast ensemble equals the reference, GPU equals CPU, mobilisation rule), and the engine (mass, rest, speed, entrainment, GPU equals CPU, Joyner-Boore, Wells-Coppersmith, mobilisation). GPU tests skip if the shared GPU cannot be initialised.

## 30.3 Files

| Path | Content |
|---|---|
| `runs/<id>/` | one run: summary, manifest, arrays, frames, 3D scene |
| `datasets/national/` | national product, district statistics, build log |
| `datasets/derived/` | 30 m slope raster for validation |
| `datasets/state/` | monitoring watches, run history |
| `docs/validation/` | JSON results and sample tables that this document reads |

## 30.4 Safety

One heavy job at a time; the GPU is shared, so it is released after every job; any GPU failure falls back to the CPU; all data paths are read-only; the application never writes into SAILAB or the shared data folders.


# 42. References

- Azarafza, M. et al. (2021). Deep learning-based landslide susceptibility mapping. *Scientific Reports* 11, 24112 (the national ML method).
- Bates, P. D., Horritt, M. S., Fewtrell, T. J. (2010). A simple inertial formulation of the shallow water equations. *Journal of Hydrology* 387, 33-45.
- Caine, N. (1980). The rainfall intensity-duration control of shallow landslides and debris flows. *Geografiska Annaler A* 62, 23-27.
- Corominas, J. (1996). The angle of reach as a mobility index for small and large landslides. *Canadian Geotechnical Journal* 33, 260-271.
- Funk, C. et al. (2015). The climate hazards infrared precipitation with stations (CHIRPS). *Scientific Data* 2, 150066.
- Green, W. H., Ampt, G. A. (1911). Studies on soil physics. *Journal of Agricultural Science* 4, 1-24.
- Guzzetti, F., Peruccacci, S., Rossi, M., Stark, C. P. (2008). The rainfall intensity-duration control of shallow landslides and debris flows: an update. *Landslides* 5, 3-17.
- Dorren, L. K. A. (2003). A review of rockfall mechanics and modelling approaches. *Progress in Physical Geography* 27, 69-87.
- Volkwein, A. et al. (2011). Rockfall characterisation and structural protection: a review. *Natural Hazards and Earth System Sciences* 11, 2617-2651.
- Ermini, L., Casagli, N. (2003). Prediction of the behaviour of landslide dams using a geomorphological dimensionless index. *Earth Surface Processes and Landforms* 28, 31-47.
- Froehlich, D. C. (1995). Peak outflow from breached embankment dam. *Journal of Water Resources Planning and Management* 121, 90-97.
- Hosking, J. R. M. (1990). L-moments: analysis and estimation of distributions using linear combinations of order statistics. *Journal of the Royal Statistical Society B* 52, 105-124.
- Thrasher, B. et al. (2022). NASA Global Daily Downscaled Projections, CMIP6. *Scientific Data* 9, 262.
- Huffman, G. J. et al. (2023). GPM IMERG Final Precipitation L3 Half Hourly 0.1 degree V07.
- Horn, B. K. P. (1981). Hill shading and the reflectance map. *Proceedings of the IEEE* 69, 14-47.
- Jibson, R. W. (2007). Regression models for estimating coseismic landslide displacement. *Engineering Geology* 91, 209-218.
- Joyner, W. B., Boore, D. M. (1981). Peak horizontal acceleration and velocity from strong-motion records including records from the 1979 Imperial Valley, California, earthquake. *Bulletin of the Seismological Society of America* 71, 2011-2038.
- Muñoz-Sabater, J. et al. (2021). ERA5-Land: a state-of-the-art global reanalysis dataset for land applications. *Earth System Science Data* 13, 4349-4383.
- Sirko, W. et al. (2021). Continental-scale building detection from high resolution satellite imagery (Open Buildings). arXiv:2107.12283.
- Voellmy, A. (1955). Ueber die Zerstoerungskraft von Lawinen. *Schweizerische Bauzeitung* 73, 159-165, 212-217, 246-249, 280-285.
- Wells, D. L., Coppersmith, K. J. (1994). New empirical relationships among magnitude, rupture length, rupture width, rupture area, and surface displacement. *Bulletin of the Seismological Society of America* 84, 974-1002.

> Coefficients quoted from memory of these papers (Joyner-Boore, Wells-Coppersmith, Jibson, Caine, Guzzetti) should be re-checked against the originals before any operational use; this document marks them as screening-grade for that reason.
