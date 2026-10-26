<!-- part: Part I - Overview -->
# Executive Summary

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
| Tiers 1 to 4, national product, districts, basins | Implemented and tested ({{TESTS}} unit tests) |
| Rainfall sources: design storm, forecast, recent, ERA5, CHIRPS, CSV | Implemented |
| Impacts: buildings, roads, hospitals and schools, direct loss | Implemented (all thresholds assumed, Ch. {{ch:exposure_damage}}) |
| Live monitoring with webhook, compare runs, PDF report, MP4 export | Implemented |
| Rainfall-threshold validation against the inventory | **Done** (Ch. {{ch:rain_threshold_validation}}) |
| Spatial validation, physics and ground calibration, runout check, ShakeMap comparison, quake-landslide check | **Run** (Ch. {{ch:spatial_validation}} to {{ch:runout_calibration}}, {{ch:earthquake_failure}}.2, {{ch:accuracy_record}}) |
| Design storms from observed IDF, climate multiplier (code), average annual loss | Implemented; the climate multiplier and AAL have **not yet been run on real data** (compute heavy) |
| Nature-based levers, barriers, ranking, automatic barrier placement | Implemented and unit tested; **not yet run on real areas** (placement is expensive) |
| Landslide-dam screening, rainfall hotspots, scoring against an observed extent | Implemented (dam screening and hotspots run on real data; observed scoring needs a supplied extent) |
| Rockfall simulation (GPU Monte Carlo, barriers, impacts) | Implemented and run on a Hunza area; **uncalibrated** (Ch. {{ch:rockfall}}) |
| Debris, earthquake and rockfall visualisation | Rebuilt and checked by rendering (Ch. {{ch:visualization}}) |
| Spatially varying ground, access and isolation impacts, GIS export, token and rate limit, run clean-up, IMERG rainfall | Implemented |
| Physics, runout and PGA calibration scripts | **Written and unit tested on synthetic data; not run** (compute heavy, on request) |


> **Honest summary of accuracy today.** Every strength, friction, fragility and cost value is a scenario value. The only validation completed is the temporal one: ERA5 rainfall separates reported rain-triggered landslide days from same-place, same-season controls with an AUC of {{rain_threshold.json:feature_auc.I24.auc|2}} (95% interval {{rain_threshold.json:feature_auc.I24.ci95.0|2}} to {{rain_threshold.json:feature_auc.I24.ci95.1|2}}). That is real but modest skill. Nothing in this system is validated against mapped deposits, because none exist on the server.

## 1.3 Principles

- **Nothing invented.** Missing data stays missing (NODATA is never "low risk"); unknown soil strength is an explicit range, never a silent default.
- **Screening grade.** Every run carries `calibration_status`, `validation_status` and `not_for_engineering_design`.
- **GPU first, then RAM, then CPU.** The runout solver and the stability ensembles run on CUDA; arrays live in host RAM; NumPy/numba is the automatic fallback (Ch. {{ch:gpu_implementation}}).
- **Numbers from files.** This document reads its results from `docs/validation/*.json` when it is built.
