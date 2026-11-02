# Known Limitations

1. **Calibrated and validated only as far as the inventory allows.** See Ch. {{ch:accuracy_record}} for exactly what has and has not been checked.
2. **One soil layer, infinite slope.** No deep-seated slides, no rock-slope kinematics, no rockfall, no snow avalanche, no glacial-lake outbursts.
3. **Rain is spatially uniform** over the area by default and comes from a point (ERA5, CHIRPS, forecast) or a design storm; a gridded-rain option exists (Ch. {{ch:rain_triggered_failure}}.7) but cannot be tested on this inventory.
4. **Pore pressure is a proxy** from a wetting front, not groundwater flow. A topographic water-table option and a suction option exist; neither improved held-out skill, so both are off.
5. **Failure depth equals soil depth**, thinned with slope by an assumption and optionally capped by the bedrock-depth map; real slip surfaces are not mapped, and the borehole, groundwater and soil data supplied later are on the Indus plain, not on slopes, so they could not constrain it (Ch. {{ch:data_sources}}.4).
6. **Earthquake ground motion** uses NGA-West2 with a Vs30 site term (and a regional intraslab model for deep events) with no directivity; it is within a factor of about 1.5 of ShakeMap, low by about a quarter for M 7 and above (Ch. {{ch:earthquake_failure}}.2).
7. **Runout friction is a scenario value by flow type;** the single-phase depth-averaged model does not separate solid and fluid phases.
8. **Impacts** use assumed fragility medians and a single unit cost; no indirect loss, no lives.
9. **Building heights** are assumed 6 m (display only); footprints come from a satellite-derived dataset with its own errors.
10. **ML susceptibility** covers the north only.
11. **Terrain** is SRTM at 29 m: gullies, small scarps and road cuts are not resolved.
12. **Spatial misregistration** of the 3D canvas (lon/lat rectangle over a UTM grid) is small for tens of kilometres and grows with area.
13. **Design storms** are point depths from 46 years of ERA5-Land annual maxima: 100- and 200-year values are extrapolations, short durations are lower bounds, and storms are limited to 24 h.
14. **Mitigation effects** (root cohesion, regrading, drainage, barrier height) are the user's scenario inputs; regrading changes stability only, not the terrain the flow crosses; barriers are not drawn in the 3D scene.
15. **Average annual loss** assumes a T-year storm gives the T-year loss.
16. **Dam screening** uses a drainage area truncated at the analysed edge and an embankment breach formula for the peak; there is no downstream routing.
17. **Rockfall** uses scenario restitution, friction and roughness; the first run gave reach angles steeper than literature shadow angles, so it is probably too dissipative; energy is translational only; no damage or loss is estimated.
18. **Geology** strength multipliers are neutral (1.0) because the geology raster's lithology is only guessed from colours.
19. **Earthquake animation** wavefronts are time-scaled; the shaking field has no site amplification.
20. **Access analysis** sees only roads inside the area and ignores speeds.
