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
