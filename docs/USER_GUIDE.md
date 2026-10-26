# LANDLAB user guide

Landslide modelling for Pakistan: screening, physics runs, earthquakes, rockfall, mitigation. **Screening grade: soil strength and friction are scenarios, nothing is calibrated, not for engineering design or evacuation.** Details and limits are in `LANDLAB_Technical_Reference.pdf`.

## Start
`~/flood/venv/bin/python landslide_app.py` then open `http://<server>:5070`. Optional: `LANDLAB_TOKEN=secret` makes runs require that token.

## Choose an area
Draw a polygon (map tool, top-left), upload a zipped shapefile or GeoJSON, or use a district or river basin from the right column. Physics runs work up to about 700,000 cells (about 600 km2 at 30 m). Larger areas use Tiers 1-2 and the national layers.

## The tabs
| Tab | Use it to |
|---|---|
| 1 Screening | see susceptibility (north only), a quick stability share and population exposure |
| 2 Instant | build a rain ladder; drag the slider for the failing area; show the rain each slope needs to fail |
| 3 Physics | load a rainfall series (design storm, return-period storm, forecast, ERA5, IMERG, CHIRPS, CSV), run, watch the 3D event |
| 4 Quake | set magnitude and epicentre; see shaking, failures, runout |
| 5 Mitigate | nature-based levers, barriers, rank combinations, average annual loss |
| Rockfall | release rocks from steep faces; see paths, energy, buildings and roads reached |

## Reading a 3D scene
Debris scene: dark wet mud moving, pale cracked mud at rest; red flash then pale scar where a slope failed; "Terrain change" shows lost (blue) and gained (brown) ground; buildings turn yellow to red with the damage expected from the depth reached. Earthquake: epicentre, rupture line, rings (time-scaled), "Ground shaking" map. Rockfall: rocks coloured by energy, trails, dust, reach / energy / bounce maps (click the map for values). Right-drag rotates.

## After a run
PDF report, GIS export (GeoTIFF, GeoJSON, CSV), landslide-dam screening, scoring against an observed extent you upload, compare two runs, batch PDF. Runs live in `runs/<id>`; `POST /runs/cleanup` (dry run by default) frees disk.

## Things that surprise people
- No failure is a valid answer: change rain, strength scenario (slider) or soil type.
- "Strength scenario" 0 is weakest, 1 strongest; results change a lot across it.
- Land-cover root cohesion (Spatially varying ground) can triple the failing area.
- Rain is uniform over the area; ERA5 and CHIRPS smooth cloudbursts.
- Heavy jobs run one at a time on the shared GPU and fall back to the CPU if it is full.
