<!-- part: Part III - Workflow -->
# The Tiered Workflow

The page follows SAILAB's pattern: an area is chosen once (drawn, uploaded as a shapefile or GeoJSON, or taken from a district or a HydroSHEDS basin) and stays visible above four tier tabs. Each tier answers a question at a different cost.

| | Area limit | Output | Needs rainfall series |
|---|---|---|---|
| 1 Screening | up to the whole country (physics only below 150 m cells) | susceptibility, stability share, exposure | rain intensity and duration only |
| 2 Instant | up to about 1,350 km2 | critical-rain map, failing area against rain | no |
| 3 Physics | up to about 700,000 cells (at most 120 m) | failure times, flow over time, impacts, loss | yes |
| 4 Earthquake | same as Tier 3 | PGA, failures, flow over time, impacts | optional |

A sixth tab, **Rockfall**, runs the separate rock simulation (Ch. {{ch:rockfall}}). A fifth tab, **Mitigate**, holds nature-based levers, barriers (drawn on the map, optionally auto-placed) and average annual loss (Ch. {{ch:nature_based}}, {{ch:barriers}}, {{ch:aal}}). The right-hand column also holds area discovery (district ranking by national metrics, basins), a rainfall context panel, live monitoring, layer pickers for the finished run, run history, comparison and the PDF report.
