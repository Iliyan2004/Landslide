# LANDSLIDE MODELLING PLATFORM — COMPLETE TECHNICAL METHODOLOGY

**Document type:** Engineering methodology, data specification, model-selection framework and web-application implementation blueprint  
**Version:** 1.0 | **Date:** 12 October 2026    
**Geographic focus:** Pakistan (especially Gilgit-Baltistan, Khyber Pakhtunkhwa, Azad Jammu and Kashmir); transferable globally with local recalibration.  
**Data policy:** Free-to-access primary and supplementary datasets, with explicit licensing and access checks. Free access does not imply unrestricted redistribution or commercial reuse.

---

## 0. Executive design decision

Build **one web interface around several distinct hazard engines**, rather than pretending a single weighted-overlay equation simulates all landslides. The layers are:

1. **Terrain and inventory foundation** — user AOI; immutable, versioned, quality-checked raster/vector inputs.
2. **Tier S: rapid susceptibility screening** — lithology/terrain scoring, statistical logistic regression, random forest or gradient boosting; spatially validated when a sufficient historical inventory exists.
3. **Tier T: time-varying shallow slope stability** — rainfall/snowmelt infiltration, groundwater pressure and infinite-slope factor of safety (FS), using explicit measured, inferred or scenario geotechnical parameters.
4. **Tier E: earthquake-triggered failure** — ground-motion intensity, pseudostatic FS and Newmark permanent displacement; only where suitable geotechnical and seismic input assumptions exist.
5. **Tier R: source-to-impact runout** — separately configured rockfall, shallow slide, debris-flow and channelized sediment routing; optional external multi-phase dynamics engine.
6. **Tier D: erosion and river sediment** — RUSLE-style hillslope erosion screening, critical shear and bedload capacity, debris-flow entrainment/deposition, sediment delivery and channel blockage scenarios.
7. **Tier X: exposure, expected consequences and scenario comparison** — buildings, roads, facilities, river blockages, people, uncertainty and mitigation.
8. **Tier M: monitoring and alerts** — satellite change signals, rain-threshold triggers, earthquake event triggers, optional InSAR; never label rainfall exceedance alone as a confirmed landslide.

**Model outputs have distinct meanings:** susceptibility is spatial propensity, stability is a modelled mechanical state, hazard adds frequency/intensity, and risk requires exposure and vulnerability. A 0–1 ML susceptibility score is NOT automatically an annual probability. A factor of safety below 1 is NOT a defensible prediction of failure timing without validated dynamics and initial/boundary conditions.


---

## 1. Scope and design principles

### 1.1 Physical processes to distinguish

| Hazard | Initiation mechanism | Recommended model | Time scale | Governing missing inputs |
|---|---|---|---|---|
| Shallow translational landslide | Increase in pore pressure / loss of root reinforcement | Infinite-slope FS + Green–Ampt / Richards-type infiltration | Minutes–days | Soil depth, cohesion, friction angle, hydraulic properties, pore pressure |
| Deep-seated slide | Bedrock weakness, variable basal geometry, groundwater, seismic loading | Limit equilibrium (Bishop/Janbu/Spencer) and optional FEM | Event–years | Slip surface, stratigraphy, joints, groundwater and strength measurements |
| Earthquake-triggered landslide | Inertial loading above yield acceleration | Pseudostatic screening, Newmark displacement | Seconds | PGA/acceleration time history, strength, mass geometry |
| Rockfall | Discontinuity failure and detached block motion | Kinematic release + ballistic/particle trajectory | Seconds–minutes | Joint orientations, block size, restitution, roughness |
| Channelized debris flow | Rapid mobilization of saturated coarse sediment | Empirical mobility first; r.avaflow-type multiphase dynamics for selected scenarios | Minutes–hours | Source volume, water fraction, rheology, entrainment |
| Bank failure/landslide dam | Erosion or failure into stream | Bank stability + runout–river intersection and blockage screening | Event-dependent | Bank geometry, water levels, deposits, breach geometry |
| Diffuse sheet/rill erosion | Rainfall detachment and runoff transport | RUSLE annual potential erosion, runoff shear indicators | Storm–years | Erosivity, soil erodibility, C/P, land management |

### 1.2 Spatial and temporal resolution

- **Default regional screening:** 30 m DEM grid, derived metrics at native grid; effective reliability limited by geology and soil source resolution.
- **Local slope modelling:** 5–10 m only with genuine high-resolution terrain and defensible soil inputs. Upsampling a 30 m DEM to 5 m does NOT create 5 m information.
- **Rainfall:** IMERG half-hourly ~0.1° for event triggers; ERA5-Land hourly ~0.1° for temperature/snow/soil; CHIRPS daily ~0.05° for climatology. Do not present these as observed 30 m rainfall.
- **SoilGrids:** 250 m; not a direct measurement of geotechnical shear strength.
- **Forecast horizon:** limited by the selected meteorological forecast's published horizon and latency; record forecast issuance and validity times.
- **Runout resolution:** preferably ≤10 m when available; at 30 m only screening-grade channelized routes and coarse footprints.
- **Time:** store all model times in UTC, display localized time with explicit timezone.

### 1.3 No unsupported defaults

Unknown soil thickness, cohesion, friction angle, hydraulic conductivity, suction, groundwater depth, joint orientation, source volume and runout friction MUST be marked **unknown**, replaced with bounded literature **scenarios** only by explicit model configuration. Do not silently treat fictional measurements as observations. Return an `insufficient_data` state for high-fidelity runs when essential variables are missing.

---

## 2. Complete raw-data acquisition registry

**Access codes:** P = available publicly; R = free registration/API credential; C = conditional/verify terms; L = local field information generally not publicly available; O = optional. **Priority:** A = base minimum; B = advanced engine; C = local study/specialized.

| ID | Raw source and access entry point | Native data/resolution | What to acquire and why | Access | Priority |
|---|---|---|---|---|---|
| D01 | **Copernicus DEM GLO-30 Public** — https://registry.opendata.aws/copernicus-dem/ | DSM, ~30 m, tiled COG | Elevation, profile and plan curvature, relief, catchments, channel network, runout terrain | P/C terms | A |
| D02 | **NASADEM / SRTM** — https://lpdaac.usgs.gov/ | DEM ~30 m | Secondary terrain and comparison/bias check | R | A |
| D03 | **OpenTopography** — https://www.opentopography.org/developers | Multiple DEMs | Local finer data where published; API key for standard global endpoints, enterprise terms may apply to commercial integration | R/C | C |
| D04 | **GLiM global lithology** — Hartmann & Moosdorf; locate archive via https://doi.org/10.1029/2012GC004370 | Geological vector polygons | Lithology, rock classes; regional geological susceptibility | P/C archive | A |
| D05 | **OneGeology / Geological Survey of Pakistan** — https://portal.onegeology.org/ | Variable-scale geological maps | Faults, lithology, bedrock units, fold/structure data where legitimately obtainable | C | B |
| D06 | **SoilGrids 2.0** — https://files.isric.org/soilgrids/latest/data/ and https://docs.isric.org/globaldata/soilgrids/ | 250 m, six depth intervals | Sand, silt, clay, bulk density, coarse fragments, organic carbon; candidate pedotransfer inputs, NOT measured cohesion | P | A |
| D07 | **ESA WorldCover 2021 v200** — https://esa-worldcover.org/en/data-access | 10 m categorical | Vegetation/forest/bare/built cropland cover, land-cover transition proxy, erosion cover factor | P | A |
| D08 | **Dynamic World** — https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1 | 10 m per-scene probabilities | Seasonal cover probability and disturbances; acquire cloud-screened composites | R (GEE) | B |
| D09 | **Sentinel-2 L2A** — https://dataspace.copernicus.eu/ | 10–20 m multispectral | NDVI, NDMI, NBR, bare-soil fraction, post-event change inventory, vegetation stress | R | A |
| D10 | **Sentinel-1 GRD/SLC** — https://dataspace.copernicus.eu/ | ~10 m backscatter; SLC phase | Event mapping, landslide change detection; SLC for InSAR with coherence/geometry limitations | R | B |
| D11 | **NASA COOLR / Global Landslide Catalog** — https://gpm.nasa.gov/applications/landslides/coolr | Point/polygon records, uneven completeness | Historical reported landslide occurrences and event identifiers; scrutinize locational uncertainty | P/C | A |
| D12 | **NASA LHASA datasets/code** — https://github.com/nasa/LHASA | ~1 km daily nowcast / global static data | Global reference baseline and benchmark, not independent ground truth | P/R Earthdata | B |
| D13 | **Copernicus EMS, UNOSAT, national agencies, literature** — https://rapidmapping.emergency.copernicus.eu/ ; https://unosat.org/ | Event polygons/maps of varied accuracy | Independent post-event landslide delineations, validated extents | P/C | A |
| D14 | **GPM IMERG** — https://gpm.nasa.gov/data/imerg | Half-hourly ~0.1°; calibrated final vs near-real-time runs | Short-intense rainfall, accumulation windows, onset/antecedent forcing | R Earthdata or GEE | A |
| D15 | **CHIRPS v2+** — https://www.chc.ucsb.edu/data/chirps | Daily ~0.05° | Historical rainfall, antecedent windows, long-term percentile thresholds | P | A |
| D16 | **ERA5-Land** — https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land | Hourly ~0.1° | Temperature, precipitation, soil moisture layers, snow, evaporation, freeze–thaw proxy | R CDS | A |
| D17 | **Open-Meteo weather forecast/historical API** — https://open-meteo.com/en/docs | Model-specific hourly grids | Operational forecast rainfall/temperature, issuance metadata | C; inspect commercial plan/API terms | B |
| D18 | **SMAP** — https://nsidc.org/data/smap | 9–36 km products | Large-scale surface/root-zone moisture anomaly; never downscale by interpolation as local slope moisture observation | R Earthdata | B |
| D19 | **Global seismic catalog** — https://earthquake.usgs.gov/fdsnws/event/1/ | Earthquake event point and parameters | Event date, magnitude, depth, epicentre, mechanism if available | P | B |
| D20 | **USGS ShakeMap** — https://earthquake.usgs.gov/data/shakemap/ | Event-specific PGA/PGV grids | Earthquake-induced displacement input; use actual event shaking grid when present | P | B |
| D21 | **OpenQuake / GEM seismic products** — https://www.globalquakemodel.org/openquake | Models and hazard maps | PSHA scenarios and spectral accelerations; license/site conditions to be checked | P/C | B |
| D22 | **Active faults** — https://github.com/GEMScienceTools / national maps | Vector lines and map metadata | Distance to fault, deformation setting; poor substitute for actual acceleration | C | B |
| D23 | **OSM Geofabrik Pakistan** — https://download.geofabrik.de/asia/pakistan.html | PBF / vector GPKG | Roads, river crossings, settlements, critical POI, terrain modification proxies | P ODbL | A |
| D24 | **Google Open Buildings** — https://sites.research.google/gr/open-buildings/ | Building polygons and confidence | Exposure footprints, coverage/confidence filtering | P/C usage terms | B |
| D25 | **WorldPop / GHSL** — https://www.worldpop.org/ ; https://human-settlement.emergency.copernicus.eu/ | Population grid, ~100 m–1 km depending product | Population at risk; report reference year and day/night uncertainty | P/C | B |
| D26 | **HydroSHEDS / HydroRIVERS / HydroBASINS** — https://www.hydrosheds.org/ | Hydro network and basin polygons | Network topology, river blockage/receptor tracing | P/C | A |
| D27 | **JRC Global Surface Water** — https://global-surface-water.appspot.com/ | ~30 m multi-year occurrence/change | Persistent channels, reservoir/water presence | P | B |
| D28 | **Hansen Global Forest Change** — https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/download.html | 30 m historical forest loss | Landslide conditioning by logging/deforestation and time-varying cover | P/C | B |
| D29 | **Landsat Collection 2 Level 2** — https://earthexplorer.usgs.gov/ | 30 m, historical | Multi-decadal vegetation/change/inventory augmentation | R | B |
| D30 | **Global glacier/lake inventories** — https://www.glims.org/ ; https://www.glims.org/RGI/ | Glacier vector polygons | Periglacial slope context, glacier retreat and exposed sediment | P/C | C |
| D31 | **Global Dam Watch / HydroLAKES** — https://www.globaldamwatch.org/ ; https://www.hydrosheds.org/products/hydrolakes | Dam points, reservoir/lake vectors | Possible landslide blockage and secondary flood consequences | P/C | C |
| D32 | **Local geotechnical reports and lab tests** — national engineering studies, transport departments, universities, project clients | Site-specific borehole/test CSV, logs | Soil thickness, c', phi', unit weight, permeability, GSI/RMR, joints and failure-plane data | L | B/C |
| D33 | **Groundwater/piezometers** — PCRWR, local authorities, academic datasets | Point/well time series | Water-table elevations, pore pressures, perched aquifers; validation of infiltration model | L | B/C |
| D34 | **River stage/sediment gauges** — WAPDA, irrigation departments, PMD where available | Discharge, stage, SSC, bedload, grain sizes | Sediment rating curves, delivery, sediment budget, flood obstruction | L | B/C |
| D35 | **Landslide deformation ground instruments** — GNSS, inclinometers, extensometers, tiltmeters | Site time series | Displacement/velocity and event validation | L | C |
| D36 | **High-resolution optical imagery/field UAV** — open event imagery where permitted | 0.1–5 m variable | Failure scar, runout mapping, source-volume geometry, infrastructure details | C/L | C |
| D37 | **Observed snow / snow cover** — MODIS snow products, Sentinel-2 | 10–500 m | Snow-covered area and snowmelt-season forcing | P/R | B |
| D38 | **Soil/rock mechanics literature databases** — papers with relevant geological context | Tabulated distributions | Prior ranges for phi', c', Ks, densities, residual strengths, restitution and friction | C | B |
| D39 | **Local rainfall gauges** — PMD, university and agency networks | Minute/hour/day | Local event timing, orographic bias correction, trigger threshold validation | L | B |
| D40 | **Regional landslide data** — Geological Survey, NDMA/PDMA, transport departments, peer-reviewed mapped inventories | Point/line/polygon | Pakistan-specific onset/footprint calibration and independent validation | C/L | A |

**Important download restrictions:** SoilGrids REST point API is beta and rate-limited; use WebDAV/WCS for rasters. OpenTopography public API keys must not be embedded in a public commercial web service, and its terms distinguish commercial integrations. Open-Meteo public API is not an unrestricted commercial guarantee. Publicly readable Copernicus GLO-30 data are a **DSM**; buildings and trees can influence terrain-derived slopes. GEE, Copernicus Data Space, Earthdata and CDS require separate authenticated accounts, even where the underlying data are free. Inspect each dataset license, acknowledgments, redistribution restrictions and allowed API throughput before deployment.

### 2.1 Raw-data download plan by execution phase

**Stage 1 national offline baseline (one-time or version-based):** country/AOI boundaries; GLiM; DEM tiles; SoilGrids sand/clay/silt/bulk density/coarse fragments/soc by depth; WorldCover; HydroRIVERS/HydroBASINS; OSM; available landslide inventories. Index and retain immutable source files.

**Stage 2 historical archives (version-based):** Sentinel-2 pre/post event composites; Landsat long-term data; CHIRPS rainfall 20–40 years; event-wise IMERG rainfall; ERA5-Land moisture/temperature/snow; USGS seismic event catalog and ShakeMaps; forest loss; optional InSAR stacks.

**Stage 3 per selected AOI:** spatial subset the stored national datasets first. Fetch only missing COG windows, rainfall time windows, recent satellite tiles and event metadata. Cache by source version and AOI geometry, not only display URL.

**Stage 4 event or scenario:** assemble a snapshot forcing package. Attach measured gauge/survey inputs when available; otherwise declare uncertain parameter ranges and run ensembles.

### 2.2 Minimum truly free-data configurations

- **Tier S without field data:** D01+D04+D06+D07+D11 or D40+D14/D15+D23. Produces defensible *screening layers only* after inventory quality and cross-validation.
- **Tier T rainfall stability scenarios:** Tier S plus D16, rainfall event forcing, bounded scenario soil thickness, strength and hydraulic parameters. Do not claim verified absolute failure probability.
- **Tier E earthquake:** Tier S + D20 for actual shaking or scenario PGA plus geology/strength assumptions. Ground acceleration is essential; distance to epicentre alone is insufficient.
- **Tier R runout:** credible landslide release polygon, source thickness/volume, terrain, material-specific runout parameters and validation observations where possible. Without these, provide a clearly labelled *envelope* rather than simulated observed extent.
- **Tier D sediment:** river cross sections/channel slope/width, grain size, transport coefficients, flows. SoilGrids-derived d50 is a proxy for soils, **not a measurement of active riverbed sediment**.

---

## 3. Extraction products and derived-layer register

Every derived layer must record `source_ids`, `algorithm`, `parameters`, `source_timestamp`, `processing_version`, `units`, `crs`, `grid_resolution`, `nodata`, `confidence/uncertainty` and `quality_flags` in metadata.

| Input raw data | Derived model input | Algorithm/logic | Units / output |
|---|---|---|---|
| DEM | `elevation`, `slope_deg`, `slope_pct`, `aspect_deg` | Project to metric CRS; robust finite differences | m, degrees, %, degrees / COG |
| DEM | `plan_curvature`, `profile_curvature`, `roughness`, `TRI`, `TPI` | Metric window derivatives; scale metadata | 1/m or declared metric, unitless/m / COG |
| DEM | `local_relief`, `valley_depth`, `confinement`, `distance_ridge` | Multi-scale moving windows / valley cross sections | m, dimensionless / COG |
| DEM / streams | `flow_direction`, `accum_area`, `contributing_area` | Conditioned DEM + D8/D-infinity | direction index; m² / COG |
| DEM + hydrology | `TWI`, `SPI_stream_power`, `HAND`, `drainage_density` | TWI = ln(a/tan beta), stream-power proxies | unitless, proxy units, m, km/km² |
| DEM / ridge | `slope_length`, `LS_factor` | Flow accumulation/topographic formulas (RUSLE variant logged) | m, dimensionless / COG |
| GLiM / geology | `lithology_code`, `erodibility_rank`, `formation`, `distance_fault` | Preserve original codes and mapping table | categorical; 1–5; m / COG |
| SoilGrids profiles | `sand`, `clay`, `silt`, `bulk_density`, `cfvo`, `soc` | Scale-factor conversion and depth interpolation | %, kg/m³, %, g/kg as appropriate / COG |
| Soil texture | `soil_texture`, `Ksat_prior`, `porosity_prior` | Named USDA texture classifier, documented pedotransfer + confidence | class, m/s, fraction / COG |
| Soil / geology | `soil_depth_prior`, `root_cohesion_prior`, `c_eff_prior`, `phi_eff_prior` | **Scenario priors only** without local samples | m, Pa, Pa, degrees / COG+JSON |
| Sentinel-2 | `NDVI`, `NDMI`, `NBR`, change composites | Cloud/shadow/snow QA; seasonal comparisons | -1 to 1 / dated COG |
| WorldCover/DW | `landcover`, `veg_cover_fraction`, `cover_factor_C`, `root_zone_proxy` | Class assignment, probabilities + uncertainty | class, fraction / COG |
| Rainfall | `rain_1h`, `rain_3h`, `rain_24h`, `rain_3d`, `rain_7d`, `rain_30d`, `API` | Convert rates to depth using exact timestamps; rolling sums | mm; API mm / CF NetCDF/Zarr |
| Rainfall climatology | `rain_percentile`, `event_return_interval_proxy`, `ID_thresholds` | Event-specific distribution; threshold fitted by season | probability ranking, mm / COG/Parquet |
| ERA5-Land | `soil_moisture_0_7`, `7_28`, `28_100`, `100_289`, `snow_water_equivalent`, `t2m` | Preserve native layer thickness and physics-specific conversion | m³/m³, m SWE, K / NetCDF |
| IMERG/ERA5 | `infiltration`, `water_table_proxy`, `pore_pressure_scenario` | Calibrated hydrologic model or bounded scenarios | m/s, m, Pa / NetCDF |
| USGS event/ShakeMap | `PGA_g`, `PGV`, `MMI`, `distance_event` | Select actual event shake grid where available | g, cm/s or m/s, scale, m / COG |
| Sentinel-1 | `backscatter_change`, `coherence_change`, `LOS_velocity` | Orbit-specific, calibrated/terrain-corrected SAR; proper SLC interferometry | dB, 0–1, mm/yr / dated COG |
| Inventories | `landslide_source`, `scar`, `runout`, `confidence`, `event_date` | Digitize/merge/dedupe by event; independent QA | GeoPackage/GeoParquet |
| HydroRIVERS/DEM | `stream`, `river_width_proxy`, `distance_stream`, `blockage_candidates` | Hydrologically snapped network with downstream graph | vector and m / GPKG/COG |
| OSM/Buildings | `road`, `building`, `bridge`, `hospital`, `school`, `population` | Spatial join, positional-confidence and age checks | vectors / GPKG/GeoParquet |
| Flow + bed sediment | `shear_stress`, `Shields`, `bedload_capacity`, `sediment_budget` | Shields/Meyer-Peter–Müller within validity envelope | Pa, dimensionless, m²/s, m³ / NetCDF |

### 3.1 Standard input schema

```yaml
study_area:
  geometry: data/aois/aoi.geojson
  canonical_crs: EPSG:4326
  analysis_crs: auto_utm_or_local_equal_area
  target_resolution_m: 30
  buffer_m: 3000
  strict_aoi_statistics: true
forcing:
  rainfall: prepared/met/rain_hourly.nc
  temperature: prepared/met/t2m_hourly.nc
  soil_moisture: prepared/met/sm_hourly.nc
  earthquake_shakemap: null
soil:
  profile: prepared/soil/soil_profiles.zarr
  soil_depth: null                  # measured input or explicit scenario
  effective_cohesion: null         # Pa, measured or scenario
  friction_angle: null             # degrees, measured or scenario
  hydraulic_conductivity: null     # m/s, from tests or uncertain pedotransfer
  water_table: null                # m below ground, measured or scenario
  parameter_mode: scenario_ensemble
inventory: prepared/inventory/landslides.gpkg
terrain: prepared/terrain/dem_cog.tif
models:
  susceptibility: random_forest
  shallow_stability: infinite_slope
  rainfall_hydrology: green_ampt_scenario
  runout: empirical_envelope
  sediment: shields_capacity
quality:
  reject_nodata_fraction_above: 0.10
  provenance_required: true
  prevent_extrapolation_beyond_training_domain: true
```

**Storage contract:** COG GeoTIFF for 2D rasters and map-ready previews; CF-compliant NetCDF or Zarr for gridded time series/ensemble states; GeoPackage/GeoParquet for vectors; CSV/Parquet for observations; JSON/YAML for run metadata; STAC item/catalog optional for discoverability. Numerical rasters are not automatically resampled to a fake common 10 m precision.

---

## 4. Preprocessing end-to-end SOP

### 4.1 AOI, grid and geometry
1. Accept drawn polygon, GeoJSON, zipped Shapefile or GeoPackage; repair invalid rings; reject self-intersections that change footprint unexpectedly.
2. Reproject source AOI to EPSG:4326 for queries and to locally appropriate **metric projected CRS** for modelling. UTM zones in Pakistan differ: determine from AOI centroid and warn when AOI crosses zones.
3. Build *two* masks: strict AOI for reporting, buffered computational domain for water routing/runout and minimizing edge artifacts.
4. Freeze `grid_spec.json`: affine transform, pixel registration, cell size, width, height, EPSG, NODATA conventions; verify every required layer against it.
5. Use nearest-neighbour for categorical rasters, bilinear/cubic for continuous values **only when physically appropriate**, and conservative/time-integral preserving remapping for accumulated rainfall and fluxes.

### 4.2 Terrain/hydrology
1. Acquire DEM tile intersections; verify vertical datum, voids, stripe artifacts, elevations and mosaic seams.
2. Correct isolated outliers and missing cells, retaining a QC layer. Use a bare-earth DTM where available. At 30 m Copernicus DSM, inspect forest and settlements for slope artifacts.
3. Keep raw DEM and hydrologically conditioned DEM separately; never overwrite terrain with stream burn without metadata.
4. Derive slope/aspect with stable metric derivatives; calculate slope **degrees** for FS (convert percent `100 tan(beta)` only for compatibility with SAILAB's screening thresholds).
5. Fill only spurious pits; preserve actual closed depressions and blocking ridges where relevant. Compare conditioned drainage against HydroRIVERS and high-res imagery.
6. Calculate local relief, multi-scale curvature, TWI, contributing area, drainage density and valley confinement; treat TWI as a topographic **index**, not groundwater depth.
7. Validate georeferencing and hydrology with slope distribution, stream-to-river distance, upstream area and drainage-flow topology (no cycles).

### 4.3 Lithology/geotechnical
1. Download GLiM and clip polygons. Store original class and confidence; apply an **editable transparent** rock erodibility table (1–5 is a screening rating, not shear strength).
2. Compare with any higher-quality local geological formation, mapped faults and structural attitude; retain scale and survey year.
3. Regrid SoilGrids mean plus uncertainty/quantiles at each depth interval. Apply each variable's documented conversion factor before using percentages, densities or stocks.
4. Integrate profile depths over the soil column, respecting layer boundaries and rock/coarse fragment fractions.
5. Derive soil texture and hydrological priors with published pedotransfer functions; never derive `c'` and `phi'` from soil texture as if these were measurements.
6. For high-fidelity analysis attach lab data: effective cohesion (Pa), friction angle (degrees), total/unsaturated unit weight (N/m³), soil depth (m), permeability (m/s), suction (Pa), water table (m), residual strength; optional rock joint strike/dip.
7. Use multiple prior parameter ensembles and record where measured data constrain them. Reject engineering-design grade output when inputs remain unconstrained.

### 4.4 Rainfall and soil moisture
1. Pull hourly/half-hourly forcing in UTC, honoring native time intervals and accumulation definitions (some ERA5-Land variables are accumulated; de-accumulate correctly).
2. Drop duplicate timestamps, mark missing slots, check negative/implausible rainfall, check runoff balance.
3. Align time zones and isolate event windows with antecedent padding (default 30 days, configurable).
4. Prepare 1/3/6/12/24/48/72-hour and 7/15/30-day accumulation, seasonally normalized anomalies and antecedent precipitation index.
5. Compare satellite/reanalysis precipitation against real gauges where available; estimate orographic and event biases with held-out stations.
6. Never assume 30 m spatial rainfall variations from a 10 km forcing grid; optionally downscale with elevation covariates only if validated independently.
7. Use soil moisture as an observed/reanalysis constraint on hydrology model state, not as exact groundwater pressure at the slip surface.

### 4.5 Landslide inventory and spatial ML leakage prevention
1. Standardize hazard subtype, occurrence date/time, source footprint, runout footprint, area, point precision, mapped confidence, trigger and reference.
2. Do not mix CNN model output with ground-truth labels. Distinguish event detections, documented reported points, mapped polygons and suspected change features.
3. Map training labels to **initiation/source scar** when susceptibility is the target, not deposit footprints. Set buffers for uncertain points; exclude positional uncertainty zones from confident negatives.
4. Generate negative samples only from observationally covered areas, with spatial/temporal design; absence of a catalog entry is not proof of stability.
5. Divide by geographic blocks, basins and/or independent events BEFORE preprocessing/training/tuning to prevent near-neighbor leakage.
6. Evaluate precision/recall, PR-AUC, ROC-AUC, sensitivity, false alarms, Brier score/calibration and event-to-event skill; report geographic transfer.

### 4.6 Satellite/InSAR
1. Optical: harmonize sun/view season, QA cloud/shadow and snow; use matched pre/post periods; flag low-quality composites.
2. SAR GRD: orbit, polarization, incidence, thermal noise, terrain correction, speckle suppression; change features are **candidate** movement evidence.
3. SLC/InSAR: precise orbits, coregistration, baseline management, interferogram/coherence, topographic phase removal, unwrapping, atmospheric filtering, stable-reference selection, temporal inversion; retain LOS direction, uncertainty, decorrelation, low-coherence mask.
4. Satellite LOS velocity is not full three-dimensional displacement. Expect shadows/layover in steep Pakistan valleys and snow/glacier contamination.

### 4.7 Final acceptance gates
Reject/prevent model run when CRS mismatch, wrong units, missing geotechnical parameters, inadequate AOI DEM, inconsistent timestamps, precipitation without provenance, missing landslide inventory for supervised ML, unstable flow graph, invalid parameter value, or no runout source polygon. Show precise errors, never quietly substitute another AOI or DEM.

---

## 5. Physical quantities, meanings, equations and implementation logic

Symbols: `beta` slope angle (rad internally), `z` vertical soil depth (m), `c'` effective cohesion (Pa), `c_r` root reinforcement (Pa), `phi'` friction angle (rad), `gamma` total soil unit weight (N/m³), `gamma_w` water unit weight (N/m³), `m` ratio of saturated thickness to failure-plane depth (0–1) under simple parallel seepage assumptions, `u` pore pressure (Pa), `rho` density (kg/m³), `g=9.80665 m/s²`, `h` flow depth (m), `v` speed (m/s), `Q` discharge (m³/s), `d50` median grain size (m).

### 5.1 Terrain conditioning parameters

| Parameter | Equation / calculation | Significance | Notes |
|---|---|---|---|
| Surface gradient | `beta = atan(sqrt((dz/dx)^2+(dz/dy)^2))` | Gravity loading and flow routing | Metric coordinates required |
| Slope percent | `S_pct=100 tan(beta)` | SAILAB compatibility/screening | 35% ≠ 35 degrees |
| Topographic wetness | `TWI = ln(a / tan(beta))` | Convergent potential wetness | `a` specific contributing area (m); floors to prevent zero division |
| Relative relief | `H=max(z)-min(z)` in window | Relief potential and source height | Window scale must be specified |
| Stream power index | `SPI=a tan(beta)` or variant | Concentrated erosion propensity | This is an index; not mechanical shear power |
| Plan/profile curvature | Terrain second derivatives | Flow convergence vs downslope steepening | Sensitive to DEM noise and kernel |
| Sediment connectivity | Distance/gradient/impedance index | Delivery probability from slide to watercourse | Calibrate by basin |
| Valley confinement | Valley width / channel width (or explicit alternative) | Flow confinement, deposition and channel blockage | No universal threshold |

### 5.2 Mechanical slope stability

**Infinite slope, saturated parallel-seepage form**:

`FS = [c' + c_r + (gamma*z*cos(beta)^2 - m*gamma_w*z*cos(beta)^2)*tan(phi')] / [gamma*z*sin(beta)*cos(beta)]`

**Meaning:** ratio resisting to driving shear stress on a plane parallel to surface. `FS < 1` means the idealized stress balance favors failure. `FS ≈ 1` warrants sensitivity analysis. This formulation assumes uniform slope, translational shallow failure, specified basal pore pressure, fixed thickness and Mohr–Coulomb effective stress. The geometry/definition of `z` and unit weights MUST be consistent; use `c_r` cautiously as temporary effective reinforcement, not constant for all tree species.

General form: `FS = [c' + c_r + (sigma_n - u) tan(phi')] / tau_drive`, with `sigma_n=gamma*z*cos²(beta)`, `tau_drive=gamma*z*sin(beta)cos(beta)`. Check `u` against water head, saturation and soil thickness; negative effective stress needs treatment.

**Effective stress:** `sigma' = sigma_total - u`. Rising positive pore pressure lowers effective normal stress; can trigger failure even at unchanged slope. For unsaturated soils, optional suction stress / Fredlund–Morgenstern form:

`tau_f = c' + (sigma_n - u_a)tan(phi') + (u_a-u_w)tan(phi_b)`

where `u_a` air pressure, `u_w` water pressure and `phi_b` suction strength angle. Apply only with soil-water-retention data; do NOT extrapolate the unsaturated formula into arbitrary saturated pressures.

**Newmark yield acceleration (screening):** `a_y ≈ (FS_static-1) g sin(beta)` for a simplified block on a slope under specified conventions; verify geometry and acceleration direction in implementation. A more complete pseudostatic FS treats horizontal seismic coefficient `k_h = a_h/g` in force equilibrium. **Permanent displacement:** integrate positive block acceleration relative to the yield threshold over a calibrated acceleration time history: `v(t+dt)=max(0,v(t)+(a_drive(t)-a_y)*dt)`, `D = sum(v*dt)` with force-direction handling and possible velocity reversal. Empirical Newmark displacement regression using PGA/PGV/Arias intensity is an alternative for regional mapping; never label such displacement as actual observed ground movement.

**Circular/deep failure:** Simplified Bishop slice equilibrium:

`FS = [sum_i{(c'_i*b_i + (W_i-u_i*b_i)*tan(phi'_i))/m_i}]/[sum_i W_i sin(alpha_i)]`

`m_i = cos(alpha_i) + sin(alpha_i)tan(phi'_i)/FS`.

Solve iteratively; requires real/geologically defensible basal geometry and site data. For irregular slip surfaces use Spencer/Janbu or equivalent and report method and convergence. Avoid promising free global data provide those inputs.
 
**Rock joint kinematics:** orientation-based planar/wedge/toppling feasibility from dip direction, slope direction and friction angle. Use stereonet tests when joints are measured. Rock-mass GSI/RMR correlations are uncertain and cannot replace surveyed joint sets.

### 5.3 Rainfall infiltration / transient pore pressure

**Antecedent precipitation index:** `API_t = P_t + k*API_(t-1)` for 0<k<1; an empirical proxy, not groundwater pressure.

**Green–Ampt event infiltration:** infiltration capacity `f_c=K_s[1+(psi_f*(theta_s-theta_i))/F]`, with `F` cumulative infiltration (m), `K_s` saturated conductivity (m/s), suction head `psi_f` (m), initial/fully saturated water content `theta_i/theta_s` (fractions). Actual infiltration `min(rainfall_rate, f_c)` and ponded water/mass balance need explicit handling. Green–Ampt is a front approximation and cannot by itself determine deep groundwater response.

**Richards equation (advanced):** `∂theta(h_p)/∂t = ∇·[K(h_p)∇(h_p+z_elev)] - S`, with hydraulic head `h_p` and sink `S`, coupled to van Genuchten retention/conductivity curves. Must specify dimensionality, drainage boundaries, initial moisture/pressure, convergence controls and soil layers. Use stable established PDE libraries or a tested solver rather than an unverified custom implementation.

**Pressure-head to pore pressure:** `u = rho_w*g*h_p` for positive pressure head under consistent convention; negative suction requires unsaturated strength treatment.

**Water budget:** `P = I + R_surface + ΔStorage + ET + D_deep` over an event/basin after consistent units and time integration. Require non-negative physically meaningful terms and numerical residual checks.

**Rainfall-threshold empirical trigger:** `I = alpha*D^(-beta_r)` with intensity `I` (mm/h), duration `D` (h), regionally fitted `alpha,beta_r`. Or logistic: `logit(p_event) = b0 + b1*R24 + b2*R7 + b3*moisture + ...`, calibrated against dated landslide *events with known detection coverage*. Raw threshold exceedance is a watch trigger, not a probabilistic event without calibration.

**Snowmelt contribution:** `M_snow = DDF_snow*max(T-T0,0)` in mm/day (if calibrated); model rain-on-snow and freeze/thaw where data support it. A permafrost/degradation proxy from degree days is not a validated frost-boundary model.

### 5.4 Debris-flow initiation, mass movement and runout

**Release volume:** `V0 = ∫_source t(x,y) dA` (m³) based on source polygon and uncertain release thickness, not one invented default. `M=rho_bulk*V` for mass (kg).

**Conservation of moving thickness:** `∂h/∂t + ∂(hu)/∂x + ∂(hv)/∂y = E-D`, with erosion/entrainment `E` and deposition `D` as thickness rates (m/s) when using volume-conserving form.

**Depth-averaged momentum (schematic):** `∂(hU)/∂t + ∇·(hU⊗U + 0.5*g*h² I) = g*h*(slope_vector) - basal_resistance + exchange_momentum`; replace hydrostatic closure with an appropriate mixture pressure/solid fraction and phase interaction for debris flows. The flood-only shallow-water solver in SAILAB is **not a debris-flow rheology solver**.

**Voellmy-type basal acceleration:** along flow: `dv/dt ≈ g sin(beta) - mu*g cos(beta) - g*v²/(xi*h)` under one conventional form, with dimensioned turbulence parameter `xi` and dry/Coulomb friction `mu`. Choose and document one published convention precisely. A coarse travel/stop envelope may use an empirical reach angle: `tan(alpha_reach) = H/L`. Such mobility envelopes are screening estimates, not resolved impact depths.

**Rockfall:** ballistic free-flight `x(t)=x0+v_x0*t`, `z(t)=z0+v_z0*t-0.5*g*t²`; at impacts apply normal/tangential restitution `v_n+=-e_n*v_n-` and `v_t+=e_t*v_t-` after transforming to local tangent/normal; include rolling/sliding and fragmentation options only if calibrated. Do not use one restitution coefficient on every terrain class.

**Debris entrainment:** `dV/dt = Q_entrain-Q_deposit`, with capacity/erosion laws selected per material, depth and shear; impose finite erodible thickness and track conservation. Source morphology, runout direction, depth, velocity and deposit thickness require genuine terrain physics and material parameters.

**Landslide-dam screening:** intersect time/peak runout with river graph, estimate impacted channel width, deposit thickness and impoundment opportunity. A **possible blockage** is not a breach-hydrograph prediction. Secondary flood simulation belongs to the hydrodynamic engine after a separately defined breach/dam-release scenario.

### 5.5 Erosion and sediment physics

**Hillslope annual sheet/rill erosion (RUSLE):** `A=R*K*LS*C*P`, where `A` is estimated average erosion (t/ha/year, conditional on compatible factor units), `R` rainfall erosivity, `K` erodibility, `LS` topographic length/steepness, `C` cover management and `P` supporting practice. Not a prediction of earthquake landslide sediment or an individual debris flow. `P=1` may represent *unknown conservation practice*, and must be labelled an assumption.

**Bed shear from flow depth and slope:** `tau_b ≈ rho_w*g*R_h*S_f` (Pa) under approximately uniform flow, hydraulic radius `R_h` (m), energy slope `S_f` (dimensionless). SAILAB's existing flood postprocess uses Manning velocity-based `tau_b = rho_w*g*n²*V²/h^(1/3)`; this is a model-derived approximation, only defined for valid wet cells and consistent friction conventions.

**Shields stress:** `theta = tau_b / [(rho_s-rho_w)*g*d50]`; threshold often screened with `theta_c≈0.047` for noncohesive sediment, but critical stress varies with grain size, hiding/exposure, slope and cohesive bed material.

**Meyer-Peter–Müller bedload capacity (one version):** `q_b = 8*max(theta-theta_c,0)^(3/2)*sqrt((s-1)*g*d50^3)` where `s=rho_s/rho_w`; `q_b` volumetric bedload **per unit channel width** (m²/s), not total sediment volume. Total `Q_b = q_b*B` (m³/s) for active width `B`. This is a noncohesive-bed formula; not automatically applicable to muddy debris flows, mixed cohesive banks or boulder pulses.

**Suspended sediment:** `Q_s = Q*C_s` (kg/s if `C_s` in kg/m³ and `Q` in m³/s); observed sediment rating relation `C_s=a*Q^b` is site-calibrated and vulnerable to hysteresis. Optional advection–diffusion–settling equation `∂(hC)/∂t+∇·(hUC)=∇·(hD∇C)+source-sink` only if coupled correctly to hydraulics.

**Sediment budget:** `ΔS = inputs_from_slides + hillslope_erosion + bank_erosion - exported_sediment - deposition` in mass units consistently. No sediment DEM-feedback in basic tier. Dynamic bed update requires Exner: `(1-lambda_p)*∂z_b/∂t + ∇·q_s = 0`, with bed porosity `lambda_p` and compatible volumetric transport; use coupling and stability tests before permitting morphology updates.

**Particle/grain parameter caveat:** SoilGrids percentages of sand/silt/clay permit a *soil texture* estimate but do not uniquely identify riverbed `d50`, cohesive erosion thresholds or landslide debris boulder fraction. Use measured bed sampling or show scenario bands.

### 5.6 Exposure, consequences and uncertainty

**Exposure:** `N_exposed = sum(population_i * overlap_fraction_i)` or count intersected roads/buildings/facilities; include inventory completeness, reference years and grid-resolution limits. **Impact intensity** = peak deposit depth (m), dynamic pressure `p_dyn≈rho_mix*v²` (Pa, convention factor to be documented), arrival time, flow direction, impact energy (rockfall) and blockage potential. Convert to damage only with hazard-specific fragility functions calibrated for structure types.

**Risk over events:** `EAL = ∫ L(p) dp` only with a credible scenario frequency/probability model and comparable loss estimates. Scenarios of assumed size with no frequency cannot produce statistically grounded EAL/AAL. Monte Carlo for uncertain strength and source volume: present 5/50/95th percentile extent/depth/FS, median, input variance contributions and calibration status.

---

## 6. Complete model catalogue and tier-selection rules

| Model ID | Model | Inputs | Outputs | Maturity/when allowed |
|---|---|---|---|---|
| M01 | GLiM + slope legacy SAILAB score | Slope %, lithology 1–5 | 4-category regional screening | Fast fallback, not a physical probability |
| M02 | Inventory-driven logistic GAM / GLM | Factors + verified historical events | Relative susceptibility, calibration | Recommended interpretable statistical baseline |
| M03 | Random forest | Terrain, geology, soil, cover, triggers + inventory | Relative score, importance, uncertainty | Use blocked/event holdouts |
| M04 | XGBoost / LightGBM | As above | Relative score, ensemble | Strong structured-tabular option, spatial CV mandatory |
| M05 | CNN/U-Net scar segmentation | Multi-temporal imagery and polygon labels | Candidate scars and uncertainty | Observation/detection, not mechanically predicted failures |
| M06 | LHASA global benchmark | NASA LHASA products and compatible triggers | Global daily situational benchmark | Compare, do not train/test on LHASA predictions as truth |
| M07 | Rainfall threshold (I–D/API) | Gauge/IMERG, dated inventory | Watch categories + calibrated detection metrics | Empirical trigger warning only |
| M08 | Green–Ampt + infinite slope | Rain, hydraulic priors, depth/strength scenarios | Transient FS at location/grid | Open-data scenario, uncertainty emphasized |
| M09 | Richards + infinite slope | Soil hydraulic curve, vertical profile, BC/IC | Hourly pore pressure and FS | Local high fidelity with data and solver verification |
| M10 | TRIGRS-style transient stability | DEM slope, soil depth, Ksat, diffusivity, rainfall, groundwater | Time-varying FS and potential source patches | Requires strong geotechnical assumptions and tests |
| M11 | SINMAP-style wetness/stability index | Slope, drainage area, parameter ranges | Terrain-stability index | Screening, not observed failure date |
| M12 | Bishop/Janbu/Spencer LEM | Boreholes, water table, slip surface, strengths | FS by candidate surface | Site-specific, no global automatic promise |
| M13 | Pseudostatic / Newmark | Ground motion, strengths, slopes | Yield acceleration, displacement | Screening after ground-motion quality checks |
| M14 | Rockfall trajectory | Rock-source zones, local DTM, restitution | Reach probability, impact energy, trajectories | Site resolution/highly calibrated |
| M15 | Empirical runout/angle-of-reach | Source, H, empirical L/H distributions | Conservative envelope | Coarse regional screening |
| M16 | r.avaflow (external solver) | DEM, release geometry/volume, friction/rheology, erosion | Time-series deposit depth/velocity/pressure | Advanced debris-flow scenarios; integration/license/version check |
| M17 | RUSLE | Erosivity, soil K, LS, cover and practice | Annual potential sheet/rill erosion | Long-term screening, not event debris flow |
| M18 | Shields + MPM | River flow depth/velocity, n, d50, width | Transport-capacity indicators | Noncohesive channel screening, SAILAB-compatible |
| M19 | Suspended sediment rating/advective transport | Q, measured SSC, river routing | Sediment loads and timing | Calibrate at gauges; no default national rating curve |
| M20 | River blockage and breach coupling | Runout outputs, channels, valley terrain, breach scenarios | Candidate dams + optional flood impact | Send credible breach hydrograph to flood model |
| M21 | Exposure / fragility / loss | Impact footprints/intensity, asset inventories, fragility | Affected assets / scenario losses | Do not use flood-only vulnerability curves |
| M22 | Watch/nowcast orchestration | Forecast rainfall, moisture, instrument alerts | Alert tiers, evidence status, model provenance | Event watch, not automatic definitive evacuation order |

**Processing logic:** if user selects `rapid`, run M01+M02–M04 where inventory adequate, otherwise M01 alone, explicitly low confidence. If `rainfall stability`, require depth+strength assumptions, then M08 or M09/M10 depending validation. If `earthquake`, require shakemap and mechanical inputs, then M13. If `runout`, source polygon+volume and materials required; M15 for provisional, M16 only after validation. If `sediment`, M17 independent of M18; M18 requires hydraulic outputs; sediment supply from slides must be explicitly linked to source quantities.

### 6.1 Spatial ML training standards
- Inventory negatives collected only in areas/times with adequate visibility.
- Separate `training`, `validation`, `spatial_holdout`, `event_holdout` and `independent_region_test` sets.
- Handle spatial imbalance and rare positives; use PR-AUC in addition to ROC-AUC.
- Fit transformations and imputation on training folds only; preserve missingness flags.
- Report calibrated reliability curve, confusion matrix under declared threshold, precision/recall, transfer scores and class prevalence.
- Map out-of-distribution areas and suppress confident results there.
- Do not fit ML susceptibility directly to M01's heuristic map or global LHASA output and then claim independent predictive skill.

### 6.2 Physics checks
- Infinite-slope monotonicity: holding all else constant, increasing pore pressure must not increase FS; increasing cohesion generally must not decrease FS.
- Flat slope (`beta≈0`) needs special nonfailure handling; zero-depth soil or zero denominator invalid, not FS=0.
- Pore pressure bounded by declared groundwater scenario; cap wetness physically when saturation maximum reached.
- Richards residual convergence/time step, infiltration conservation and no negative water content.
- Newmark zero/excess shaking: no yield exceedance means zero sliding displacement; control sign and time integration.
- Runout mass conservation: `initial volume + entrained - deposited - exported - airborne/residual = 0` within solver tolerance.
- Bedload: `theta <= theta_c` yields zero capacity; nonnegative Q and transport; NODATA/strided flood frames refused.

---

## 7. Web application: navigation, workflows and API

### 7.1 User workflows / left panel

1. **AOI & base data:** Draw/upload/select tehsil or river basin; map and `Data Status` immediately show DEM, geology, soil, land cover, inventory and rainfall coverage; `Fetch` buttons only for missing sources.
2. **Explore layers:** DEM, hillshade, slope, lithology, vegetation, rainfall, seismic intensity, fault distance, inventory, roads/assets. Toggle all from a persistent layer panel; cached results never silently recalculated.
3. **Susceptibility:** Choose legacy screening, logistic, RF/boosting; inspect factor importance, inventory completeness, held-out skill and limitations.
4. **Rainfall-triggered stability:** Pick historical event/live forecast/upload gauge; choose measured or scenario parameter sets; get pore pressure and FS timeline.
5. **Earthquake hazards:** Choose dated USGS event or upload ShakeMap; run pseudostatic/Newmark and view displacement envelope.
6. **Runout & debris flow:** Pick/source slide polygon; preview release thickness/volume range; run empirical or external multiphase engine; inspect route animation.
7. **Sediment & river blockage:** Run RUSLE screening or hydraulic shear/MPM after compatible flow model; map loads, delivery, blockage candidates.
8. **Exposure & mitigation:** Overlay buildings, roads, bridge crossings and people; specify drainage, retaining stabilization, reforestation or road protections; re-run same event with altered validated parameters.
9. **Monitoring:** Define region/threshold/watch frequency; alerts show observed/forecast/estimated flags and data age.
10. **Export & audit:** Maps, CSV, rasters, vectors, report, JSON, run manifest and uncertainty tables.

### 7.2 Essential REST endpoints

`POST /api/aois` — AOI validate; `GET /api/data/status?aoid=`; `POST /api/data/fetch`; `GET /api/layers?aoid=`; `POST /api/derive`; `POST /api/models/susceptibility`; `POST /api/models/stability`; `POST /api/models/seismic`; `POST /api/models/runout`; `POST /api/models/sediment`; `POST /api/scenarios/compare`; `POST /api/monitor/watch`; `GET /api/jobs/{id}`; `GET /api/results/{id}/manifest`; `GET /api/results/{id}/tiles/{z}/{x}/{y}`; `GET /api/results/{id}/download`.

Use queued jobs with progress stage, cancellation and idempotent cache key. Authentication and AOI quota protect paid hosting capacity; open/free source data **do not make compute/storage/bandwidth free**. Keep API keys server-side. Use role-based auth for user-uploaded proprietary geotechnical files.

### 7.3 Technology stack

- **Frontend:** React or Vue + MapLibre GL JS (open-source map renderer) + drawing tools, legend, synchronized layer toggles, charts and 3D terrain; license-check basemap tiles separately.
- **Backend:** FastAPI (recommended) or Flask; Pydantic validation; GeoPandas/Shapely/Rasterio/GDAL, xarray/Dask; OGR/pyogrio.
- **Spatial storage:** PostGIS for metadata and vector indexes, Parquet/GeoParquet for bulk points; immutable raster/object-store COG/NetCDF/Zarr; PMTiles/vector tiles for presentation.
- **Jobs:** Celery/RQ + Redis, resource quotas and retry with exponential backoff; workers split into data retrieval, raster processing, ML inference, physical solver and report generation.
- **Models:** scikit-learn, XGBoost/LightGBM where licenses permit; SciPy ODE/PDE; external verified runout engines via command-line adapters in isolated containers.
- **3D:** MapLibre terrain visualization with tile source. Browser animations use reduced visual mesh but analysis stays full resolution.
- **Ops:** Docker Compose for prototype; persistent source registry, structured logs, metrics, result checksums, tests and backup strategy.

### 7.4 SAILAB interoperability

- Reuse SAILAB's AOI masks, versioned data registry, existing GLiM lithology, SoilGrids, valley metrics, building/road source layers, flood output *only when compatible*.
- Read SAILAB `depth(t), velocity(t), Manning_n` to compute channel sediment capacity; require **unstrided full-resolution** depth/velocity, consistent CRS, cell alignment and valid wet masks.
- Pass physically defined landslide-dam breach hydrograph/runoff inputs to SAILAB flood Tier 3 as a distinct scenario; SAILAB cannot calculate landslide rheology from its water solver.
- Never transfer SAILAB's flood-derived building depth–damage curves to impact from rockfall/debris flow.
- Maintain independent model/caching signatures; avoid embedding huge time stacks into HTML, serve compressed tiled frame data.

---

## 8. Every requested class of model output

### 8.1 Terrain, geomorphology and geological outputs
- DEM, hillshade, slope angle/percent, aspect, plan/profile curvature, TRI, TPI, roughness, local relief, elevation bands, HAND, TWI, flow direction, accumulation, drainage density, channel gradient, stream-power index, valley depth/confinement, lithology and erodibility, distance to faults/streams/roads, land cover, NDVI/NDMI and recent vegetation change.

### 8.2 Hazard and timing outputs
- Historical landslide inventory overlay and source polygon quality.
- Relative susceptibility score, four/five documented classification bins and calibrated probability only if enough reliable labels and tested calibration exist.
- Soil depth scenario, soil texture/hydraulic priors, hydraulic parameter uncertainty, rainfall accumulation/API and moisture anomaly layers.
- Infiltration rate, cumulative infiltration, saturation/pressure head, time-dependent pore pressure, soil saturation state, FS raster, FS minimum and time of minimum, candidate unstable source areas, sensitivity to soil thickness/friction/cohesion/groundwater.
- Earthquake PGA/PGV/shaking input, pseudostatic FS, yield acceleration, Newmark permanent-displacement proxy, terrain quality / liquefaction not covered flag.
- Runout source volume, time-to-arrival, peak flow depth, peak velocity, dynamic impact pressure, maximum reach, envelope probability conditional on priors, travel paths, deposition thickness/volume and erosion/entrainment totals.
- Rockfall source polygons, trajectories, likely reach, impact energy and frequency conditional on calibrated release probability.
- Active/possible landslide dam sites, estimated obstruction dimensions and impacted downstream river/roads (screening versus breach simulation clearly distinguished).

### 8.3 Sediment and watershed outputs
- RUSLE annual hillslope soil erosion, erosion hotspots, subbasin source area, sediment connectivity index, delivery routes, flood-derived bed shear, Shields exceedance, bedload capacity (m²/s), total channel bedload if channel width supplied (m³/s), SSC where observed or calibrated, sediment volume/mass supplied by landslides, deposition map, subbasin and outlet load, uncertainty and data coverage.

### 8.4 Exposure, decision and operational outputs
- Affected buildings/roads/bridges/settlements/schools/hospitals and road isolation; population exposed with timestamp and data age.
- Scenario-specific physical damage indicators; monetary loss **only if defensible fragility, unit costs and exposure are available**; explicit range rather than false precision.
- Baseline versus mitigation and rainfall/seismic scenario differences at identical grid and inventory snapshot; affected assets, reach/volume changes, unintended downstream effects and costs if supplied.
- Historical event reconstruction, forecast conditional watch map, uncertainty envelope, alert threshold crossing and sensor source metadata.
- Calibration/validation dashboard, reliability plots, spatial confusion maps, change-detection false alarms, parameter sensitivity, event holdout results and data age/coverage.

### 8.5 Download formats

| Deliverable | Format | Content |
|---|---|---|
| Analysis rasters | Cloud-Optimized GeoTIFF `.tif` | 1-band or annotated multiband layers with units/NoData |
| Time-evolving/ensemble grids | CF NetCDF `.nc` / Zarr `.zarr` | `{time,y,x}`, optional `{member}` and variable attrs |
| Slide scars and runout | GeoPackage `.gpkg` / GeoParquet | Geometry, event/model IDs, date, class, confidence |
| Sample/sensor series | `.csv` / `.parquet` | Timestamps UTC, coordinates, unit-labelled variables |
| Project state / reproduction | `.yaml`, `.json`, STAC | Inputs, hashes, all model parameters, software version, license |
| Map and charts | `.png`, `.svg`, `.pdf` | AOI, scale, north, legend, CRS, time, method, uncertainty |
| Formal report | `.html`, `.pdf` | Executive + technical methods, warnings, results, provenance |
| 3D playback | Browser tile frames, optional `.mp4` | Animated moving material with timing, depth, speed |
| Complete run bundle | `.zip` | Manifest + selected rasters/vectors/tables/report and README |

---

## 9. Validation, uncertainty and acceptance criteria

### 9.1 Observation hierarchy

1. **Highest confidence:** event-dated source/scar polygons, survey/GNSS/borehole/piezometer, calibrated gauges and measured runout/deposit thickness.
2. **Intermediate:** cloud-screened high-resolution independent optical maps, precise seismic ShakeMaps, multi-temporal InSAR with adequate coherence and uncertainty assessment.
3. **Reference but not ground truth:** published inventories with positional uncertainty, 30 m global land products, GloFAS, NASA LHASA outputs, reanalysis soil moisture/rainfall.
4. **Scenarios, not observations:** worldwide friction-angle lookup, inferred soil depth, universal groundwater level, assumed boulder fraction/runout friction.

### 9.2 Required tests per model

| Component | Validation | Metrics | Release guard |
|---|---|---|---|
| ML susceptibility | Spatial-block + out-of-event holdout | PR-AUC, ROC-AUC, recall/precision, Brier, reliability | No claimed national predictive skill from random pixel holdout only |
| Rainfall threshold | Independent event and non-event dates | POD, FAR, critical-success index, lead time, event rate | Do not claim calibrated probability absent detection coverage |
| Infiltration / pore pressure | Measured soil moisture/water table/field suction | MAE, bias, Nash–Sutcliffe where appropriate, balance residual | Flag parameter/BC uncertainty |
| Infinite-slope FS | Laboratory/field known unstable and stable sites | ROC/PR, FS distribution and sensitivity | No site-specific certification without ground investigation |
| Newmark | Documented earthquake sliding extents/displacement | Bias, spatial event detection, distribution | No claim of measured deformation |
| Runout | Independently mapped reach/deposit/flow marks | CSI/IoU, runout length error, depth RMSE, volume balance | Do not silently tune and validate on same event |
| Sediment | Observed SSC/bedload/station flow where available | Bias, NSE/KGE as appropriate, sediment budget closure | Qualitative 'capacity' only where no sediment observations |
| Exposure | Sample building/road positions and mapped settlement checks | Geometric completeness, false intersects | Unmapped assets not counted as no risk |

### 9.3 Uncertainty reporting

- **Source uncertainty:** DEM bias, 250 m soil data represented at 30 m, sparse inventories, old land-cover dates, rainfall gauge/reanalysis biases.
- **Parameter uncertainty:** friction/cohesion/depth, hydraulic conductivity, antecedent moisture, source volume, bed grain size, rheology and impact fragility.
- **Structural uncertainty:** infinite-slope vs curved slip surface, Richards vs Green–Ampt, MPM vs actual sediment mixture, regional to local transfer.
- **Sampling:** Monte Carlo/Sobol or Latin hypercube ensembles, correlated prior distributions where geological parameters depend on soil unit.
- **Quality output:** `data_quality`, `model_validation_status`, `out_of_domain`, `parameter_mode`, `uncertainty_bounds`, `not_for_engineering_design` flag.
- **Claims:** No public dataset guarantees every physically relevant parameter can be accurately estimated for all hillslopes; the system must give explicit model-specific limitations.

### 9.4 Verification gate before live alerting

Require at least one independently held-out event dataset in the target region, run a retrospective seasonal hindcast, audit false alarms, calibrate class thresholds, define alerts as decision support, document a human escalation path, and demonstrate fallback when weather/satellite feeds fail. An early warning pilot requires real communications, agency procedures and field confirmation.

---

## 10. Build sequence: feasible engineering roadmap

| Release | Modules | Data | Completion criterion |
|---|---|---|---|
| Phase 0 — foundations | AOI/upload, versioned registry, DEM/climate/soil/GLiM/OSM fetch, COG map | D01–D07,D11,D14–D16,D23 | AOI checks, cache-hit parity, reproducible layers |
| Phase 1 — usable MVP | M01, interpretable ML M02/M03, inventory + map, export/report | Baseline sources + dated local inventory | Spatial/event holdout metrics and no fake probabilities |
| Phase 2 — transient triggers | M07/M08, moisture/rain time series, FS ensembles, first watch | ERA5/IMERG and scenario/field geotechnics | Physics tests + offline hindcast and warning calibration |
| Phase 3 — seismic and runout | M13/M15, then optional M14/M16 | ShakeMap, source polygons, measured volume/reach where possible | Validated runout/hazard case studies and volume checks |
| Phase 4 — sediment integration | M17/M18/M19/M20, linked flood coupling | Channel/flow/bed data and source sediment | Mass/width checks, observed comparison when possible |
| Phase 5 — operational decisions | M21/M22, alert QA, comparative interventions, audit | Fragility and assets, sensors | Independent regional tests, watch governance, performance monitoring |

**Recommended starting pilot:** select two contrasting Pakistani basins with well-documented landslide inventories (one steep rainfall-dominated valley, one road-cut/settlement corridor), reconstruct several rainfall and landslide events, and reserve whole events and a geographically separate basin for untouched validation. Do not start with a nationwide 10 m simulation.

---

## 11. Engineering repository and repeatable pipeline

```text
landslide-platform/
  docs/
    LANDSLIDE_PLATFORM_FULL_METHODOLOGY.md
    data_registry.yaml
    model_registry.yaml
    validation_protocol.md
    licensing_register.csv
  backend/
    api/                  # AOI, layers, fetch, jobs, model, monitor, report
    data/
      fetchers/           # STAC/S3/Earthdata/CDS/Geofabrik/etc.
      preprocessing/      # DEM, rainfall, soil, landcover, inventory
      registry.py
    models/
      susceptibility/
      stability/
      infiltration/
      seismic/
      runout/
      sediment/
      exposure/
      monitoring/
    workers/
    tests/
  frontend/
    src/components/      # AOI, dataset status, toggles, scenarios, timeline
  datasets/
    raw/                  # immutable; provider/version/date
    prepared/             # CRS/grid/versioned datasets
    indices/              # spatiotemporal source catalogs
    user_private/         # restricted field files
  runs/
    <run_id>/
      manifest.json
      inputs.yaml
      quality_report.json
      rasters/
      timeseries/
      vectors/
      metrics/
      report/
  docker-compose.yml
  pyproject.toml
```

### 11.1 Run manifest contract

```json
{
  "run_id": "<uuid>",
  "model": "infinite_slope_green_ampt",
  "model_version": "1.0.0",
  "source_data": [{"id": "copernicus_dem_glo30", "version": "2026_snapshot", "sha256": "<hash>"}],
  "aoi_sha256": "<geometry_hash>",
  "grid": {"crs": "EPSG:32643", "resolution_m": 30},
  "time_start_utc": "2025-07-01T00:00:00Z",
  "time_end_utc": "2025-07-03T00:00:00Z",
  "parameter_mode": "scenario_ensemble",
  "calibration_status": "not_calibrated",
  "validation_status": "screening_only",
  "warnings": ["soil strength not measured", "rainfall spatial scale much coarser than DEM"],
  "results": ["rasters/minimum_fs.tif", "timeseries/fs.nc", "quality_report.json"]
}
```

### 11.2 Important data-integrity / code tests

- Identical AOI + input versions + parameter set ⇒ identical artifact hash or numerically documented tolerated variance.
- All raster math respects valid-cell mask and strict AOI stats; no NODATA encoded as extreme risk.
- Physical units tested: slope degree versus percent, km² to m², mm/h to m/s, kPa to Pa, hourly accumulation to depth, sediment per-width to total transport, soil bulk density scale factors.
- Cropping/resampling preserves physical rainfall totals and hydrologic catchment-area consistency within declared tolerance.
- Boundary checks: rainy event with zero Ksat cannot absorb infinite water; dry soils do not produce positive pore pressure without supply/boundary water.
- No attempt to run user-uploaded arbitrary code. User geotechnical files stored access-controlled.
- Periodic source freshness, provenance and license audit. A blocked fetch returns explicit unavailable state and an authorized alternative rather than fabricated data.

---

## 12. Authoritative links and source notes

**Official dataset and software landing pages:**
- Copernicus DEM AWS: https://registry.opendata.aws/copernicus-dem/
- SoilGrids WCS/WebDAV/docs: https://docs.isric.org/globaldata/soilgrids/ ; https://files.isric.org/soilgrids/latest/data/
- NASA COOLR: https://gpm.nasa.gov/applications/landslides/coolr
- NASA LHASA model/software: https://github.com/nasa/LHASA
- NASA Global Landslide Nowcast: https://data.nasa.gov/dataset/global-landslide-nowcast-from-lhasa-l4-1-day-1-km-x-1-km-version-2-0-0-global-landslide-no-0f8e8
- ESA WorldCover: https://esa-worldcover.org/en/data-access
- ERA5-Land: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land
- NASA IMERG: https://gpm.nasa.gov/data/imerg
- Copernicus Sentinel: https://dataspace.copernicus.eu/
- OpenTopography terms/API: https://www.opentopography.org/developers
- OSM Geofabrik Pakistan: https://download.geofabrik.de/asia/pakistan.html
- USGS earthquake API: https://earthquake.usgs.gov/fdsnws/event/1/
- USGS ShakeMap: https://earthquake.usgs.gov/data/shakemap/
- r.avaflow: https://www.avaflow.org/

**Scientific methods to consult for implementing and checking formula versions:** Montgomery & Dietrich (1994, shallow landslide/topography); Iverson (2000, landslide triggering by rain infiltration); Baum, Savage & Godt (2002, TRIGRS transient rainfall infiltration); van Genuchten (1980, unsaturated retention); Fredlund, Morgenstern & Widger (1978, unsaturated shear strength); Newmark (1965, earthquake slope displacements); Jibson (2007, regression models for Newmark); Meyer-Peter & Müller (1948, bedload); Renard et al. (1997, RUSLE); Stanley & Kirschbaum (2017), Kirschbaum & Stanley (2018), Stanley et al. (LHASA references); Mergili et al. (r.avaflow multiphase flow). Consult the exact published formulation, domain of validity and implementation license before production use.

---

## 13. Final implementation acceptance checklist

- [ ] Dataset license and commercial integration permission recorded for every downloader and public map layer.
- [ ] For every raw source: stable ID, version, provider URL, acquired date, extent, native CRS, native resolution, units, uncertainty, hash.
- [ ] For every model variable: physical meaning, source variable, units, preprocessing function, allowed range, default = explicit scenario or measured value.
- [ ] Reference SAILAB geomorphology outputs reproduced as a separate legacy baseline, not conflated with new hazard prediction.
- [ ] Historical source-scar inventories separated from runout deposits and historical event windows.
- [ ] Susceptibility statistically validated by spatial blocks and independent dates/regions; probability calibration only when supported.
- [ ] Slope stability checks units, measured-versus-inferred soils, transient pressure physics, exact FS equation and uncertainties.
- [ ] Seismic model uses actual/specified ground-motion intensity and a defensible yield acceleration.
- [ ] Runout requires release geometry and uncertain initial volume; outputs mass balance, impact and spatial skill.
- [ ] Sediment model distinguishes gross hillslope erosion, channel transport capacity, measured SSC and actual deliveries.
- [ ] Missing data never silently fill with plausible-looking physical values.
- [ ] All output rasters downloadable with CRS, source lineage, unit, timestamps and QC indicators.
- [ ] Alerting is clearly conditional, human-reviewable, hindcast validated and not a replacement for national public-safety authorities.

**Bottom line:** A freely sourced web platform can realistically deliver national-scale terrain/lithology/ML screening and conditional rainfall watch products. Mechanistic FS, deep-landslide stability, precise runout intensity, sediment loading and engineering-grade risk depend on local physical parameter constraints and independent event calibration. Exposing that distinction in the website is part of the scientific methodology, not an optional disclaimer.
