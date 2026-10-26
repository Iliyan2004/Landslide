# Gilgit Landslide Platform: Small-Scale Methodology

Pilot for Gilgit, designed to expand to all of Pakistan. Sister project of SAILAB (flood). It follows the same pattern: tiers by speed and fidelity, every number labelled as measured, published formula, or scenario, cached by AOI hash, provenance in every output.
The full national methodology is in `LANDSLIDE_PLATFORM_FULL_METHODOLOGY.md`. This file is the cut-down version for one area.

## 1. Scope

- **Area:** `Shapefiles/Gilgit shp/Gilgit.shp`. Its extent is 93 x 91 km (UTM 43N), which is district scale, not the city alone. A tighter city polygon can be dropped in later; the grid stays the same.
- **Grid:** `gilgit_dem.tif`, 26.63 m, EPSG:32643, 3419 x 3501 cells. Every layer is resampled onto this grid.
- **Hazards in the pilot:** shallow rainfall/snowmelt slides, debris flows in side gullies, rockfall source zones, earthquake-triggered slides, landslide-dam candidates on the Gilgit and Hunza rivers.
- **Out of the pilot:** deep-seated slides, InSAR deformation, live alerting.

## 2. Data

### 2.1 Already held

| Data | Location | Status for Gilgit |
|---|---|---|
| DEM 26.6 m | `gilgit_dem.tif` | Ready. Source is Copernicus GLO-30 (a surface model). |
| DEM derivatives: filled DEM, slope, aspect, D8 direction, flow accumulation, streams, subbasins | `DEM derrived inputs/` | Ready. Curvature, TWI, relief, roughness still to compute. |
| Landslide inventory (NASA COOLR points) | `LANDSLIDE PLATFORM/additional data/downloaded_data/landslide_inventory/` | **Too thin.** 188 points nationally, 7 inside the AOI, 35 within 50 km. Not enough to train a supervised model alone. |
| Earthquake catalogue | `earthquake data/raw/earthquake/`, `.../earthquake_hazard/usgs_events.*` | Events only. No PGA grid yet. |
| Hourly rainfall and temperature, ERA5-Land 0.1 degree | `Snow Glacier Model/Precipitation`, `era5 Temperature` | 2025 and Jan-May 2026 only. Too short for rainfall thresholds. |
| Soil texture 0-30 cm (sand, clay, bulk density, coarse fragments, SOC) and derived infiltration, percolation, capacity | `Snow Glacier Model/Flood susceptibility/` | Ready, 250 m. Scenario prior only, not shear strength. |
| Glacier basins, glacier lakes, IceBoost thickness, debris factor, snow/ice melt model output | `Snow Glacier Model/`, `Glacier thickness/`, `GLOF_Model/` | Ready. Feeds the snowmelt trigger and GLOF-linked blockages. |
| HydroRIVERS (Asia) | `LANDSLIDE PLATFORM/additional data/downloaded_data/river/` | Folder present. Confirm the shapefile itself is inside. |
| OSM Pakistan (roads, buildings, land use, places) | `runout data/exposure/osm/pakistan-latest-free.gpkg.zip` | Ready, needs unzipping and clipping. |
| Sentinel-1 / Sentinel-2 product catalogues | `runout data/deformation/satellite_catalog/` | Metadata only, no imagery. |
| Platform code, config, registries, tests | `landslide-platform/` | Config exists; several dataset keys are not wired into the API yet. |

Not useful for Gilgit: `sediment/discharge/discharge_daily.csv` (GloFAS values for sites outside the region).

### 2.2 Missing, and the best source for each

Satellite embeddings do not replace everything. They are a learned summary of imagery, so they suit mapping scars, change and surface material. They cannot give elevation, rainfall, shaking or soil strength. Each missing item therefore uses whichever source is best for it.

| Missing data | Best source | Why this source | Automated |
|---|---|---|---|
| Landslide scars to widen the 7-point inventory | **Satellite embeddings** (Google Satellite Embedding V1, 64 bands, 10 m, 2017-2025) | Similarity to known scars and year-to-year change finds candidate scars without a hand-built training set | Yes |
| Surface material / rock-type proxy | **Satellite embeddings**, clustered | No open lithology map of Gilgit is detailed enough; clusters labelled from sparse geology and field points | Yes (download) |
| Land cover | ESA WorldCover 2021 (10 m) | A true classification with published accuracy; embeddings are not class labels | Yes |
| Vegetation, moisture, burn, bare soil, two epochs | Sentinel-2 SR dry-season composites (NDVI, NDMI, NBR, BSI) | Physical, interpretable indices; needed for the cohesion prior and change maps | Yes |
| Rainfall history 1981-today | CHIRPS daily (0.05 degree) | Long record for intensity-duration thresholds. ERA5-Land hourly (1980-present) is already available in your pipeline for sub-daily detail | Yes |
| Active faults | GEM Global Active Faults | Open, harmonised, curated | Yes |
| Buildings | Google Open Buildings v3 (confidence 0.7 or higher) | Far denser than OSM in the region | Yes |
| Population | WorldPop 100 m | Exposure | Yes |
| Seismic shaking (PGA) | USGS ShakeMap per event, or GEM seismic hazard map for scenarios | Needs real ground motion, not epicentre distance | Manual per event |
| Lithology (GLiM) | GLiM (Hartmann and Moosdorf 2012) | The standard open global map; no stable API | Manual |
| Cohesion, friction angle, soil depth, groundwater, joints | Field data, or literature scenario ranges | Cannot come from satellites | Manual / scenario |
| Verified landslide polygons | Field mapping, NDMA/GB disaster records | Needed for validation | Manual |

Run: `python landslide-platform/scripts/download_gilgit_data.py --dry-run`, then without `--dry-run`. Outputs go to `landslide-platform/datasets/raw/gilgit/`, aligned to the DEM grid. Embeddings are stored as int8; decode with `v = sign(q) * (q / 127.5)^2`.

## 3. Pipeline

1. **Grid and terrain.** Reproject everything to EPSG:32643 at 26.63 m. Compute slope, aspect, profile and plan curvature, TPI, TRI, local relief, TWI, stream power, HAND, distance to stream, LS factor. Record source, algorithm, units and timestamp for each layer.
2. **Cleaning gates.** Reject a layer with more than 10 % NoData inside the AOI. Strict polygon-only statistics.
3. **Inventory expansion.** Embed the 7 in-AOI scars plus the 35 nearby ones. Rank every cell by cosine similarity to the scar embeddings and by 2017-to-2024 embedding distance. A person reviews the top candidates against Sentinel-2 before they join the inventory. Unreviewed candidates never enter training.
4. **Tier S, susceptibility.** Gradient-boosted trees (and a logistic regression as a baseline) on terrain, WorldCover, NDVI/BSI, distance to fault, distance to stream, soil prior, and embedding principal components. Spatial block cross-validation with blocks wider than the autocorrelation range. Report AUC, precision-recall and a calibration plot. Output is a 0-1 relative score and classes, never an annual probability.
5. **Tier T, rainfall and snowmelt trigger.** Infinite-slope factor of safety with Green-Ampt infiltration from rain plus melt. Soil depth, cohesion, friction and water table are bounded scenario ranges run as an ensemble. Output is the share of ensemble members with FS below 1 per cell. Rainfall thresholds come from the CHIRPS/ERA5 record against dated events.
6. **Tier E, earthquake.** Newmark displacement from a ShakeMap PGA and yield acceleration from slope and the strength scenarios. Only run for a stated event or scenario.
7. **Tier R, runout.** Empirical envelope (Heim ratio / reach angle) from candidate release cells over the DEM, flagged as an envelope, not a simulated footprint. Landslide-dam candidates where a runout reaches the river network.
8. **Tier X, exposure.** Overlay buildings, roads, population on susceptibility and runout. Counts per class, per ward and per road segment.
9. **Report.** Map, tables, run manifest (inputs, hashes, versions, parameters, ensemble ranges), uncertainty statement.

## 4. Validation

- Independent test blocks held out by geography, not random cells.
- Compare with the 42 inventory points, and with Sentinel-2 before/after images for any event dated in the record.
- Report how many cells fall outside the training range of each predictor; do not extrapolate there.
- A rainfall exceedance is a trigger signal. It is never labelled a confirmed landslide.

## 5. Limits to state on every output

- 26.6 m surface model: buildings and trees affect slope.
- Seven in-area inventory points; the embedding-assisted inventory is candidate-based until reviewed.
- Soil strength, depth and water table are scenarios, not measurements.
- Gilgit terrain is steep; the ACC flood-solver depth issue in SAILAB does not apply here, but 26.6 m smooths cliff-scale slope and under-reports rockfall source zones.
- Embeddings are a feature layer and a search tool. They are not ground truth.

## 6. Expansion to Pakistan

Same code and registry; the AOI becomes a tile list. National datasets (CHIRPS, WorldCover, embeddings, faults) are fetched per tile; the inventory model is retrained per region with block cross-validation across regions. The `parameter_mode: scenario_ensemble` default stays until local measurements exist.

## 7. Status

- Written: this document, `scripts/download_gilgit_data.py`.
- Not yet run: the downloader (it needs your approval for the Earth Engine calls) and every model stage.

## Accuracy additions (second round)

| Addition | Source | Script | Result |
|---|---|---|---|
| Hourly rain, soil water and snowmelt at 188 Pakistan reports and 564 matched no-report windows | ERA5-Land hourly, Earth Engine | `download_hourly_climate.py`, `analyze_hourly_climate.py` | Rain in the previous 7 days is the best single predictor (AUC 0.70 for rain-type reports); 1-6 hour intensity is weak at 9 km; combining intensity, 7- and 30-day rain gives a cross-validated AUC of 0.71 |
| Soil texture (sand, silt, clay, 0-30 cm) giving cohesion and friction a spatial pattern | SoilGrids 2.0, Earth Engine | `download_soil_texture.py` | Cohesion factor 0.78-1.26 and friction offset -0.5 to +0.8 degrees (5th-95th percentile); not supported by the 17 in-area reports (AUC 0.32 for weak soil), so treat as an unvalidated prior |
| Elevation cross-check | Copernicus GLO-30, Earth Engine | one-off | Agrees with the 26.6 m DEM: RMSE 6.5 m, bias 0.2 m on 1,500 random points; no change needed |

Checked and not available by script: NASA COOLR/GLC bulk download (blocked, 404), USGS ScienceBase inventories (Cloudflare challenge), ALOS 12.5 m DEM (needs an ASF/Earthdata login), global Vs30 (no accessible Earth Engine asset). Landslide polygons with dates for Gilgit-Baltistan are not openly published.
