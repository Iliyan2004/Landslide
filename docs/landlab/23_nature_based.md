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

## First run on a real area, and a counting artefact

On the same 57 km2 Gilgit area (60 mm/h triangular, 12 h; baseline failing area 8.56 km2) the ranking gave:

| Levers | Failing area (km2) | Change |
|---|---|---|
| planting + regrading | 0 | -100% |
| planting + regrading + drainage | 0 | -100% |
| drainage | {{area_demo.json:nbs_rank.result.ranked.2.failing_km2|2}} | {{area_demo.json:nbs_rank.result.ranked.2.reduction_frac|pct}} less |
| planting + drainage | {{area_demo.json:nbs_rank.result.ranked.3.failing_km2|2}} | {{area_demo.json:nbs_rank.result.ranked.3.reduction_frac|pct}} less |
| planting alone | {{area_demo.json:nbs_rank.result.ranked.4.failing_km2|2}} | **more failure than the baseline** |

Planting alone *increasing* the failing area is not a physical result. The model counts only slopes that were **stable before the storm** (Ch. {{ch:terrain_parameters}}.5), because a slope that is already unstable would have failed earlier. Extra root cohesion makes slopes stable before the storm that were unstable without it (the count of cells that can fail rises from 37,429 to 49,021), and some of those then fail in the storm, so they are counted as new failures even though without planting they would have been counted as already failed. The unit test passes because the synthetic slope has no such cells. The honest reading is: the ranking is reliable for the *order* of the options that include regrading or drainage, and it must not be used to conclude that planting is harmful or useless. The fix (counting pre-existing instabilities in the baseline so that every lever is compared on the same cells) is a design decision left open.
