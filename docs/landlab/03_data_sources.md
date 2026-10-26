# Data Sources

All paths are in `backend/landslide/app/paths.py` (one place, checked at `/api/data-status`) and can be overridden by `LANDSLIDE_<NAME>` environment variables.

| Dataset | Detail | Used for |
|---|---|---|
| SRTM DEM | `Pak_srtm.tif`, 29.16 m, EPSG:32642, 52,189 x 64,499 cells | Slope, runout terrain, national product |
| National ML susceptibility | CNN-DNN + RF ensemble, 90 m, EPSG:32643, north only (about 31.1 N and up) | Tier 1, district statistics |
| Risk stack | `05_risk`: hazard, exposure, vulnerability, population (WorldPop 2025 constrained, people per 90 m cell), built fraction | Exposure, tiles |
| ERA5-Land hourly precipitation | zarr, 1980-01-01 to 2026-05-20, 0.1 degree, mm per hour | Hindcast storms, threshold validation |
| CHIRPS daily | 5 km GeoTIFFs from 1981 | Daily hindcasts (spread evenly over 24 h) |
| Open-Meteo | hourly forecast and recent observed, live | Forecast runs, monitoring, context |
| Buildings | Google Open Buildings, 7 local parquet tiles (5.85 GB), queried with DuckDB | Building damage, 3D |
| Roads | HOTOSM Pakistan roads, indexed GeoPackage | Blocked-road length, 3D |
| Facilities | Hospitals and Schools shapefiles | Facilities hit |
| Faults | `Fault_lines.shp` | Earthquake scenarios |
| Boundaries | Pakistan border, 164 districts | National mask, district statistics |
| Basins | HydroSHEDS level 8, 1,131 basins | Choosing an area |
| Landslide inventory | `Landslides_All.shp`, 392 points (NASA COOLR reports, GLC rainfall catalogue, AJK/GB/KP local inventories) | Validation only |
| Predictor stack | `01_layers`: slope, elevation, curvature, geology, land cover, TWI, SPI, distances, rainfall climatology | Validation only |

## 3.1 What the inventory is, and is not

After cleaning, the inventory has {{inventory_summary.json:records|0}} unique events. Positions are reports: the stated accuracy ranges from 0.5 km to 50 km, and for many records it is 25 km or worse. Dates are kept at the precision they were given: a bare year is never turned into 1 January. There are no deposit polygons, no measured volumes (one record), no soil measurements and no depth of failure. This caps what any validation can show (Ch. {{ch:validation_protocol}}).

## 3.2 Known coverage gaps

- The ML susceptibility layer ends near 31 N; elsewhere it is NODATA and is never read as "low".
- The 05_risk population layer follows the same extent.
- ERA5-Land ends on 20 May 2026.
