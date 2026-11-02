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

An early ranking counted only slopes that were *stable before the storm and fail in it*, and put planting alone at 23% **more** failure than the baseline, which is not physical: the model counts only slopes that were stable before the storm (Ch. {{ch:terrain_parameters}}.5), and extra root cohesion turns slopes that were unstable (not counted) into slopes that are stable before the storm and then fail in it (counted). The ranking now uses the **unstable area at the end of the storm, including slopes that were already unstable** (`unstable_km2`, `failing_area` in `engine/run.py`). Every lever is compared on the same cells, so a lever can only remove instability; the "failing" figure is still reported for reference. A unit test checks that planting never increases the unstable area.

The ranking below is for the 57 km2 Gilgit area, a 60 mm/h triangular storm of 12 hours (an extreme storm, 360 mm) and the "weak_clayey" scenario at quantile 0.3:

| Levers | Unstable area (km2) | Change against the baseline ({{area_demo.json:nbs_rank.result.baseline.unstable_km2|1}} km2) |
|---|---|---|
| {{area_demo.json:nbs_rank.result.ranked.0.levers}} | {{area_demo.json:nbs_rank.result.ranked.0.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.0.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.1.levers}} | {{area_demo.json:nbs_rank.result.ranked.1.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.1.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.2.levers}} | {{area_demo.json:nbs_rank.result.ranked.2.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.2.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.3.levers}} | {{area_demo.json:nbs_rank.result.ranked.3.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.3.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.4.levers}} | {{area_demo.json:nbs_rank.result.ranked.4.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.4.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.5.levers}} | {{area_demo.json:nbs_rank.result.ranked.5.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.5.reduction_frac|pct}} less |
| {{area_demo.json:nbs_rank.result.ranked.6.levers}} | {{area_demo.json:nbs_rank.result.ranked.6.unstable_km2|1}} | {{area_demo.json:nbs_rank.result.ranked.6.reduction_frac|pct}} less |

How to read it: every option that includes planting removes all the instability, because the assumed 6 kPa of root cohesion is as large as the scenario's own cohesion (2 to 10 kPa); that is a property of the user-set effect size, not of planting in general. Without planting the levers are weak: regrading to the 25 degree cap and drainage together remove {{area_demo.json:nbs_rank.result.ranked.4.reduction_frac|pct}}, drainage alone a few percent, and regrading alone almost nothing, because a saturated slope of friction angle 15 to 26 degrees is unstable even at 25. The effect sizes (6 kPa root cohesion, 25 degree cap, drainage lowering saturation) are user inputs, not measurements, and the ranking is a stability-only comparison; the runout benefit needs a full mitigated run.
