# Tier 1: Screening and the National Layers

## 10.1 National layers

The map offers four national layers as XYZ tiles read straight from the rasters (reprojected to Web Mercator per tile): the ML susceptibility (north only), the risk index, the national physics share (share of ensemble members with FS below 1 under 20 mm/h for 24 h on the colluvium preset), and slope at 90 m. The physics layer is built by `scripts/build_national.py`: EPSG:32642, 90 m, 2048-cell tiles, resumable, GPU first, only mobilisable cells counted. Slope from a 90 m average understates local slope, so it is a regional screen.

## 10.2 District statistics

`scripts/build_districts.py` summarises the 164 districts: area share and population above susceptibility 0.7, mean risk index, and the physics share on the physics product's own country-wide grid (the susceptibility grid covers only the north). Districts can be ranked by any of these and used as an area.

## 10.3 Area screening

For a drawn area, Tier 1 reads the DEM at 30 m (or coarser), the ML layer, runs the stability ensemble for the chosen rain, optionally Newmark with a scenario PGA, and a reach-angle run-out envelope (Corominas-style H/L, not a simulated depth), then reports population in the area and in unstable and reached cells. Population is people per 90 m cell and is rescaled by cell area when resampled; reading it bilinearly onto a 30 m grid had counted each person nine times (Ch. {{ch:chronicle}}).

> The ML layer is an external product trained on these reports with a random split and flat-ground negatives. It ranks slope proneness; it does not describe a specific storm.
