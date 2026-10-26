# Validation 2: Spatial Skill

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

{{spatial_skill.json:n_events|0}} events, {{spatial_skill.json:n_controls|0}} random controls; AUC on held-out 1 degree blocks, interval by bootstrap over blocks.

| Predictor | AUC | 95% interval |
|---|---|---|
| Slope only | {{spatial_skill.json:models.slope_only.auc|3}} | {{spatial_skill.json:models.slope_only.ci95.0|3}} to {{spatial_skill.json:models.slope_only.ci95.1|3}} |
| Physical instability index, shipped parameters | {{spatial_skill.json:models.physics_infinite_slope.auc|3}} | {{spatial_skill.json:models.physics_infinite_slope.ci95.0|3}} to {{spatial_skill.json:models.physics_infinite_slope.ci95.1|3}} |
| Terrain (boosted trees) | {{spatial_skill.json:models.terrain.auc|3}} | {{spatial_skill.json:models.terrain.ci95.0|3}} to {{spatial_skill.json:models.terrain.ci95.1|3}} |
| Hazard-only (terrain, hydrology, geology, land cover, rain) | {{spatial_skill.json:models.terrain+hydro+geology+landcover+rain (hazard-only GBM).auc|3}} | {{spatial_skill.json:models.terrain+hydro+geology+landcover+rain (hazard-only GBM).ci95.0|3}} to {{spatial_skill.json:models.terrain+hydro+geology+landcover+rain (hazard-only GBM).ci95.1|3}} |
| Hazard-only plus physics | {{spatial_skill.json:models.hazard-only + physics.auc|3}} | {{spatial_skill.json:models.hazard-only + physics.ci95.0|3}} to {{spatial_skill.json:models.hazard-only + physics.ci95.1|3}} |
| Hazard-only plus the new ground layers (GLiM, texture, bedrock, Vs30) | {{spatial_skill.json:models.hazard-only + new ground layers (GLiM, texture, bedrock depth, Vs30).auc|3}} | {{spatial_skill.json:models.hazard-only + new ground layers (GLiM, texture, bedrock depth, Vs30).ci95.0|3}} to {{spatial_skill.json:models.hazard-only + new ground layers (GLiM, texture, bedrock depth, Vs30).ci95.1|3}} |
| Report-aware (adds distance to roads and cities) | {{spatial_skill.json:models.hazard + human-access variables (report-aware).auc|3}} | {{spatial_skill.json:models.hazard + human-access variables (report-aware).ci95.0|3}} to {{spatial_skill.json:models.hazard + human-access variables (report-aware).ci95.1|3}} |

What this says:

- The infinite-slope physics ranks reported landslide places only a little better than slope itself (0.60 against 0.57; the intervals overlap). On this inventory the physical model, with its generic parameters, is not a strong locator.
- Statistical models using terrain, hydrology and land cover do clearly better (0.71 to 0.75). Physics adds nothing to them (0.752 against 0.753).
- The new ground layers did **not** help; they lowered the score (0.733) because the extra inputs over-fit the 600 events. This agrees with Ch. {{ch:ground_calibration}}.
- Adding road and city distance gives 0.763: reporting bias is small compared with the terrain signal, but not zero.
- Skill falls with location uncertainty: AUC {{spatial_skill.json:by_radius.<=1 km.auc|2}} for reports located within 1 km, {{spatial_skill.json:by_radius.1-5 km.auc|2}} for 1 to 5 km, {{spatial_skill.json:by_radius.>5 km.auc|2}} beyond 5 km, as expected when a report's position is only known to its accuracy radius.

> The existing national ML map reports AUC 0.88 to 0.90 (and 0.80 here on mean probability, with the caveat that it was trained on these reports). Its negatives are half flat ground, at least 5 km from any landslide, and its test split is random. This experiment uses random negatives and block cross-validation, so the numbers are lower and the two are not comparable.

The physics model's job in the platform is runout, impacts and scenario testing, where the statistical models cannot help; for *where* landslides are likely, the national ML susceptibility layer (Tier 1) is the better guide, and the physics run should be read as "if this slope fails".
