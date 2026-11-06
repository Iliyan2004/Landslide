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
| Tiers 1 to 4, national product, districts, basins | Implemented and tested (131 unit tests) |
| Rainfall sources: design storm, forecast, recent, ERA5, CHIRPS, CSV | Implemented |
| Impacts: buildings, roads, hospitals and schools, direct loss | Implemented (all thresholds assumed, Ch. 17) |
| Live monitoring with webhook, compare runs, PDF report, MP4 export | Implemented |
| Rainfall-threshold validation against the inventory | **Done** (Ch. 25) |
| Spatial validation, physics and ground calibration, runout check, ShakeMap comparison, quake-landslide check | **Run** (Ch. 26 to 29, 6.2, 31) |
| Design storms from observed IDF, climate multiplier, average annual loss | Implemented and **run once on a 57 km2 Gilgit area** (Ch. 20); the climate signal is within model spread, and the loss is an order of magnitude |
| Nature-based levers, barriers, ranking, automatic barrier placement | Implemented and **run once on the same area** (Ch. 22, 23); this exposed a counting artefact for planting and a placement bug, both fixed |
| Landslide-dam screening, rainfall hotspots, scoring against an observed extent | Implemented (dam screening and hotspots run on real data; observed scoring needs a supplied extent) |
| Autonomous monitoring agents: feed fallback, job recovery, health, forecast audit and bias correction | Implemented, rule-based (Ch. 35); forecast back-test run |
| Debris and earthquake visualisation | Rebuilt and checked by rendering (Ch. 32) |
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

After cleaning, the inventory has 381 unique events. Positions are reports: the stated accuracy ranges from 0.5 km to 50 km, and for many records it is 25 km or worse. Dates are kept at the precision they were given: a bare year is never turned into 1 January. There are no deposit polygons, no measured volumes (one record), no soil measurements and no depth of failure. This caps what any validation can show (Ch. 24).

## 3.2 Known coverage gaps

- The ML susceptibility layer ends near 31 N; elsewhere it is NODATA and is never read as "low".
- The 05_risk population layer follows the same extent.
- ERA5-Land ends on 20 May 2026.


## 3.4 Borehole, soil and groundwater data added later (`Datadownload/`)

Five collections were supplied to find slip-surface depth, regolith and soil strength. `scripts/check_new_data.py` (`docs/validation/new_data_checks.json`) tested what each can do:

| Collection | Content | Where | Use for landslides |
|---|---|---|---|
| CSIRO Indus borelog database | 1,497 lithological logs, median depth 177 m | Indus plain only: latitude 24.2 to 32.9, 0 holes north of 33 degrees | None: alluvium, no slopes. It does show that the SoilGrids depth-to-bedrock map is wrong on the plain: 92% of the holes are deeper than the bedrock the map gives (median hole 177 m against a mapped 55 m), because the holes rarely reach rock. The map is used only as a cap on slope soil depth (off by default), where the plain is irrelevant. |
| BGS groundwater levels | 58,600 readings from 4,027 stations, 1884 to 2020 | Punjab and Sindh plains; 2 stations north of 33 degrees | Depth to the water table on the plain: median 3.9 m, 10th to 90th percentile 1.4 to 12.3 m since 1990, and 67% of readings between 2 and 10 m, the water-table prior range of the model. That supports the order of magnitude of the prior, for flat ground. Every reading is the 1 October value, so the seasonal rise (and therefore the antecedent water-table response) cannot be measured. |
| WoSIS soil profiles | 80 profiles, 48 north of 31.5 degrees | Sparse, mostly 1984 US survey and old FAO/ISRIC profiles | Measured clay and sand agree with the SoilGrids values the ground model reads: clay bias 2.0 percentage points, mean error 4.5; sand bias -1.3, mean error 3.3 (69 profiles). **This is not an independent test**: SoilGrids is trained on WoSIS. No shear strength, cohesion or friction is in the collection. |
| WoSIS profile depths | described depth of the northern profiles | 48 profiles | They are described to the sampling depth (median 190 cm), not to bedrock. Five reach a rock or Cr contact, at 127 to 175 cm: weak support for a soil depth of 1.3 to 1.8 m on the Potwar and Hazara foothills, against the fitted 2.4 m. |
| USGS Indus borehole logs, depth-to-bedrock raster | 16 deep holes in the eastern Indus plain; the raster is the same SoilGrids 250 m map already used | Plain / already held | Nothing new. |

**Is it enough?** No, for the purpose it was gathered for. The collections are almost entirely on the flat Indus plain, where landslides do not happen. There is no borehole, geophysical profile, shear-strength test or regolith thickness on a slope in the mountains, which is what a mapped slip surface, a two-layer soil or a calibrated cohesion would need. What it does is confirm three assumptions on the plain or at sparse points (water-table depth range, SoilGrids texture, and a 1 to 2 m soil depth in the foothills) and show one input to distrust (the SoilGrids bedrock depth on the plain). No parameter of the model was changed by it. To close the gap the model needs boreholes or geophysical (seismic refraction, resistivity) lines on slopes in the Hindu Kush, Karakoram and Himalaya foothills, ideally with shear tests.


## 3.5 Census (Pakistan Bureau of Statistics, 2023)

`Datadownload`-era folder `PBS DATA district` holds district tables of population, density, household size and housing type (permanent, semi-permanent, mud or temporary). The population and housing-type tables and the district boundaries are copied to `datasets/external/pbs/` and used for construction-class fragility, household size and the population fallback (Ch. 17). Coverage: 142 districts; **Gilgit-Baltistan and Azad Kashmir are absent**, so the highest-landslide districts fall back to national means.

**Population raster against the census.** For the 37 census districts that lie wholly inside the raster's footprint, the median ratio of the WorldPop 2025 total to the 2023 census total is 1.05 (25th to 75th percentile 1.02 to 1.14), about the two years of growth, and 76% of the districts are within 20%. The outliers are census-row or boundary problems rather than raster errors: the census table gives Mirpur 15,610 people, Muzaffarabad 174,708 and Peshawar 2.19 million (district totals in the raster are 548,000, 787,000 and 5.2 million), which are tehsil-sized or pre-reorganisation figures. The raster total over the checked districts is 1.17 times the census total, driven by those rows.

**Building heights.** No usable source was found. Google's Open Buildings 2.5D height layer is on Earth Engine, whose project on this server denies access (a missing service-usage role); Overture Maps has a height for only 30 of 24,216 Gilgit buildings and a floor count for 29. Heights stay at the assumed 6 m (two storeys), and the loss chapter says so (Ch. 18).


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

A rain or earthquake event can only mobilise a cell that (a) carries soil, meaning slope at most 45 degrees (steeper ground is treated as bare rock and is not modelled), and (b) was **stable before the event**, meaning FS at least 1 at the baseline water table. Cells that fail the second test would already have failed under ordinary conditions. Without this rule the model labels bare rock and perennially unstable cells as storm failures: with the weakest strength preset, 48% of the Gilgit test area was "unstable" with zero rain. The run reports the counts it excluded (`trigger.mobilisable`).


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

The 30 days come from ERA5-Land (server zarr) for the same point, whichever source drives the storm (ERA5, IMERG or CHIRPS). Design storms and forecasts carry no antecedent unless the user supplies one. The constants are scenario values (`engine/antecedent.py`); `scripts/calibrate_physics.py` fits them against the event inventory with matched control days, and the fit is reported in Ch. 27 (a calibrated set is adopted only if it beats the defaults on held-out data). The main run and the mitigation evaluation build their scenario in one function (`run._scenario`) so that a paired run with a barrier or a planting always starts from the same soil as the unmitigated run.

## 5.6 Parameter-uncertainty ensemble

The single scenario moves every parameter together to one end of its prior range (the strength quantile). Setting `ensemble: n` in a run additionally draws n members by Latin hypercube with EVERY prior varied independently (cohesion, friction, depth, conductivity, water table, root cohesion), applies the same spatial-ground and antecedent adjustments to each member, and evaluates failure with the exact end-of-storm shortcut of Ch. 5.4. The outputs are a failure-probability raster (share of members in which the cell is mobilisable and fails) and the 5th, 50th and 95th percentile of the failing area. The probability is conditional on the priors and on independence between them (cohesion and friction are in fact negatively correlated in real soils); it is not a frequency of landslides. It runs on the GPU first.

## 5.7 Optional physics added for the limits, and what the data says about it

Three additions address limits that earlier versions listed. All are **off by default** and are run parameters:

| Limit | Addition | Parameter | What it does |
|---|---|---|---|
| Uniform rain over the area | Gridded rain | `rain_field: true` | Multiplies each cell's storm depth by the ERA5-Land storm total of the cell under it, divided by the total at the cell the series was read from (scaling limited to 0.3 to 3). The Green-Ampt front is not linear in rain, so it is run for five representative scale values and each cell takes the nearest. Only for ERA5, IMERG and CHIRPS series that carry a start time. |
| No lateral flow or perched water | Topographic water table | `wetness_beta` | The depth to the starting water table varies with the topographic wetness index, `water_table x exp(-beta x (TWI - mean)/sd)` (`engine/wetness.py`): hollows and valley floors start wetter than spurs. Upslope area is counted only inside the analysis area. |
| No unsaturated suction strength | Suction cohesion | `suction_kpa` | Adds `suction x (1 - m)` of apparent cohesion, lost as the layer saturates (`trigger.suction_cohesion`). |

The depth limit is handled by the bedrock-depth cap (Ch. 28); the slip surface is still the soil depth, because a mapped slip surface needs boreholes or geophysics, and none exist for Pakistan in any source I could reach (public repositories hold none; the global soil-thickness map of Pelletier et al. needs an Earthdata login).

**Test.** The temporal calibration (Ch. 27) was re-run with the wetness exponent (0 to 2) and the suction (0 to 10 kPa) as two more fitted parameters, the wetness index taken from the national 90 m layer sampled in each report's accuracy disc. Held-out AUC: 0.685 with them, against 0.683 without. That is no gain. The fitted values also differ wildly between folds (wetness exponent 0.2 to 1.7, suction 1.5 to 10 kPa), so the data cannot identify them. **They stay at zero by default.** They are available for sensitivity runs, not as calibrated physics.

Rain is not scale-tested against the inventory: a report's accuracy disc and the 9 km ERA5 cell are the same scale, so the gridded rain cannot show a difference on this data. It matters only for areas several ERA5 cells wide.

## 5.8 Limits

Uniform rain over the area unless the gridded option is on; lateral flow only through the optional topographic water table; suction strength only as an uncalibrated option; one soil layer; depth of failure is the soil depth, not a mapped slip surface; no rock slopes (Ch. 40).


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

The friction parameters are **scenario values by flow type, not calibrated to any event** (calibration is planned, Ch. 29):

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

These show the code solves its equations. They do not show it predicts real runout; see Ch. 29.


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

A fifth tab, **Mitigate**, holds nature-based levers, barriers (drawn on the map, optionally auto-placed) and average annual loss (Ch. 22, 23, 20). The right-hand column also holds area discovery (district ranking by national metrics, basins), a rainfall context panel, live monitoring, layer pickers for the finished run, run history, comparison and the PDF report.


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

Failing area and soil depth; released, entrained and final volume with a mass check; impacted area, maximum depth, maximum speed and runout from the source; counts of failed cells against time; maximum depth, speed, deposit, scar, failure-time, minimum-FS and slope rasters; impacts (Ch. 17 and 17); the 3D scene.

## 12.4 Reference run (a stress test, not a design storm)

Gilgit test area (about 20 km2, 22,000 cells at 30 m), triangular storm of 60 mm/h peak for 12 h (360 mm), colluvium preset, strength quantile 0.3, debris flow, entrainment on: 1,329 failing cells (1.20 km2), 0.96 million m3 released plus 65,000 m3 entrained, 3.6 km2 impacted, maximum depth 7.1 m, maximum speed 11.9 m/s, runout 1.3 km, 24 s end to end on the GPU. A 70 mm/h peak storm on the same area impacts 3.9 km2 (maximum depth 7.3 m), only slightly more than the 60 mm/h run, whereas an M 7.2 earthquake with a 2 cm Newmark criterion on the same area impacts 12.4 km2 with depths up to 19.7 m. Outcomes are very sensitive to the trigger and to the strength scenario (Ch. 4.3).


# 13. Tier 4: Earthquake Scenario

The tab takes a magnitude, a focal depth, an epicentre (clicked on the map or the area centre), the time after the start of the animation, the Newmark criterion, an option to snap to the nearest mapped fault, and an optional preceding rainfall series. It previews the rupture length and mean PGA at 0 to 150 km, then runs the same pipeline as Tier 3 with the failures set by Newmark displacement (Ch. 6). Outputs add the PGA raster. Faults can be drawn on the map.

The shaking now carries a site term (Vs30 from the USGS global grid) and a separate intermediate-depth model for the Hindu Kush and Pamir earthquakes (a focal depth over 40 km switches to it). Both were compared with 398 USGS ShakeMaps (Ch. 6.2): the scatter against ShakeMap is 0.40 ln units over all events. There is still no calibration to a recorded landslide inventory of a specific earthquake, so the result is a scenario of pattern and order of magnitude, not a forecast for a specific earthquake.


# 14. Rainfall Sources

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

> ERA5-Land is a model reanalysis on a 0.1 degree grid: it smooths convective cloudbursts, which dominate Pakistani landslide triggers. Hindcasts with ERA5 therefore understate peak intensities at a point. This affects the validation in Ch. 25 equally for events and controls, but it lowers the achievable skill.


# 15. Design Storms and Climate Scaling

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


# 16. Intensity-Duration Thresholds and Live Monitoring

## 15.1 Global thresholds

For the watch tier the platform uses published global curves, not a Pakistan-specific fit (Ch. 25 shows a fit does no better on the available data):

```
Caine (1980):             I = 14.82 D^-0.39    (mm/h, D in hours, 0.167 to 500 h)
Guzzetti et al. (2008):   I = 2.20  D^-0.44    (mm/h, D in hours, 0.1 to 1000 h)
```

For a rain series the maximum mean intensity over 1, 3, 6, 12, 24, 48 and 72 h is compared with the curve; exceedance at any duration is reported. The status is always `experimental_unvalidated`, and the page says a threshold exceedance is a watch, never a prediction. An antecedent precipitation index (k = 0.98 per hour on the last three days) is shown beside it.

## 15.2 Live monitoring

A watch stores an area, a forecast-intensity threshold (default 10 mm/h), a check interval and an optional webhook. A scheduler thread wakes every 60 s and checks the watches that are due: it fetches the Open-Meteo forecast for the area centre, and when the forecast peak crosses the threshold (and the previous check had not) it starts a Tier 3 run on that forecast and posts to the webhook. Watches are stored in `datasets/state/watches.json`.

> Monitoring uses a point forecast and uniform rain, and the Tier 3 physics is screening grade; an automatic run is an early look, not a warning.


# 17. Exposure and Damage

## 16.1 Exposure layers

| Layer | Source | Rule |
|---|---|---|
| Buildings | Google Open Buildings, local parquet tiles via DuckDB | Footprints whose centroid is inside the area; each takes the 3 x 3 cell maximum of flow depth and speed at its centroid; assumed height 6 m (3D only) |
| Roads | HOTOSM roads | A segment is blocked if flow depth at a vertex or at the segment midpoint is at least 0.5 m; blocked length is summed |
| Hospitals, schools | government shapefiles | Impacted if depth at the point is at least 0.3 m |
| Population | WorldPop 2025 via 05_risk | People per 90 m cell, rescaled by cell area; people in cells reached at 0.3 m or more. Where the raster has no data (south of about 31 N) the 2023 census district density is used, uniform within each district, and the result says so (a district total, not a map of settlements). |
| People in damaged buildings | damaged buildings (DS 2 or worse) x district average household size from the 2023 census | assumes one household per footprint; the national mean household size where the district has no census row |

## 16.2 Building damage

Dynamic pressure from the flow, a lognormal fragility for four damage states, and a floor from burial depth:

```
p (kPa) = rho v^2 / 1000,   rho = 1800 kg/m3
P(DS >= k) = Phi( ln(p / median_k) / 0.6 ),   medians 5, 15, 40, 100 kPa for DS1 to DS4
burial floor: depth >= 0.3 / 1 / 2 / 4 m  ->  at least DS1 / DS2 / DS3 / DS4
damage ratio by state: 0, 0.05, 0.20, 0.55, 1.00
```

**Construction class from the census.** Each building is assigned to the district polygon that contains its centroid, and the three fragility curves below are averaged with that district's household shares of pakka (permanent), semi-pakka and kacha (mud or temporary) construction from the 2023 census (`engine/census.py`; `datasets/external/pbs/`). The pressure medians of the pakka curve are multiplied by 1.0, 0.6 and 0.3 for pakka, semi-pakka and kacha (assumed multipliers: there is no Pakistani damage data to fit them). The household shares are district-wide, so a mud hamlet in a pakka-dominated district is still scored with the district mix. The census tables have **no row for Gilgit-Baltistan or Azad Kashmir** (23 of the 164 district polygons, the highest-landslide areas); there the national mix (about 67% pakka, 13% semi-pakka, 20% kacha) is used and the result's census note says so.

For a flow of 1.5 m depth at 5 m/s the expected damage ratio is 0.44 for an all-pakka building and 0.77 for a district that is 70% kacha: the mix matters more than any other single exposure input.

The expected damage ratio is the probability-weighted ratio. Buildings in cells that never reach 0.3 m are DS0. **Every threshold above is an assumption inherited from the earlier prototype; none is calibrated to observed damage in Pakistan.**

## 16.3 3D colouring

The 3D viewer colours buildings by the expected damage from the depth reached so far (a curve of 0, 0.05, 0.20, 0.55 and 1.00 at 0, 0.3, 1, 2 and 4 m), so a building changes colour as the flow arrives. Roads turn when blocked.


# 18. Estimated Direct Loss

Loss is valued the way SAILAB values flood loss (`loss_utils.py` there, `engine/loss.py` here), so a landslide loss and a flood loss are on the same footing and the same average-annual-loss method (Ch. 20) applies to both.

## 19.1 Valuation

```
structure loss = damage ratio x footprint area x storeys x maximum damage value
  storeys               = max(1, building height / 3 m)
  maximum damage value  = 111 EUR/m2 x 322.5 PKR/EUR = 35,798 PKR/m2      (Huizinga et al. 2017, JRC EUR 28552, Table 3-21, Asia residential, 2010 prices)
content loss    = 50% of structure loss                                   (FEMA HAZUS residential content ratio)
agricultural    = cropland cell area x damage fraction x 0.03 EUR/m2 x 322.5   (JRC Asia agriculture)
direct loss     = structure + content + agriculture
```

What differs from the flood method, and why:

- The **damage ratio** is the landslide's own, not a flood depth-damage curve. A flood curve describes slow inundation; debris destroys by dynamic pressure and burial. Each building takes the maximum flow depth and speed of the surrounding cells, the dynamic pressure `rho v2 / 2` (rho = 1,800 kg/m3) is mapped to damage states with lognormal fragility medians of 5, 15, 40 and 100 kPa (dispersion 0.6), a burial depth sets a minimum state (0.3, 1, 2 and 4 m), and the expected ratio uses 0, 0.05, 0.20, 0.55 and 1.0 for the five states. **All of these are assumed; none is calibrated** to a Pakistani event.
- The **damage fraction on cropland** is `min(1, debris depth / 0.5 m)`: half a metre of burial is taken as a total loss of the crop. JRC's agriculture value (0.03 EUR/m2, about 10 PKR/m2) is tiny against buildings, so crops rarely matter in the total.
- **Building height** is not in the footprint dataset; 6 m (two storeys) is assumed for every building, which, with the 50% contents, makes the same damage cost about 3 times what the earlier flat valuation (35,000 PKR/m2, one floor, no contents) gave. Loss figures from before this change are not comparable with the ones here.

## 19.2 Limits

The unit value is a regional (Asia) average: Pakistan has no figure of its own in the source table. The exchange rate is a current-date conversion applied to a 2010-price figure, not inflation-adjusted. Footprint area times two storeys overstates single-storey kacha houses and understates multi-storey urban blocks, which is why housing type from the census (now used for the damage ratio, Ch. 17) matters; the valuation itself is still one value per square metre for every class. Indirect losses (road closure days, business interruption, lives) are **not** estimated. The result is an order-of-magnitude figure for comparing scenarios, not an insured value.


# 19. Access and Isolation Impacts, and GIS Export

## Access

A blocked road is a poor measure of consequence on its own. After a debris-flow run the platform builds a network from the HOTOSM roads in the area (vertices snapped to a 5 m grid), removes segments blocked at 0.5 m depth, and asks which buildings and facilities lose road access.

- A point is **cut off** when its nearest road node is in the largest connected component before the event but not after. Components that were already disconnected are not blamed on the event (a test checks this).
- Points farther than 400 m from any road are not assessed.
- For hospitals and schools, the shortest path to a central node of the network is compared before and after, giving the extra distance or a cut-off flag.

Gilgit reference (3.6 km2 flow, 14,458 points): 39% of buildings were cut off; the largest road component fell from 88% to 46% of nodes; of the 58 hospitals and schools assessed, several were cut off and a few faced detours of 70 to 230 m. Limits: the network ends at the area boundary, so connection through the outside world is unseen; distance only, no speeds or capacity; missing OpenStreetMap roads make isolation overestimated.

## Spatially varying ground

By default one strength set applies to the whole area. With **spatially varying ground** (off by default) the platform reads land cover and geology rasters. Root cohesion comes from land cover (trees 6 kPa, crops 1.5, rangeland 0.5, flooded vegetation 2, bare, built, snow and water 0; mid-range assumptions) and replaces the scenario root cohesion where the land cover is known. **Geology multipliers on cohesion and friction are all 1.0:** the national geology raster has 16 colour-coded units whose lithology is only guessed from map colours, so strength values for them would be invented. The mechanism exists so calibration can fit multipliers on held-out data (Ch. 27). In the Gilgit reference storm, switching it on raised the failing area from 1.2 to 4.4 km2, because land-cover root cohesion is mostly zero on the steep slopes (the default scenario assumed 0 to 5 kPa everywhere). Land cover is a strong lever, and it is an assumption.

## GIS export

`/runs/<id>/export.zip` gives: GeoTIFF rasters in the analysis CRS (DEM, slope, maximum depth and speed, deposit, scour, failure time, minimum FS, PGA as available); GeoJSON polygons of the failure zones and the debris; GeoJSON and CSV of buildings with damage state, loss; affected roads; the manifest with all parameters and warnings; the summary. Nodata is -9999.


# 20. Average Annual Loss

Average annual loss (AAL) is the expected loss per year from landslides triggered by storms. The platform runs design storms of the chosen return periods (Ch. 15), each a full Tier 3 simulation with the same ground and strength settings, and takes the direct loss of each (Ch. 18).

```
p = 1 / T                                       annual exceedance probability
AAL = integral of loss over p
  between the rarest and most frequent scenario:  trapezoid in p
  beyond the rarest (p < 1/Tmax):                 loss held at the rarest scenario's value
  between the most frequent scenario and p = 1:   loss falls linearly to zero at p = 1
```

A test checks the trapezoid against an analytic integral, and that zero loss gives zero AAL and more loss gives more.

> **The assumption that carries the number:** a T-year storm gives the T-year loss. That ignores antecedent wetness, the spatial pattern of rain, and the fact that most storms of a given depth cause no landslide at all; it also depends on the strength scenario, which is uncalibrated (Ch. 27). Treat AAL as an order of magnitude for comparing places or options, not as an insurance figure. It also inherits every assumption in the damage and cost model.

Each return period is an expensive simulation, so the page asks for confirmation.

## First run on a real area

Gilgit, a 57 km2 area (7.8 by 7.3 km) around the test site (`scripts/run_area_demo.py`, `docs/validation/area_demo.json`), strength scenario "weak_clayey" at quantile 0.3 (the weakest standard preset with a graded response; the strong presets fail nothing in these storms and the fitted one over-predicts, Ch. 27.6), losses valued as in Ch. 18 (structure, contents and crops, SAILAB valuation; about 3 times the earlier flat valuation), six return periods from 2 to 100 years, 6 hour storms from the observed IDF cube:

| Return period (y) | Storm depth (mm) | Failing area (km2) | Direct loss today (PKR) | Direct loss, SSP5-8.5 (PKR) |
|---|---|---|---|---|
| 2 | 15 | 0.09 | 606,055,977 | 606,942,709 |
| 5 | 18 | 0.16 | 1,224,447,023 | 1,229,370,267 |
| 10 | 21 | 0.23 | 2,317,665,342 | 2,429,264,794 |
| 25 | 24 | 0.28 | 3,189,036,333 | 3,195,274,664 |
| 50 | 26 | 0.32 | 3,734,438,110 | 3,773,198,537 |
| 100 | 28 | 0.38 | 4,495,795,969 | 4,791,500,034 |
| **Average annual loss** | | | **923,739,987 PKR** | **939,273,786 PKR** |

The climate factor for the 50 year, 24 hour rainfall under SSP5-8.5, 2036 to 2065, is 1.016 (ensemble median over 8 CMIP6 models whose individual ratios range from 0.90 to 1.32). A factor that close to 1 with that spread is **no detectable change**, not a prediction of none.

Cautions that apply to these numbers:

- **The climate scenario changes the average annual loss by only 939,273,786 against 923,739,987 PKR**, because the climate factor is 1.016. That is the honest result of a factor inside the model spread, not a finding that climate has no effect.
- The failing area is a fraction of a square kilometre for every return period (0.09 to 0.38 km2), but the impacted area is about five times larger (0.5 to 2.1 km2): runout carries debris to buildings well beyond the slope that failed, and the loss depends on which buildings it reaches, so it moves in steps.
- The AAL adds a frequent tail (storms more frequent than the 2 year, linear to zero at p = 1) that contributes 151,513,994 PKR of the total; the result is therefore sensitive to the 2 year loss.
- The earlier version of this table used the fitted weak preset and gave about 1 billion PKR with a larger spread of losses; the preset is the dominant uncertainty of every absolute number here.
- Every caveat above in this chapter applies: loss frequency is taken equal to rainfall frequency, with no antecedent wetness. Read the figure as an order of magnitude for this area, not a budget.


# 21. Landslide-Dam Screening

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


# 22. Nature-Based Solutions

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

An early ranking counted only slopes that were *stable before the storm and fail in it*, and put planting alone at 23% **more** failure than the baseline, which is not physical: the model counts only slopes that were stable before the storm (Ch. 4.5), and extra root cohesion turns slopes that were unstable (not counted) into slopes that are stable before the storm and then fail in it (counted). The ranking now uses the **unstable area at the end of the storm, including slopes that were already unstable** (`unstable_km2`, `failing_area` in `engine/run.py`). Every lever is compared on the same cells, so a lever can only remove instability; the "failing" figure is still reported for reference. A unit test checks that planting never increases the unstable area.

The ranking below is for the 57 km2 Gilgit area, a 60 mm/h triangular storm of 12 hours (an extreme storm, 360 mm) and the "weak_clayey" scenario at quantile 0.3:

| Levers | Unstable area (km2) | Change against the baseline (23.7 km2) |
|---|---|---|
| ['planting'] | 0.0 | 100% less |
| ['planting', 'regrading'] | 0.0 | 100% less |
| ['planting', 'drainage'] | 0.0 | 100% less |
| ['planting', 'regrading', 'drainage'] | 0.0 | 100% less |
| ['regrading', 'drainage'] | 14.7 | 38% less |
| ['drainage'] | 22.0 | 7% less |
| ['regrading'] | 22.7 | 4% less |

How to read it: every option that includes planting removes all the instability, because the assumed 6 kPa of root cohesion is as large as the scenario's own cohesion (2 to 10 kPa); that is a property of the user-set effect size, not of planting in general. Without planting the levers are weak: regrading to the 25 degree cap and drainage together remove 38%, drainage alone a few percent, and regrading alone almost nothing, because a saturated slope of friction angle 15 to 26 degrees is unstable even at 25. The effect sizes (6 kPa root cohesion, 25 degree cap, drainage lowering saturation) are user inputs, not measurements, and the ranking is a stability-only comparison; the runout benefit needs a full mitigated run.


# 23. Barriers and Automatic Placement

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

The same 57 km2 Gilgit area and extreme storm (60 mm/h triangular for 12 h), the "weak_clayey" scenario at quantile 0.3, 2 barriers, a budget of 16 simulations (`area_demo.json`, 80 minutes). The first attempt returned barriers of zero length: cells outside the area had been filled with a high elevation, so the pit-filling step flooded the whole area flat and no flow path existed. That bug is fixed (`flow_corridor` now leaves outside cells empty so they act as outlets; the corridor is 7 cells, 210 m). The result:

| | Baseline | With the best 2 barriers |
|---|---|---|
| Direct loss (PKR) | 38,088,729,486 | 37,888,770,942 |
| Buildings with damage state 3 or worse | 3,706 | 3,704 |
| Impacted area (km2) | 13.7 | 13.7 |

Two barriers (5 m and 10 m high) cut the loss by 0.5%, the damaged buildings by 2 of 3,706 and the impacted area not at all. That is small because the failure is spread over thousands of release cells across the area (4.3 km2 of failing hillside sending debris over about 14 km2), so a barrier on one flow path intercepts only a small share. The optimiser works as a tool, but this storm scenario is too large for barriers to matter; it is meant for one gully-sized failure, and the scenario is useful mainly as a limit on what barriers can do. With a 16 simulation budget the result is "a better option", not an optimum.


# 24. Calibration and Validation Protocol

## 18.1 What can and cannot be validated

| Question | Can it be checked here? | How |
|---|---|---|
| Does the code solve its own equations? | Yes | Unit tests and analytic checks (verification, Ch. 7.5) |
| When does rain trigger landslides in Pakistan? | Partly | Dated rain-triggered reports against matched control days (Ch. 25) |
| Where are slopes prone? | Partly | Reports against random places, scored over each report's accuracy disc (Ch. 26) |
| Are soil strength parameters right? | Only through their effect on the two items above | Calibration against reports with block cross-validation (Ch. 27) |
| Is simulated runout and depth right? | Only against published empirical relations | No mapped deposits exist locally (Ch. 29) |
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


# 25. Validation 1: Rainfall Skill (completed)

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


# 26. Validation 2: Spatial Skill

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
- The new ground layers did **not** help; they lowered the score (0.733) because the extra inputs over-fit the 600 events. This agrees with Ch. 28.
- Adding road and city distance gives 0.763: reporting bias is small compared with the terrain signal, but not zero.
- Skill falls with location uncertainty: AUC 0.82 for reports located within 1 km, 0.83 for 1 to 5 km, 0.73 beyond 5 km, as expected when a report's position is only known to its accuracy radius.

> The existing national ML map reports AUC 0.88 to 0.90 (and 0.80 here on mean probability, with the caveat that it was trained on these reports). Its negatives are half flat ground, at least 5 km from any landslide, and its test split is random. This experiment uses random negatives and block cross-validation, so the numbers are lower and the two are not comparable.

The physics model's job in the platform is runout, impacts and scenario testing, where the statistical models cannot help; for *where* landslides are likely, the national ML susceptibility layer (Tier 1) is the better guide, and the physics run should be read as "if this slope fails".


# 27. Calibration of the Physical Parameters

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
| Held-out AUC, calibrated | 0.685 |
| Calibrated values (median over folds) | c=1.05e+03, phi=18.6, cr=1.02e+03, z=2.4, wt=5.57, ks=5.03e-05, api_wet=70.6, k=0.965, s_dry=0.3, s_wet=0.935, f_wt=0.342, beta=1.41, suc=6.76e+03 |

The calibrated set beat the defaults by more than the 0.02 adoption margin, so the antecedent constants are the platform's defaults now (`engine/antecedent.py`) and a strength preset "calibrated_reports_weak" carries the fitted soil depth (2.5 m), cohesion (0.9 kPa) and friction (29.9 degrees).

Read this with care:

- Most of the gain comes from the fitted strength being weak (cohesion near the bottom of its allowed range) and from the antecedent terms together; the antecedent wetness at its initial constants added nothing on its own. The fit says what makes the model rank *reported* landslide days above ordinary days, not what the true soil strength is. The fitted conductivity, water table and root cohesion sit at the edges of their ranges and are not carried into the presets: they are partly absorbing errors elsewhere (ERA5 smoothing the bursts, report bias).
- Held-out folds differ a lot (0.58 to 0.72 for the first two folds) because there are only 144 events, so the 0.68 has a wide interval.
- The skill is relative: it ranks days, it does not predict how many landslides occur.

## 21.5 Second run, with topographic wetness and suction

The same fit repeated with two more parameters (wetness exponent, suction; Ch. 5.7) gives held-out AUC 0.685 against 0.683 before: no improvement, and the added parameters are not identifiable between folds. The first fit (0.683, the antecedent constants and the "calibrated_reports_weak" preset) is the one adopted in the code; the file `physics_calibration_v1_no_wetness_suction.json` keeps it.

## 21.6 The fitted preset is not a default

The fitted point values are stored as the strength preset `calibrated_reports_weak` (cohesion 0.9 kPa, friction 29.9 degrees, depth 2.5 m). They make the model rank *reported landslide days* above ordinary days, which is a ranking task; they are not a description of how much failure a storm causes. On the Gilgit area they leave about a quarter of the soil-bearing slopes unstable even when dry, and they fail 0.2% of the area for a 15 mm shower and 6% for a 120 mm storm. A magnitude 7.2 earthquake fails 8% of a 190 km2 area and releases 41 million m3, with debris 71 m deep at the deepest cell: a worst case, not a forecast. The preset was briefly the first in the list, which made it the page's default and made every run look catastrophic; it is now last, the page defaults to `colluvium_shallow`, and any run that fails more than 5% of its area carries a warning. The shipped presets differ sharply: for the same M 6.8 earthquake `colluvium_shallow` fails nothing (at a 5 cm criterion), `residual_soil` 7.7 km2, `weak_clayey` 17.8 km2 and `calibrated_reports_weak` 14.7 km2. Which one describes a real hillside is a question for soil data that do not exist for the mountains (Ch. 3.4); until then the preset is the dominant uncertainty of every absolute number in the platform.


# 28. Calibration of the Spatial Ground

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


# 29. Check of the Runout Parameters

## 22.1 What data exists

The inventory has almost no volumes (one record) and no runout lengths or deposit areas, so the friction coefficients mu and xi cannot be fitted to Pakistani events. What can be done:

1. **Match published empirical relations.** The Corominas (1996) fits of height drop H against runout length L, H = a L^b, with debris flows 1.109 L^0.857, landslides 2.606 L^0.669, and rock avalanches 1.758 L^0.859, give an expected travel angle for a given volume class. mu and xi per flow type are tuned so simulated reach angles over synthetic and real slopes fall inside the scatter of these relations.
2. **Earthquake ground motion** can be checked against USGS ShakeMaps of past Pakistani earthquakes (done, Ch. 6.2).
3. **Deposit shape** can be scored (IoU, depth error) only if the owner supplies mapped deposits, for example from field surveys or high-resolution imagery.

## 22.2 Result

Synthetic channelised slopes (V-shaped valley, concave profile, heights 500, 800 and 1200 m, volumes 10^4, 10^5 and 10^6 m3) were released as a slab and run to rest on the GPU. For each, H is the elevation drop from the source to the furthest cell with depth over 0.3 m, L the path length, and the ratio is H(simulated) divided by the Corominas H for that L. A ratio of 1 reproduces the relation; the published scatter is about a factor of 2.

| Flow type, as shipped | mu, xi | Median ratio | Range over the 9 cases |
|---|---|---|---|
| Debris flow | 0.12, 200 | 0.71 | 0.43 to 1.03 |
| Landslide (shallow slide) | 0.30, 300 | 1.56 | 1.03 to 2.22 |

Both medians and all nine cases of each type lie inside a factor of 2.3 of the relation, but the two types sit on opposite sides: the debris flow is somewhat too long for its drop in the wettest sense (ratio below 1) and the shallow slide too short, and the shallow-slide ratio grows with volume (1.0 at 10^4 m3, about 2.1 at 10^6). So **mu and xi were left unchanged**: the synthetic valley is not a Pakistani valley, the Corominas relations are for a world sample with their own factor-of-2 scatter, and tuning two coefficients to one synthetic geometry would give false precision. The result says the solver's runouts are in the right range, not that they are calibrated. Any real calibration needs mapped deposits from the owner.

## 22.3 Why the friction was not tuned further

Because the simulated debris-flow runouts sit about 1.5 times longer than the Corominas median for the same drop (a median ratio of 0.71, which is a runout about 1.5 times the median relation's for the same drop) and the shallow-slide ones about half as long, a tuning of mu to the median was started. One evaluation of the debris-flow friction moved the median ratio only from 0.71 to 0.74 when mu rose from 0.12 to 0.13, so matching the median would need a friction near that of the shallow slide, which would erase the difference between the two flow types on the strength of one synthetic channel. It was stopped and the shipped values kept. The large flow depths and impacted areas seen in early runs came from the strength preset, not from the friction (Ch. 27.6), and are handled there.


# 30. Scoring a Run Against an Observed Extent

Any finished run can be scored against an observed deposit or affected area supplied by the user (GeoJSON or zipped shapefile polygons, or a 0/1 GeoTIFF), for the same event. The model extent is the cells where the flow reached at least a chosen depth (default 0.3 m). On the run's own grid, inside the analysed area:

```
hits = model and observed;  false alarms = model, not observed;  misses = observed, not model
CSI = hits / (hits + false alarms + misses)        POD = hits / (hits + misses)
FAR = false alarms / (hits + false alarms)         F1 = 2 hits / (2 hits + false alarms + misses)        bias = (hits + false alarms)/(hits + misses)
```

A perfect match gives CSI 1 and disjoint extents give 0 (tested). This is the only route to validating runout extent. No mapped Pakistani deposit is on the server, so **no real score exists yet**; one supplied event, with a rainfall record, would allow calibrating the friction parameters against it (Ch. 29).


# 31. Accuracy Record

| Claim | Evidence | Status |
|---|---|---|
| The code solves its equations | 131 unit tests; mass conservation, rest, Voellmy speed, entrainment, GPU equals CPU, fast ensemble equals the reference ensemble | **Verified** |
| Rainfall separates landslide days from ordinary days | AUC 0.73 (0.71 to 0.76) for 24 h intensity, leave-one-year-out | **Validated, modest** |
| Published Guzzetti threshold is usable as a watch | TSS 0.32 on the same data | **Validated, weak** |
| Slopes flagged by the physics are the slopes that fail | Ground calibration, held-out blocks: base physics 0.56, with soil texture 0.65; mean slope 0.59 | **Weak** |
| Calibrated parameters are better than the defaults | Held-out AUC 0.59 to 0.68 (144 events) | **Improved, wide interval** |
| Runout lengths are realistic | Corominas relations on synthetic slopes (Ch. 29) | **Right order of magnitude, within a factor of about 2** |
| Earthquake PGA is realistic | 398 ShakeMaps: scatter 0.40 ln units (Ch. 6.2) | **Agrees with ShakeMap, which is itself a model** |
| Shaking locates earthquake-triggered landslide reports | 31 reports, 7 earthquakes: PGA AUC 0.61, Newmark 0.57, slope 0.63 | **Not shown (n too small, reports cluster at roads)** |
| Observed design storms are right | Back-test: Gumbel fitted to the first 30 years, the last 15 years of 75 points exceed the fitted level at 10 years 10% of the time (expected 10%), at 25 years 5% (expected 4%), at 2 years 42% (expected 50%); ERA5-Land smooths bursts | **Validated against held-out years; depths are lower bounds** |
| Mitigation levers and barriers behave sensibly | Directional and mass tests on synthetic cases | **Verified; effect sizes are user inputs, not validated** |
| Dam screening classes and formulas | Formula and synthetic-valley tests; no observed Pakistani dam used | **Verified; not validated** |
| Annual average loss is realistic | Integration verified (identical method to SAILAB); stable when a return period is left out (within 2% for T of 10 years or more, +23% if the 2 year point is dropped) and 8% lower with log-log interpolation; assumes loss frequency equals rainfall frequency; no observed loss record | **Verified arithmetic and stable; the level is not validated** |
| Access and isolation analysis is right | Synthetic network tests; no observed closures | **Verified logic; not validated** |
| Building damage and loss are realistic | No damage records for any Pakistani landslide on the server; valuation follows SAILAB (JRC maximum damage value, storeys, contents); the fragility is assumed, now by district construction class (census); the population raster agrees with the census within a median of 5% over the districts it covers (Ch. 3.5) | **Not validated, assumed** |
| Failure depth and volume are right | Modelled patch volumes against the area-volume scaling of Larsen et al. 2010: median ratio of modelled to implied depth 0.95 over 2,028 failing patches; 2,000 to 20,000 m2 patches 1.00, over 20,000 m2 0.49. No mapped deposits for flow depth or extent | **Failure volume plausible for mid-size patches; flow depth and deposit extent not validated** |

## 23.2 Checks added in the last round

- **Design-storm back-test.** At 75 random points in the north, a Gumbel fitted to the first 31 years of ERA5-Land 24 hour annual maxima is compared with the last 15 years. The 10 and 25 year levels are exceeded about as often as they should be; the 2 and 5 year levels are exceeded a little less often than expected (42% against 50%, 16% against 20%), consistent with a short fitting record or slightly drier recent years. The points are spatially correlated, so this is one realisation, not an independent sample.
- **Failure volume.** The soil depth fitted by the calibration (2.4 m) gives patch volumes that match the Larsen et al. (2010) soil-landslide scaling for patches of 2,000 to 20,000 m2 (the cohort holding most of the patches), and are about half the scaling for patches over 20,000 m2. Those larger patches are contiguous failing hillside made of many neighbouring slides, which the one-slide relation does not describe, so the total volume (130 million m3) is a third of what the relation would give if each patch were one slide. The relation's own scatter is a factor of 2 to 3. I could not re-read the paper in this session, so the coefficients are as recalled and cited.
- **AAL stability.** See the table row above: the figure is insensitive to the rare end of the loss curve and moderately sensitive to the 2 year point and the frequent tail (88% of the total without the frequent tail).
- **Failure volume and deposit from a DEM difference (attempted, not possible).** The idea was to difference a before-event and an after-event DEM at a large known landslide and compare scar, deposit and volume with the model. The test event was the Attabad rock avalanche (Hunza, 4 January 2010). The server's `Pak_srtm.tif` (documented as SRTM, February 2000) was differenced against Copernicus GLO-30 (TanDEM-X data of 2011 to 2015, downloaded from the open AWS bucket) over a 70 km window. After smoothing out sensor striping, **no coherent change beyond 12 m exists anywhere in the window** (smoothed differences stay within -11 to +10 m, against an avalanche tens of metres thick over about a square kilometre and a lake surface raised by about 100 m). The most likely reason is that the server's SRTM file already contains the post-2010 surface or is derived from a later product, so it cannot serve as the "before" DEM; a first attempt with the server's FABDEM looked like a result (a scar and deposit of 17 million m3 each) but was the diagonal striping of the SRTM instrument, and was discarded. This test needs a genuine pre-event DEM (an original SRTM tile, or a 2000s optical stereo DEM) and was not obtainable here (`scripts/validate_dem_change.py`, `docs/validation/dem_change_attabad.json`).
- **What cannot be checked here.** Building damage and loss, flow depth, deposit extent, runout against local events, closure and isolation, and the dam classes need observed Pakistani records (damage surveys, mapped deposits, road closures, dam inventories). None exist on the server, and I found none public. Each stays "not validated" until such records are supplied.

## 23.1 What the accuracy depends on

The largest controllable limits are data: report locations good to 5 to 50 km, no deposit maps, no soil measurements, no damage records, and rainfall reanalysis that smooths bursts. What would raise accuracy most is, in order, mapped deposits and scars for a handful of Pakistani events (to calibrate friction and the failure depth), field strength and soil-depth measurements in a few catchments, a landslide inventory with surveyed positions and times, and a damage survey after one event. If you can provide any of these, the calibration chapters can use them directly.


# 32. 3D Visualization

Two scenes share SAILAB's viewer stylesheet, controls, timeline, probe and export, but each draws its own hazard. The scene files are built from saved arrays (`frames.npz`, `impacts.json.gz`, `rocks.npz`), so the look can change and every run be re-rendered without re-simulating (`rebuild_scene`).

## Debris flow and landslide

SAILAB's water surface (blue, glossy) is gone. Three things replace it:

1. **A rubble body.** A displaced mesh (three.js, standing on Mapbox's own terrain) follows the flow depth, with a per-pixel material in metres: dark wet mud while moving, pale cracked mud at rest, cobbles and boulders from noise thresholds, gravel grain, a warm sheen on the fast front. The mesh normals come from the displaced surface itself, so the lobes read as relief. A first version extruded stacked depth contours and produced stepped pillars; a second used rounded contours and produced smooth blobs; only the displaced surface with a rubble material read as debris.
2. **A scar layer.** Each cell remembers when it failed. It flashes red-orange at that moment and then stays as pale exposed earth with a ragged darker rim (the failed mask is blurred and thresholded with noise, so the outline is not a blocky grid).
3. **A terrain-change mode.** Net bed change from the solver: blue where soil was lost (scar and scour), brown where it was gained (deposit), lit as relief.

Other changes: the flow-speed mode uses a blue-to-dark-red ramp; contact shadows fall beside the flow; buildings change colour with the depth reached so far (damage curve of Ch. 17); the loop is 24 s instead of 9 so events can be followed; the camera is placed below the deposit looking up the slope toward the source.

## Earthquake

For earthquake runs the scene adds the epicentre (red marker), the rupture trace along the fault (glowing line), expanding wavefront rings, a **Ground shaking** map of PGA, and a brief damped shake of the camera as the wave passes. Failures begin at the quake time with the same flash and scar. **The wavefront speed is not physical:** the real S wave crosses a 5 km area in about a second, far shorter than any animation window, so the rings run at a time-scaled speed for visibility. The shaking map is the Joyner-Boore field of Ch. 6, without site amplification.

## Checking the renders

Scenes were rendered in headless Chromium through the DevTools protocol (`scripts/shot.py`), which waits for the scene to settle and reports JavaScript errors, and judged by eye at several moments of the event. This found real faults: the animation controls were blank because of a script error that only the page's own error hook revealed. A software GL renderer is used, so real-GPU frame rate is not measured.

## Export

PNG of the current view and an MP4 recorded from the canvas, transcoded on the server (`/export-video`).


# 33. User Interface

The page follows SAILAB's design system (colours, Barlow Condensed headings, Public Sans text, IBM Plex Mono numbers, glass panels), re-tinted amber so the two products are not confused. Layout: header with the hardware line, a 2D Mapbox map with layer buttons (national susceptibility, national physics, risk index, districts, faults, PNG export), a draggable divider, the 3D pane, a draggable column divider, and the right column.

Right-column panels, top to bottom: draw or upload an area; district discovery (ranked by a national metric); river basins; rainfall and triggers (Open-Meteo, antecedent index, ERA5 wettest 72 h, threshold check); live monitoring; five tabs (screening, instant, physics, earthquake, mitigate); layers of the current run with the PDF report link, landslide-dam screening, scoring against an observed extent and a batch PDF; GIS export, run history and comparison. Discovery also offers national rainfall hotspots. Barrier lines are drawn with the same drawing tool as the area polygon (the polygon is the area, lines are barriers). Every panel states what it is and is not, and the footer repeats that results are screening grade.

Interface checks (after the mitigation tab and run tools were added): the page and the 3D scene load in headless Chromium without JavaScript errors, and the inline script passes `node --check`. Individual controls have been exercised through the API, not clicked through in a real browser.


## Run report

The report (`/runs/<id>/report.html` and `.pdf`) follows SAILAB's report format: a masthead with the model name and run meta, a summary tile grid (failing area, peak PGA for earthquakes, released volume, impacted area, maximum depth, runout, damaged buildings, direct loss, blocked roads, people, isolated buildings), map plates over a hillshade with captions and a legend row (flow depth, deposit, failure time, factor of safety, PGA), hover charts of the storm and of the failed area against time, a run-configuration table, an assumptions and warnings list, and a footer, with SAILAB's light and dark theme (`app/report.py`).

The compare-runs panel links to a **comparison report** (`/compare-runs/<a>/<b>/report.html` and `.pdf`) and the batch list to a **batch summary** (`/batch-report.html` and `.pdf`), both in SAILAB's report format: the teal band header with the model name and tagline, tables with uppercase headers and zebra rows, a legend, and the difference map (only run A, only run B, both, neither, over a hillshade) or the per-run trend chart.


# 34. Access Control, Run Management and Operations Additions

- **Token and rate limit.** If `LANDLAB_TOKEN` is set, every write (POST, DELETE) needs it as `Authorization: Bearer`, `X-Token` or `?token=`; reads stay open on the network, as in SAILAB. A per-address limit of 40 POST requests per minute applies (`LANDLAB_RATE`). This is a guard against accidents and casual abuse on a shared network, not real authentication: the token travels in clear text over HTTP. Set it before exposing the port beyond the lab.
- **Run management.** `DELETE /runs/<id>` removes a run; `POST /runs/cleanup` lists (dry run by default) or deletes runs older than N days that are not among the 30 most recent; `GET /api/queue` lists running and queued jobs. One heavy job runs at a time.
- **API tests.** Flask test-client tests cover the page, area validation, design-storm validation, refusal of runs with missing inputs, the token and the rate limit, unknown runs returning 404, and the dry-run default of cleanup. They run no simulations.


# 35. Autonomous Monitoring Agents

The brief for this section asked for agents that manage continuous data streams, preprocess and diagnose workflows, detect interruptions, activate fallbacks, and keep validating and correcting forecasts. Part of that applies to LANDLAB and part does not, and the agents here are **rule-based programs, not language models**: each is a small deterministic procedure with a log, so it can be tested and explained (`app/agents.py`, 6 unit tests).

## 36.1 What applies and what does not

| Brief | Applies? | What was built |
|---|---|---|
| Continuous data stream management | Partly. The platform has one live stream (Open-Meteo rainfall for the watches and forecast runs); the terrain, land cover, population and inventory are static files. | Every live fetch reports success or failure to the interruption agent; `/api/agents/status` shows each feed's counts and consecutive failures. |
| Detect data interruptions, activate fallbacks | Yes | Open-Meteo calls retry three times with back-off, then fall back to the last good response for the same 0.1 degree point if it is under 6 hours old, marked `stale_cache` with its age so the page and the watch say so. Outages and recoveries are logged. |
| Preprocessing and workflow diagnostics | Partly. Preprocessing is a fixed pipeline, not a stream. | A health snapshot checks the required data files, the age of the ERA5 archive, the GPU and its free memory, disk space and the live feeds. Failed physics jobs are classified (user input, GPU, network, other): GPU and network failures are retried once (CPU solver, or a pause) and the recovery is written onto the result; user-input and unknown errors are not retried because a repeat would fail the same way. |
| Evaluate and optimise models through forecast validation and error correction | Yes, for the rain forecast that drives the watches | Each monitored forecast is stored and later scored against what Open-Meteo reports as observed for the same hours; a bias factor per lead day, shrunk toward 1, scales the forecast before the watch threshold is tested. |
| Continuous learning of the landslide model itself | No | The physics and thresholds are calibrated offline against the inventory (Ch. 27); there is no stream of confirmed landslides or damage to learn from, so nothing is adjusted automatically. |

## 36.2 The forecast back-test

Open-Meteo's previous-runs service archives forecasts made 1 and 2 days ahead. For 40 random points in northern Pakistan over 15 June to 30 September 2026, those forecasts were compared with the Open-Meteo archive (ERA5-based reanalysis rain, **not gauges**) on daily totals (`scripts/validate_forecasts.py`, `docs/validation/forecast_audit.json`).

| Lead | Bias (forecast / observed) | Mean absolute error (mm/day) | Correlation | Detection of a 20 mm/day event | False alarms |
|---|---|---|---|---|---|
| 1 day | 1.08 | 2.1 | 0.67 | 42% | 64% of alerts |
| 2 days | 1.12 | 2.3 | 0.65 | 33% | 70% of alerts |

What this says: the forecasts run 8% (1 day) and 12% (2 days) wetter than the reanalysis, they track the daily pattern moderately (correlation about 0.65), and they are **poor at heavy-rain days**: of the 72 days of 20 mm or more, a 1-day forecast flagged 42% and a 2-day forecast 33%, and about two thirds of the alerts at that level were false. The correction applied to the watch is therefore small (factor 0.93 at one day, 0.90 at two) and cannot repair that. The 0-day row (not shown) is perfect by construction because the archive is built from the same short-lead analysis, so it tests nothing; it is excluded from the conclusions, and the lead-0 factor stays at 1. Because the truth is itself a model, the correction removes forecast drift from the analysis, not bias against real rainfall; against gauges (none on the server) the picture could differ.

## 36.3 Live audit and the event log

The watches store every forecast they issue. Every 30 minutes the audit agent scores the forecasts whose horizon has passed and updates the live bias factors, which take precedence over the back-test prior once they exist. Events (feed down and recovered, job errors and recoveries, audits, health changes) are kept in `datasets/state/agents/events.jsonl` (the last 2,000) and shown at `/api/agents/status`; a status chip in the page header links to it. At the time of writing the health snapshot reports one real problem: the ERA5-Land archive on the server ends on 2026-05-20, so hindcasts of storms after that date (and the calibration of any recent event) are not possible until the archive is extended.

## 36.4 Limits

The interruption agent can only keep a watch running on a feed that returns at all: when Open-Meteo is down for more than 6 hours, the watch reports the error rather than guessing, and there is no second forecast provider to switch to. Recovery from a GPU failure repeats the whole run on the CPU, which is slower, and a run that fails for a reason not in the list is reported, not repaired. The agents do not fix the model: they keep it fed, running and honestly scored.


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
- **Mitigation comparison**: unmitigated against mitigated run, with the change in failing area, impacted area, loss, blocked road length and buildings at DS3 or above (Ch. 22, 23).


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
| 16 | A "6 m barrier" on a steep slope let 90% of a flow through | The new barrier test | A wall's height is measured above the ground upslope: the wall cell is raised by height plus the ground drop across a cell (Ch. 23) |
| 17 | IMERG sub-hourly values were intensities, not depths, so a 1 h design storm summed to 9.1 mm instead of 8.0 mm | Mass check of the hyetograph against the IDF depth | Convert intensity to depth by multiplying by duration before taking the shape (Ch. 15) |
| 18 | `np.interp` rejected an array `left` argument in the sub-hourly branch | First hyetograph call | Handle the shortest-window extrapolation explicitly |
| 19 | The reference storm (360 mm) is five times the observed 100-year 24 h depth at Gilgit | Compared with the new IDF table | Described as a stress test; use the observed design storms for realistic runs |
| 20 | The first debris viewer drew stacked depth contours: stepped pillars, then smooth blobs | Rendering and looking at it | Replaced by a displaced surface mesh with a rubble material (Ch. 32) |
| 21 | The new viewer's controls were blank | A render showed an empty timeline; no console message | An in-page error hook exposed a `const` used before its definition; the block was moved earlier |
| 24 | The deposit rebuild failed when the geometry helper arrays were cropped twice | Rebuilding a scene from saved frames | `viewer.build` takes already-cropped arrays; the crop only locates them |
| 25 | A patch list for the viewer applied in the wrong order and failed loudly (three times) | The build raised "patch target missing" | Patches that touch the same text were merged; the failing check is kept on purpose so a changed SAILAB viewer cannot silently break the scene |
| 26 | My own document builder deleted the new visualisation chapter | Two chapter files shared a slug | Rewritten; chapter slugs must be unique |
| 27 | With land-cover root cohesion the Gilgit failing area rose from 1.2 to 4.4 km2 | Comparing runs | Reported as a sensitivity, not hidden (Ch. 19) |


# 39. Considered and Declined

- **Coupling with flood modelling.** Declined by the owner: LANDLAB and SAILAB stay separate products. Debris flows are not run through a water solver.
- **Using the national ML susceptibility as a predictor in the validation models.** It was trained on the inventory; using it would leak the answer. It is shown as a labelled optimistic reference only.
- **Bilinear resampling of population.** Counts are not intensities; see Ch. 38 (#1).
- **Promoting year-only dates to a day.** Invents precision that would corrupt the rainfall validation.
- **A Pakistan-specific I-D threshold.** Fitted, but no better out of sample than the published Guzzetti curve (Ch. 25.4), so not adopted.
- **Absolute landslide probabilities.** Not identifiable from a report inventory.
- **A temperature guard on GPU jobs.** Dropped by the owner's decision (Ch. 2.3).
- **Interactive whole-country physics.** Meaningless at the needed cell size (Ch. 4.1); replaced by the tiled national product.
- **External multiphase runout engines (r.avaflow and similar).** Not available on the server; the in-house solver is verified but uncalibrated, and this is stated wherever it is used.
- **Raising the inventory with downloaded catalogues.** No further catalogue was found on the server, and none was downloaded without the owner's say-so.
- **Routing a landslide-dam breach flood downstream.** That is flood modelling; the dam screening stops at formation, stability, lake volume and a breach peak (Ch. 21).
- **An areal reduction factor on design storms.** The constants are not available from a source on the server; point rainfall is used and is conservative for the areas run.
- **A surrogate model for barrier placement.** Not trusted at this sample size; every candidate is a real simulation under a hard budget.
- **Default wall costs.** No cost data exist here; the optimiser takes the cost from the user and says what happens at zero.
- **Filling in geology strength values from intuition.** The 16 geology units are colour classes with guessed lithology; invented values would look like data. Multipliers stay 1.0 until calibration.
- **Real-time seismic wave speed in the animation.** Physically correct and invisible; the rings are time-scaled and say so.


# 40. Known Limitations

1. **Calibrated and validated only as far as the inventory allows.** See Ch. 31 for exactly what has and has not been checked.
2. **One soil layer, infinite slope.** No deep-seated slides, no rock-slope kinematics, no rockfall (not modelled: removed from the platform), no snow avalanche, no glacial-lake outbursts.
3. **Rain is spatially uniform** over the area by default and comes from a point (ERA5, CHIRPS, forecast) or a design storm; a gridded-rain option exists (Ch. 5.7) but cannot be tested on this inventory.
4. **Pore pressure is a proxy** from a wetting front, not groundwater flow. A topographic water-table option and a suction option exist; neither improved held-out skill, so both are off.
5. **Failure depth equals soil depth**, thinned with slope by an assumption and optionally capped by the bedrock-depth map; real slip surfaces are not mapped, and the borehole, groundwater and soil data supplied later are on the Indus plain, not on slopes, so they could not constrain it (Ch. 3.4).
6. **Earthquake ground motion** uses NGA-West2 with a Vs30 site term (and a regional intraslab model for deep events) with no directivity; it is within a factor of about 1.5 of ShakeMap, low by about a quarter for M 7 and above (Ch. 6.2).
7. **Runout friction is a scenario value by flow type;** the single-phase depth-averaged model does not separate solid and fluid phases.
8. **Impacts** use assumed fragility medians and a single unit cost; no indirect loss, no lives.
9. **Building heights** are assumed 6 m (display only); footprints come from a satellite-derived dataset with its own errors.
10. **ML susceptibility** covers the north only (about 31 N and up), because the landslide inventory used to train it has almost no records in the south. The physics screening (Tier 1 national physics product, Tier 3) covers all of Pakistan; the south is mostly flat, so little of it can fail.
11. **Terrain** is SRTM at 29 m: gullies, small scarps and road cuts are not resolved.
12. **Spatial misregistration** of the 3D canvas (lon/lat rectangle over a UTM grid) is small for tens of kilometres and grows with area.
13. **Design storms** are point depths from 46 years of ERA5-Land annual maxima: 100- and 200-year values are extrapolations, short durations are lower bounds, and storms are limited to 24 h.
14. **Mitigation effects** (root cohesion, regrading, drainage, barrier height) are the user's scenario inputs; regrading changes stability only, not the terrain the flow crosses; barriers are not drawn in the 3D scene.
15. **Average annual loss** assumes a T-year storm gives the T-year loss.
16. **Dam screening** uses a drainage area truncated at the analysed edge and an embankment breach formula for the peak; there is no downstream routing.
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

`cd backend && PYTHONPATH=. ~/flood/venv/bin/python -m unittest discover -s tests -t .` runs 131 tests: the original physics and integrity tests, the app layer (fast ensemble equals the reference, GPU equals CPU, mobilisation rule), and the engine (mass, rest, speed, entrainment, GPU equals CPU, Joyner-Boore, Wells-Coppersmith, mobilisation). GPU tests skip if the shared GPU cannot be initialised.

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


# 42. SAILAB Parity and FastSlide-Inspired Features

## 43.1 Pages and interface taken from SAILAB (version 2.5.0)

- **Landing page** at `/` (WebGL shader background, links to the two tools), **the app** at `/app`, and **LANDLAB Instant** at `/instant`.
- **Instant** draws an area and returns, in seconds, the unstable area against a 24 h rain ladder (0, 25, 50, 100, 150, 200, 300, 450, 600 mm), a critical-rain map and failing-cells overlays. It uses the median strength of the chosen preset, not an ensemble, so it is a screening view; the full run remains the product.
- App additions: header navigation and place search, a welcome card, 3D expand/hide, custom DEM upload, saving and loading a run file, and calibration to an observed landslide extent.
- **Custom DEM.** A user GeoTIFF replaces the national DEM inside its footprint. Areas outside the file are refused with a message rather than filled from another source.
- **Run file.** A run's inputs are written to `inputs.json`; loading one passes through a whitelist, so unknown or oversized fields are dropped.
- Not taken: the basemap switch (satellite or streets) in the 2D view, because swapping the style drops the map's sources.

## 43.2 Calibration to an observed extent

The user supplies observed landslide polygons. The platform runs trial scenarios over a strength quantile and a friction-multiplier grid and keeps the one with the highest critical success index (CSI) against the observed cells. Synthetic check: an extent produced at quantile 0.55 was used as the "observed" one, starting from quantile 0.2 (CSI 0.14); the search chose 0.5 and CSI rose to 0.92. This shows the search finds a known answer; it does not show that a real inventory is reproduced, which depends on the reports' positional accuracy.

## 43.3 Ideas from FastSlide (fastflood.org)

Implemented: **strength zones** (the user supplies polygons with `cohesion_kpa` and/or `friction_deg`; those cells take the stated values, cohesion clipped to 0 to 100 kPa and friction to 5 to 50 degrees, later polygons override earlier ones) and **per-slide runout statistics** (mean, median and 90th percentile of runout over connected flows, shown in the results and the report). The zone logic has a unit test.

Not implemented: SMAP soil-moisture input (the platform has its own antecedent-wetness treatment), an erosion or entrainment term (not calibrated here), and in-browser (WebAssembly) computation, which does not apply to a GPU server design.

The calibration also accepts no file: with "match the national susceptibility map" the target is the cells of the machine-learning susceptibility map at or above 0.5 (adjustable). In a trial on the Gilgit test area the overlap rose from 0.09 to 0.20 (strength quantile 0.3, friction halved). The target is a model, not an observation, so this makes the physics agree with the statistical layer; it does not validate either.

## 43.4 Cross-checks against external tools (from the improvement plan)

| Tool | What was done | Result |
|---|---|---|
| OpenQuake hazardlib | `scripts/check_gmpe_oq.py`: BSSA14 (60 magnitude-distance points for each of 4 Vs30 values) and the BC Hydro intraslab model (30 points for each of 6 depth and Vs30 pairs) compared with OpenQuake's implementations. | Identical to rounding error (BC Hydro exactly, BSSA14 to 1e-13 per cent). One point to know: OpenQuake has no "unspecified mechanism", so the comparison uses strike-slip; the platform's default unspecified term is 0.0383 ln units (3.8 per cent) lower, which is the published difference between the two coefficients, not an error. OpenQuake is AGPL and is used in this validation script only, never imported by the shipped backend. |
| Landlab `LandslideProbability` | `scripts/check_landlab_slope.py`: 300 random cells, 2,000 Monte Carlo draws each, same distributions. | Landlab and the SINMAP form of the equation on the same samples agree to Monte Carlo noise (correlation 0.9999). Against the platform's standard infinite-slope form they differ clearly: mean failure probability 0.28 against 0.21, and by up to 0.65 in single cells. The cause is that SINMAP (and so Landlab) divides cohesion by sin(b) where the standard form divides by sin(b) cos(b), and fixes the water to soil weight ratio at 0.5. The platform keeps the standard form; Landlab is therefore the more pessimistic of the two on cohesive soils. |
| TRIGRS (Iverson 2000 solution) | `scripts/compare_iverson.py`: the published transient pressure-head solution implemented directly and compared with the Green-Ampt proxy on 675 single-column cases (slope 25 to 45 degrees, depth 1 to 3 m, conductivity 1e-6 to 1e-4 m/s, rain 5 to 100 mm/h, water table at the slip surface or 0.5 or 1 m below it). | The two agree on failure or no failure in 76 per cent of cases. The Green-Ampt proxy is the slower and less sensitive: where both fail it takes a median of 2.3 times as long (10th to 90th percentile 1.0 to 8.2), and it misses 147 cases (22 per cent) that the Iverson solution fails, because a pressure wave from a shallow water table reaches the slip surface long before a wetting front does. In 13 cases only Green-Ampt fails. This is a comparison of two simplified columns on assumed soil values, not a test against real slides. The TRIGRS program itself was not built or run, so the Fortran code, its unsaturated option and its runoff routing were not tested. |
| USGS groundfailure | Read, not run. Its landslide models (Nowicki Jessee 2018 and others) need global lithology, land cover and topographic index grids that are not on the server, and the code was not installed. | No comparison made. |

Not done and why: r.avaflow needs GRASS GIS and a licence check; the D-Claw repositories named in the plan could not be found; MintPy needs a Sentinel-1 data account and is a separate project; Landlab's flow-routing tools were not swapped in because the existing terrain code is already tested against analytic cases.


# 43. References

- Azarafza, M. et al. (2021). Deep learning-based landslide susceptibility mapping. *Scientific Reports* 11, 24112 (the national ML method).
- Bates, P. D., Horritt, M. S., Fewtrell, T. J. (2010). A simple inertial formulation of the shallow water equations. *Journal of Hydrology* 387, 33-45.
- Caine, N. (1980). The rainfall intensity-duration control of shallow landslides and debris flows. *Geografiska Annaler A* 62, 23-27.
- Corominas, J. (1996). The angle of reach as a mobility index for small and large landslides. *Canadian Geotechnical Journal* 33, 260-271.
- Funk, C. et al. (2015). The climate hazards infrared precipitation with stations (CHIRPS). *Scientific Data* 2, 150066.
- Green, W. H., Ampt, G. A. (1911). Studies on soil physics. *Journal of Agricultural Science* 4, 1-24.
- Guzzetti, F., Peruccacci, S., Rossi, M., Stark, C. P. (2008). The rainfall intensity-duration control of shallow landslides and debris flows: an update. *Landslides* 5, 3-17.
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
