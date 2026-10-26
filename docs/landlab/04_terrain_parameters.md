<!-- part: Part II - Hazard Physics -->
# Terrain, Soil Depth and the Parameter Model

## 4.1 Terrain

Slope is the Horn (1981) 3 x 3 gradient of the DEM on a grid in the AOI's UTM zone. The analysis cell is 30 m for areas up to the interactive budget and is coarsened in 10 m steps above it so a run stays within 1.5 million cells (Tier 1) or 700,000 cells (Tiers 3 and 4). Slope is resolution dependent: coarse cells smooth steep ground away. For that reason physics is **skipped, with a message,** when cells would be coarser than 150 m (Tier 1) or 120 m (Tiers 3 and 4). A whole-country interactive run at 820 m found 0.07% of area unstable, which is an artefact of smoothing, not a result.

## 4.2 Explicit parameter ranges

Every geotechnical input is a range (`gates.check_geotech` refuses a run if one is missing). Three strength presets are provided:

| Preset | Soil depth (m) | Cohesion (kPa) | Friction (deg) |
|---|---|---|---|
| colluvium_shallow | 0.5 to 2.0 | 1 to 8 | 26 to 36 |
| residual_soil | 1.0 to 4.0 | 3 to 15 | 22 to 34 |
| weak_clayey | 1.0 to 3.0 | 2 to 10 | 15 to 26 |

Other priors: unit weight 18 kN/m3, root cohesion 0 to 5 kPa (maximum adjustable), water table 2 to 10 m, initial moisture 0.25 (capped at porosity minus 0.02). Green-Ampt parameters come from the soil texture class (Rawls-type class averages): saturated conductivity Ks, suction head and porosity, with Ks given a factor-of-10 range. All of these are **scenario priors, not measurements.**

## 4.3 Choosing one parameter set

A physics run uses one scenario point inside the ranges, chosen by a *strength quantile* q between 0 (pessimistic end) and 1 (strong end):

```
value = lo + q (hi - lo)              (Ks log-uniform)
soil depth uses the opposite end:     depth = lo + (1 - q)(hi - lo)         (weak scenario = deeper soil)
```

Tier 1 and the national product instead sample the whole range (Latin hypercube) and report the spread across members.

## 4.4 Soil depth varies with slope

By default soil thins as slope steepens (an assumption, switchable):

```
z(slope) = z_max - (z_max - z_min) * clip(slope / 50 deg, 0, 1)
```

## 4.5 Who can fail: the mobilisation rule

A rain or earthquake event can only mobilise a cell that (a) carries soil, meaning slope at most 45 degrees (steeper ground is treated as bare rock, a separate rockfall problem), and (b) was **stable before the event**, meaning FS at least 1 at the baseline water table. Cells that fail the second test would already have failed under ordinary conditions. Without this rule the model labels bare rock and perennially unstable cells as storm failures: with the weakest strength preset, 48% of the Gilgit test area was "unstable" with zero rain. The run reports the counts it excluded (`trigger.mobilisable`).
