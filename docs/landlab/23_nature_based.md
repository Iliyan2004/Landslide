<!-- part: Part VII - Mitigation -->
# Nature-Based Solutions

Three levers act on the stability inputs inside the whole area (an optional zone polygon is supported by the model; the page applies the whole area). They are **scenario levers: the size of each effect is the user's input, with plausible defaults, not a measured performance.** The platform reports the change against the unmitigated run under the same storm and strength scenario.

| Lever | What it changes | Default |
|---|---|---|
| Planting | adds root cohesion to the stability equation (Pa) | +5 kPa |
| Regrading / terracing | caps the slope used for stability at an angle | 30 degrees |
| Subsurface drainage | scales the saturated fraction m and deepens the baseline water table | m x 0.6, water table +2 m |

The mobilisation rule (Ch. {{ch:terrain_parameters}}) uses the mitigated inputs too, so cells made stable are not counted. Regrading changes the slope in the stability calculation only, not the terrain the flow runs over; a regraded slope that still fails therefore runs out over the original relief, which is a simplification.

## Ranking the combinations

The page can rank all seven non-empty combinations of the three levers by the failing area they remove. This is a **stability-only** evaluation (no flow, about a second each), so it ranks the benefit to initiation, not to runout. A full mitigated run (below) then gives the change in impacted area, blocked roads, buildings damaged and loss.

Tests: each lever never increases failure; a 25 degree cap on a 33 degree slope removes failure; the ranking returns seven options ordered by reduction.

## First run on a real area, and a counting artefact that was fixed

On the 57 km2 Gilgit area (60 mm/h triangular storm for 12 h, strength preset "calibrated_reports") the first ranking, by the area that is *stable before the storm and fails in it*, put planting alone at 23% **more** failure than the baseline. That is not physical. The model counts only slopes that were stable before the storm (Ch. {{ch:terrain_parameters}}.5), because a slope that is already unstable would have failed earlier. Extra root cohesion turns slopes that were unstable (not counted) into slopes that are stable before the storm and then fail in it (counted), so the "failing" area could rise while the instability fell.

The ranking now uses the **unstable area at the end of the storm, including slopes that were already unstable** (`unstable_km2`, `failing_area` in `engine/run.py`). Every lever is compared on the same cells, so a lever can only remove instability. The "failing" figure is still reported for reference. A unit test checks that planting never increases the unstable area.

| Levers | Unstable area (km2) | Change against the baseline ({{area_demo.json:nbs_rank.result.baseline.unstable_km2|1}} km2) |
|---|---|---|
| planting + regrading | {{area_demo.json:nbs_rank.result.ranked.0.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.0.reduction_frac|pct}} less |
| planting + regrading + drainage | {{area_demo.json:nbs_rank.result.ranked.1.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.1.reduction_frac|pct}} less |
| planting + drainage | {{area_demo.json:nbs_rank.result.ranked.2.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.2.reduction_frac|pct}} less |
| planting | {{area_demo.json:nbs_rank.result.ranked.3.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.3.reduction_frac|pct}} less |
| drainage | {{area_demo.json:nbs_rank.result.ranked.4.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.4.reduction_frac|pct}} less |
| regrading + drainage | {{area_demo.json:nbs_rank.result.ranked.5.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.5.reduction_frac|pct}} less |
| regrading | {{area_demo.json:nbs_rank.result.ranked.6.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.6.reduction_frac|pct}} less |

How to read it: planting is the strongest single lever here (the fitted soil is weak, 0.9 kPa cohesion, so added root cohesion matters most), and planting with regrading removes all instability. Regrading to the default 25 degree cap on its own does nothing for the saturated storm: a soil of friction angle 30 degrees with a fully saturated slip layer has a factor of safety below 1 even at 25 degrees, so a lower slope alone is not enough. These effect sizes (6 kPa root cohesion, 25 degree cap, drainage lowering saturation) are user inputs, not measurements, and the ranking is a stability-only comparison; the runout benefit needs a full mitigated run.
