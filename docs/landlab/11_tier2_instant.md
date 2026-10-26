# Tier 2: Instant Stability Library

Tier 2 is the landslide counterpart of an instant preview. For one area it computes median-parameter factor-of-safety maps for a ladder of 24-hour rain totals (0, 25, 50, 100, 150, 200, 300, 450 and 600 mm, uniform over 24 h) under the chosen texture, preset and strength quantile. The browser then interpolates between rungs as the slider moves, with no server call.

The **critical-rain map** assigns each mobilisable cell the rain at which FS first falls below 1, interpolating FS linearly between rungs (cells that never fail within 600 mm stay empty). The page also gives the failing area against rain and the median critical rain.

Example (Gilgit test area, colluvium preset, sandy loam, strength quantile 0.3): nothing fails at 100 mm, 5.3 km2 fail at 300 mm, and the median critical rain is about 170 mm. The same area under the weakest preset leaves 48% of cells already unstable when dry, so they are excluded (Ch. {{ch:terrain_parameters}}.5) and the library reports the excluded count.
