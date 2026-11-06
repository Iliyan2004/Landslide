# SAILAB Parity and FastSlide-Inspired Features

## 43.1 Pages and interface taken from SAILAB (version 2.5.0)

- **Landing page** at `/` (WebGL shader background, links to the two tools), **the app** at `/app`, and **LANDLAB Instant** at `/instant`.
- **Instant** draws an area and returns, in seconds, the unstable area against a 24 h rain ladder (0, 25, 50, 100, 150, 200, 300, 450, 600 mm), a critical-rain map and failing-cells overlays. It uses the median strength of the chosen preset, not an ensemble, so it is a screening view; the full run remains the product.
- App additions: header navigation and place search, a welcome card, 3D expand/hide, custom DEM upload, saving and loading a run file, and calibration to an observed landslide extent.
- **Custom DEM.** A user GeoTIFF replaces the national DEM inside its footprint. Areas outside the file are refused with a message rather than filled from another source.
- **Run file.** A run's inputs are written to `inputs.json`; loading one passes through a whitelist, so unknown or oversized fields are dropped.
- Not taken: the basemap switch (satellite or streets) in the 2D view, because swapping the style drops the map's sources.

## 43.2 Calibration to an observed extent

The user supplies observed landslide polygons. The platform runs trial scenarios over a strength quantile and a friction-multiplier grid and keeps the one with the highest critical success index (CSI) against the observed cells. Synthetic check: an extent produced at quantile 0.55 was used as the "observed" one, starting from quantile 0.2 (CSI 0.14); the search chose 0.5 and CSI rose to 0.92. This shows the search finds a known answer; it does not show that a real inventory is reproduced, which depends on the reports' positional accuracy.

## 43.3 Ideas from FastSlide (fastflood.org)

Implemented: **strength zones** (the user supplies polygons with `cohesion_kpa` and/or `friction_deg`; those cells take the stated values, cohesion clipped to 0 to 100 kPa and friction to 5 to 50 degrees, later polygons override earlier ones) and **per-slide runout statistics** (mean, median and 90th percentile of runout over connected flows, shown in the results and the report). The zone logic has a unit test.

Not implemented: SMAP soil-moisture input (the platform has its own antecedent-wetness treatment), an erosion or entrainment term (not calibrated here), and in-browser (WebAssembly) computation, which does not apply to a GPU server design.

The calibration also accepts no file: with "match the national susceptibility map" the target is the cells of the machine-learning susceptibility map at or above 0.5 (adjustable). In a trial on the Gilgit test area the overlap rose from 0.09 to 0.20 (strength quantile 0.3, friction halved). The target is a model, not an observation, so this makes the physics agree with the statistical layer; it does not validate either.

## 43.4 Cross-checks against external tools (from the improvement plan)

| Tool | What was done | Result |
|---|---|---|
| OpenQuake hazardlib | `scripts/check_gmpe_oq.py`: BSSA14 (60 magnitude-distance points for each of 4 Vs30 values) and the BC Hydro intraslab model (30 points for each of 6 depth and Vs30 pairs) compared with OpenQuake's implementations. | Identical to rounding error (BC Hydro exactly, BSSA14 to 1e-13 per cent). One point to know: OpenQuake has no "unspecified mechanism", so the comparison uses strike-slip; the platform's default unspecified term is 0.0383 ln units (3.8 per cent) lower, which is the published difference between the two coefficients, not an error. OpenQuake is AGPL and is used in this validation script only, never imported by the shipped backend. |
| Landlab `LandslideProbability` | `scripts/check_landlab_slope.py`: 300 random cells, 2,000 Monte Carlo draws each, same distributions. | Landlab and the SINMAP form of the equation on the same samples agree to Monte Carlo noise (correlation 0.9999). Against the platform's standard infinite-slope form they differ clearly: mean failure probability 0.28 against 0.21, and by up to 0.65 in single cells. The cause is that SINMAP (and so Landlab) divides cohesion by sin(b) where the standard form divides by sin(b) cos(b), and fixes the water to soil weight ratio at 0.5. The platform keeps the standard form; Landlab is therefore the more pessimistic of the two on cohesive soils. |
| TRIGRS (Iverson 2000 solution) | `scripts/compare_iverson.py`: the published transient pressure-head solution implemented directly and compared with the Green-Ampt proxy on 675 single-column cases (slope 25 to 45 degrees, depth 1 to 3 m, conductivity 1e-6 to 1e-4 m/s, rain 5 to 100 mm/h, water table at the slip surface or 0.5 or 1 m below it). | The two agree on failure or no failure in 76 per cent of cases. The Green-Ampt proxy is the slower and less sensitive: where both fail it takes a median of 2.3 times as long (10th to 90th percentile 1.0 to 8.2), and it misses 147 cases (22 per cent) that the Iverson solution fails, because a pressure wave from a shallow water table reaches the slip surface long before a wetting front does. In 13 cases only Green-Ampt fails. This is a comparison of two simplified columns on assumed soil values, not a test against real slides. The TRIGRS program itself was not built or run, so the Fortran code, its unsaturated option and its runoff routing were not tested. |
| USGS groundfailure | Read, not run. Its landslide models (Nowicki Jessee 2018 and others) need global lithology, land cover and topographic index grids that are not on the server, and the code was not installed. | No comparison made. |

Not done and why: r.avaflow needs GRASS GIS and a licence check; the D-Claw repositories named in the plan could not be found; MintPy needs a Sentinel-1 data account and is a separate project; Landlab's flow-routing tools were not swapped in because the existing terrain code is already tested against analytic cases.
