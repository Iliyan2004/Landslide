# Reports, Comparison and Exports

- **PDF report** (`/runs/<id>/report.pdf`): trigger, runout and exposure tables, the loss note and every warning and assumption, rendered with WeasyPrint.
- **Compare two runs** (same polygon and grid): impacted area in A only, B only and both, maximum depth, mean depth change, direct loss. Example: a 70 mm/h storm against an M 7.2 earthquake on the Gilgit test area impacts 3.9 and 12.4 km2, with 3.0 and 11.1 billion PKR direct loss.
- **Run manifest**: model and version, sources, grid, parameters, rainfall provenance, warnings, calibration and validation status.
- **Summary JSON**, **map layers** (maximum depth and speed, deposit, scour, failure time, minimum FS, PGA, slope) as georeferenced PNG overlays, **MP4 and PNG** from the 3D scene.
- **Batch PDF** (`/batch-report.pdf?ids=...`): a table of selected runs with rain, failing area, released volume, impacted area, depth, buildings at DS3 or above and direct loss.
- **Mitigation comparison**: unmitigated against mitigated run, with the change in failing area, impacted area, loss, blocked road length and buildings at DS3 or above (Ch. {{ch:nature_based}}, {{ch:barriers}}).
