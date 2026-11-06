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
