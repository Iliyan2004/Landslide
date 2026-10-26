# Tier 3: The Physics Run

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

Failing area and soil depth; released, entrained and final volume with a mass check; impacted area, maximum depth, maximum speed and runout from the source; counts of failed cells against time; maximum depth, speed, deposit, scar, failure-time, minimum-FS and slope rasters; impacts (Ch. {{ch:exposure_damage}} and 17); the 3D scene.

## 12.4 Reference run (a stress test, not a design storm)

Gilgit test area (about 20 km2, 22,000 cells at 30 m), triangular storm of 60 mm/h peak for 12 h (360 mm), colluvium preset, strength quantile 0.3, debris flow, entrainment on: 1,329 failing cells (1.20 km2), 0.96 million m3 released plus 65,000 m3 entrained, 3.6 km2 impacted, maximum depth 7.1 m, maximum speed 11.9 m/s, runout 1.3 km, 24 s end to end on the GPU. A 70 mm/h peak storm on the same area impacts 3.9 km2 (maximum depth 7.3 m), only slightly more than the 60 mm/h run, whereas an M 7.2 earthquake with a 2 cm Newmark criterion on the same area impacts 12.4 km2 with depths up to 19.7 m. Outcomes are very sensitive to the trigger and to the strength scenario (Ch. {{ch:terrain_parameters}}.3).
