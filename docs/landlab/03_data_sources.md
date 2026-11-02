# Data Sources

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

After cleaning, the inventory has {{inventory_summary.json:records|0}} unique events. Positions are reports: the stated accuracy ranges from 0.5 km to 50 km, and for many records it is 25 km or worse. Dates are kept at the precision they were given: a bare year is never turned into 1 January. There are no deposit polygons, no measured volumes (one record), no soil measurements and no depth of failure. This caps what any validation can show (Ch. {{ch:validation_protocol}}).

## 3.2 Known coverage gaps

- The ML susceptibility layer ends near 31 N; elsewhere it is NODATA and is never read as "low".
- The 05_risk population layer follows the same extent.
- ERA5-Land ends on 20 May 2026.


## 3.4 Borehole, soil and groundwater data added later (`Datadownload/`)

Five collections were supplied to find slip-surface depth, regolith and soil strength. `scripts/check_new_data.py` (`docs/validation/new_data_checks.json`) tested what each can do:

| Collection | Content | Where | Use for landslides |
|---|---|---|---|
| CSIRO Indus borelog database | {{new_data_checks.json:B_borelogs_vs_bedrock_map.holes|0}} lithological logs, median depth {{new_data_checks.json:B_borelogs_vs_bedrock_map.median_hole_depth_m|0}} m | Indus plain only: latitude {{new_data_checks.json:B_borelogs_vs_bedrock_map.lat_range.0|1}} to {{new_data_checks.json:B_borelogs_vs_bedrock_map.lat_range.1|1}}, {{new_data_checks.json:B_borelogs_vs_bedrock_map.holes_north_of_33N|0}} holes north of 33 degrees | None: alluvium, no slopes. It does show that the SoilGrids depth-to-bedrock map is wrong on the plain: {{new_data_checks.json:B_borelogs_vs_bedrock_map.share_holes_deeper_than_mapped_bedrock|pct}} of the holes are deeper than the bedrock the map gives (median hole {{new_data_checks.json:B_borelogs_vs_bedrock_map.median_hole_depth_m|0}} m against a mapped {{new_data_checks.json:B_borelogs_vs_bedrock_map.median_mapped_depth_to_bedrock_m|0}} m), because the holes rarely reach rock. The map is used only as a cap on slope soil depth (off by default), where the plain is irrelevant. |
| BGS groundwater levels | {{new_data_checks.json:C_groundwater.readings|0}} readings from {{new_data_checks.json:C_groundwater.stations_in_pakistan|0}} stations, 1884 to 2020 | Punjab and Sindh plains; {{new_data_checks.json:C_groundwater.north_of_33N_stations|0}} stations north of 33 degrees | Depth to the water table on the plain: median {{new_data_checks.json:C_groundwater.depth_to_water_m_quantiles_since_1990.p50|1}} m, 10th to 90th percentile {{new_data_checks.json:C_groundwater.depth_to_water_m_quantiles_since_1990.p10|1}} to {{new_data_checks.json:C_groundwater.depth_to_water_m_quantiles_since_1990.p90|1}} m since 1990, and {{new_data_checks.json:C_groundwater.share_between_2_and_10m|pct}} of readings between 2 and 10 m, the water-table prior range of the model. That supports the order of magnitude of the prior, for flat ground. Every reading is the 1 October value, so the seasonal rise (and therefore the antecedent water-table response) cannot be measured. |
| WoSIS soil profiles | {{new_data_checks.json:A_wosis_vs_soilgrids.profiles_in_pakistan|0}} profiles, {{new_data_checks.json:A_wosis_vs_soilgrids.north_of_31_5N|0}} north of 31.5 degrees | Sparse, mostly 1984 US survey and old FAO/ISRIC profiles | Measured clay and sand agree with the SoilGrids values the ground model reads: clay bias {{new_data_checks.json:A_wosis_vs_soilgrids.clay.bias_pct_points|1}} percentage points, mean error {{new_data_checks.json:A_wosis_vs_soilgrids.clay.mae_pct_points|1}}; sand bias {{new_data_checks.json:A_wosis_vs_soilgrids.sand.bias_pct_points|1}}, mean error {{new_data_checks.json:A_wosis_vs_soilgrids.sand.mae_pct_points|1}} (69 profiles). **This is not an independent test**: SoilGrids is trained on WoSIS. No shear strength, cohesion or friction is in the collection. |
| WoSIS profile depths | described depth of the northern profiles | 48 profiles | They are described to the sampling depth (median {{new_data_checks.json:D_wosis_profile_depth.median_described_depth_cm|0}} cm), not to bedrock. Five reach a rock or Cr contact, at {{new_data_checks.json:D_wosis_profile_depth.contact_depths_cm.0|0}} to {{new_data_checks.json:D_wosis_profile_depth.contact_depths_cm.4|0}} cm: weak support for a soil depth of 1.3 to 1.8 m on the Potwar and Hazara foothills, against the fitted 2.4 m. |
| USGS Indus borehole logs, depth-to-bedrock raster | 16 deep holes in the eastern Indus plain; the raster is the same SoilGrids 250 m map already used | Plain / already held | Nothing new. |

**Is it enough?** No, for the purpose it was gathered for. The collections are almost entirely on the flat Indus plain, where landslides do not happen. There is no borehole, geophysical profile, shear-strength test or regolith thickness on a slope in the mountains, which is what a mapped slip surface, a two-layer soil or a calibrated cohesion would need. What it does is confirm three assumptions on the plain or at sparse points (water-table depth range, SoilGrids texture, and a 1 to 2 m soil depth in the foothills) and show one input to distrust (the SoilGrids bedrock depth on the plain). No parameter of the model was changed by it. To close the gap the model needs boreholes or geophysical (seismic refraction, resistivity) lines on slopes in the Hindu Kush, Karakoram and Himalaya foothills, ideally with shear tests.


## 3.5 Census (Pakistan Bureau of Statistics, 2023)

`Datadownload`-era folder `PBS DATA district` holds district tables of population, density, household size and housing type (permanent, semi-permanent, mud or temporary). The population and housing-type tables and the district boundaries are copied to `datasets/external/pbs/` and used for construction-class fragility, household size and the population fallback (Ch. {{ch:exposure_damage}}). Coverage: {{population_vs_pbs.json:districts_with_census|0}} districts; **Gilgit-Baltistan and Azad Kashmir are absent**, so the highest-landslide districts fall back to national means.

**Population raster against the census.** For the {{population_vs_pbs.json:districts_checked|0}} census districts that lie wholly inside the raster's footprint, the median ratio of the WorldPop 2025 total to the 2023 census total is {{population_vs_pbs.json:ratio_median|2}} (25th to 75th percentile {{population_vs_pbs.json:ratio_p25_p75.0|2}} to {{population_vs_pbs.json:ratio_p25_p75.1|2}}), about the two years of growth, and {{population_vs_pbs.json:share_within_20pct|pct}} of the districts are within 20%. The outliers are census-row or boundary problems rather than raster errors: the census table gives Mirpur 15,610 people, Muzaffarabad 174,708 and Peshawar 2.19 million (district totals in the raster are 548,000, 787,000 and 5.2 million), which are tehsil-sized or pre-reorganisation figures. The raster total over the checked districts is {{population_vs_pbs.json:ratio_total|2}} times the census total, driven by those rows.

**Building heights.** No usable source was found. Google's Open Buildings 2.5D height layer is on Earth Engine, whose project on this server denies access (a missing service-usage role); Overture Maps has a height for only 30 of 24,216 Gilgit buildings and a floor count for 29. Heights stay at the assumed 6 m (two storeys), and the loss chapter says so (Ch. {{ch:loss}}).
