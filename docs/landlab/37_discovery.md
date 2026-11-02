# Discovery Tools

Three aids for choosing where to look, all independent of any run:

- **Districts.** The 164 districts ranked by a national metric: area share and population above ML susceptibility 0.7, mean risk index, and the physics share from the national product (which covers all districts; the ML layer covers the north). Any district can become the area.
- **River basins.** The 1,131 HydroSHEDS level-8 basins by region, ranked by area, usable as the area (basins are used only as shapes).
- **Rainfall hotspots.** The highest individually recorded cells, never averaged, for a metric (RX1day, RX5day, R99p, peak hourly, days of at least 20 mm, trend of RX1day) and season, from the ERA5-Land indices cube, each with its district and a Go button. A neighbourhood of 2 cells keeps one hit.

> Values are those of the source dataset. The largest RX1day values (several hundred millimetres in a day in places such as Balochistan) come from ERA5-Land and were not independently checked here; the source's own README documents that ERA5-Land misses localised convective extremes in other places, so the dataset can both overstate and understate at a point.
