<!-- part: Part IV - Rockfall -->
# Rockfall Simulation

Rockfall is a separate hazard from debris flow: the mass is a set of discrete rocks that fly, bounce and roll, not a continuum. LANDLAB simulates it with a three-dimensional Monte Carlo on the DEM, on the GPU first (`engine/rockfall.py`, `rock_run.py`).

## Release

Rocks start at rest on **steep rock faces**: cells at least 50 degrees (adjustable), the same slopes the soil model excludes as bare rock (Ch. {{ch:terrain_parameters}}). Up to 150 release cells are chosen, weighted toward the steepest; each releases 40 rocks (adjustable, 60,000 rocks at most). Alternatives: user-drawn source polygons, or an earthquake, where cells with PGA of at least 0.10 g are weighted by shaking and slope. Diameter is lognormal (median 0.8 m, sigma 0.35 in ln units, clamped 0.2 to 6 m); density 2,600 kg/m3, so the median rock weighs about one tonne. Release times are staggered over 20 s for the animation only; the physics of each rock is independent.

## Motion

Time step 0.04 s. Each rock is a sphere with position and velocity:

```
flight:     vz -= g dt                                    (no air drag)
contact:    the centre reaches ground + radius -> the rock is put back on the surface and an impulse is applied
  fast (normal speed > 1.5 m/s):  tilt the normal by a random sub-grid roughness angle, then
                                  v_n' = -Rn v_n,   v_t' = Rt v_t
  slow (sliding or rolling):      v_n' = 0,   |v_t| -= mu |v_n|        (Coulomb / rolling resistance per step)
stop:       |v| < 0.2 m/s for 1 s;  also stop if it leaves the area or t > 100 s
```

Surface properties come from the land-cover raster and are **scenario values**, with friction scaled by 0.45 after a check against published runout statistics (Ch. 14.9):

| Surface | Rn | Rt | mu |
|---|---|---|---|
| Bedrock | 0.46 | 0.86 | 0.30 |
| Talus | 0.32 | 0.76 | 0.45 |
| Soil | 0.22 | 0.60 | 0.60 |
| Forest | 0.17 | 0.52 | 0.66 |
| Snow / ice | 0.15 | 0.50 | 0.22 |

Each is multiplied by shape factors (round 1, angular 0.8/0.9/1.25, platy 0.6/0.8/1.5, assumed) and jittered by 15% (Rn) and 10% (Rt) per impact. The **sub-grid roughness angle** (default 9 degrees) stands in for terrain detail that a 30 m DEM does not carry; it is the most sensitive parameter and is not yet calibrated.

## Barriers (rockfall fences)

A fence is a line of cells with a height and an energy capacity. A rock reaching it below the fence height with energy under the capacity **stops there**; above the capacity it passes with the capacity removed from its energy; above the fence height it passes unchanged. Nothing else is assumed.

## Outputs

Per cell: the share of released rocks that passed (reach probability), the maximum translational energy (0.5 m v2), the maximum bounce height above ground. Per rock: stop point and **reach (travel) angle**, the angle of the line from release to stop, which can be compared with the shadow angles of 22 to 32 degrees in the literature. A set of 250 tracked rocks is recorded every 0.12 s for the animation. Translational energy omits rotation, which can add up to 40% for a rolling sphere.

## Impacts

A building or road is reached if at least 1% of released rocks pass its cell (3 x 3 neighbourhood). Buildings and road lengths are classified by the worst energy class reaching them: below 10 kJ, 10 to 50, 50 to 300, 300 to 1000 and above 1000 kJ (the classes used to specify fences). Facilities and population in reached cells are reported. **No damage ratio or loss is computed for rockfall, because no rockfall fragility is available here.**

## Tests

Five synthetic-terrain tests: rocks start on the cliff, run down and stop on the flat with a reach angle below the slope angle; translational energy never exceeds the released potential energy (energy is dissipated, never created); a soft surface shortens the runout; a strong high fence stops everything above it and the stops are counted at the fence; the same seed gives the same result.

## Reference run

Hunza (Karimabad), 6 x 5.5 km, about 8% of cells at 50 degrees or steeper: 120 release cells, 4,800 rocks (median 1.0 t), 68 s end to end on the GPU. 95% of rocks stop, 5% leave the area, the median reach angle is 46 degrees and the 10th percentile 39 degrees. Only 0.5% of rocks have a reach angle below 27.5 degrees, so these rocks are **stopping much sooner than the literature shadow angle suggests**: with the uncalibrated surface and roughness values the model is probably too dissipative on this terrain. The peak translational energy is 38 MJ, the 95th percentile bounce height 4.7 m, and 1.8 km of road is reached, mostly above 1,000 kJ. These numbers are an uncalibrated first look, not a hazard assessment.


## 14.9 Check against published shadow angles

No Pakistani rockfall deposits are on the server, so the dissipation was checked on a synthetic profile (250 m cliff at 60 degrees, 700 m talus at 36 degrees, flat floor, 30 m cells). With the original friction the first percentile of the reach angle was 36 degrees; the literature shadow angle (the angle to the farthest 1% of rocks) is 27 to 32 degrees, and the median reach angle of rocks that stop on a 36 degree talus is 33 to 42. A sweep of roughness (5 to 13 degrees), restitution (0.8 to 1.25 times) and friction (0.15 to 1 times) showed that only friction moves the result materially: a factor of 0.4 to 0.5 gives a first percentile of 29 to 31 degrees and a median of 34 to 35 (`docs/validation/rockfall_shadow.json`). A factor of 0.45 is applied. This sets the order of magnitude of the dissipation from the literature; it is not a field calibration, and the Hunza reference numbers above predate it.
