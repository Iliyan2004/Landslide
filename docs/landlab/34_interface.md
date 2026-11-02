# User Interface

The page follows SAILAB's design system (colours, Barlow Condensed headings, Public Sans text, IBM Plex Mono numbers, glass panels), re-tinted amber so the two products are not confused. Layout: header with the hardware line, a 2D Mapbox map with layer buttons (national susceptibility, national physics, risk index, districts, faults, PNG export), a draggable divider, the 3D pane, a draggable column divider, and the right column.

Right-column panels, top to bottom: draw or upload an area; district discovery (ranked by a national metric); river basins; rainfall and triggers (Open-Meteo, antecedent index, ERA5 wettest 72 h, threshold check); live monitoring; five tabs (screening, instant, physics, earthquake, mitigate); layers of the current run with the PDF report link, landslide-dam screening, scoring against an observed extent and a batch PDF; GIS export, run history and comparison. Discovery also offers national rainfall hotspots. Barrier lines are drawn with the same drawing tool as the area polygon (the polygon is the area, lines are barriers). Every panel states what it is and is not, and the footer repeats that results are screening grade.

Interface checks (after the mitigation tab and run tools were added): the page and the 3D scene load in headless Chromium without JavaScript errors, and the inline script passes `node --check`. Individual controls have been exercised through the API, not clicked through in a real browser.


## Run report

The report (`/runs/<id>/report.html` and `.pdf`) follows SAILAB's report format: a masthead with the model name and run meta, a summary tile grid (failing area, peak PGA for earthquakes, released volume, impacted area, maximum depth, runout, damaged buildings, direct loss, blocked roads, people, isolated buildings), map plates over a hillshade with captions and a legend row (flow depth, deposit, failure time, factor of safety, PGA), hover charts of the storm and of the failed area against time, a run-configuration table, an assumptions and warnings list, and a footer, with SAILAB's light and dark theme (`app/report.py`).
