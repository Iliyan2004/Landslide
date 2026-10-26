# Access and Isolation Impacts, and GIS Export

## Access

A blocked road is a poor measure of consequence on its own. After a debris-flow run the platform builds a network from the HOTOSM roads in the area (vertices snapped to a 5 m grid), removes segments blocked at 0.5 m depth, and asks which buildings and facilities lose road access.

- A point is **cut off** when its nearest road node is in the largest connected component before the event but not after. Components that were already disconnected are not blamed on the event (a test checks this).
- Points farther than 400 m from any road are not assessed.
- For hospitals and schools, the shortest path to a central node of the network is compared before and after, giving the extra distance or a cut-off flag.

Gilgit reference (3.6 km2 flow, 14,458 points): 39% of buildings were cut off; the largest road component fell from 88% to 46% of nodes; of the 58 hospitals and schools assessed, several were cut off and a few faced detours of 70 to 230 m. Limits: the network ends at the area boundary, so connection through the outside world is unseen; distance only, no speeds or capacity; missing OpenStreetMap roads make isolation overestimated.

## Spatially varying ground

By default one strength set applies to the whole area. With **spatially varying ground** (off by default) the platform reads land cover and geology rasters. Root cohesion comes from land cover (trees 6 kPa, crops 1.5, rangeland 0.5, flooded vegetation 2, bare, built, snow and water 0; mid-range assumptions) and replaces the scenario root cohesion where the land cover is known. **Geology multipliers on cohesion and friction are all 1.0:** the national geology raster has 16 colour-coded units whose lithology is only guessed from map colours, so strength values for them would be invented. The mechanism exists so calibration can fit multipliers on held-out data (Ch. {{ch:physics_calibration}}). In the Gilgit reference storm, switching it on raised the failing area from 1.2 to 4.4 km2, because land-cover root cohesion is mostly zero on the steep slopes (the default scenario assumed 0 to 5 kPa everywhere). Land cover is a strong lever, and it is an assumption.

## GIS export

`/runs/<id>/export.zip` gives: GeoTIFF rasters in the analysis CRS (DEM, slope, maximum depth and speed, deposit, scour, failure time, minimum FS, PGA, rock reach, energy and bounce height as available); GeoJSON polygons of the failure zones and the debris or rock-reach extent; GeoJSON and CSV of buildings with damage state, loss and rock energy class; affected roads; the manifest with all parameters and warnings; the summary. Nodata is -9999.
