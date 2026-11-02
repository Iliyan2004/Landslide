# Chronicle of Findings and Bugs

Each entry was found by checking a result against something known, not by inspection of the code.

| # | Finding | How it was caught | Fix |
|---|---|---|---|
| 1 | Population was counted about 9 times at 30 m | Gilgit showed 570,000 people in 120 km2 | Resample per-cell counts by averaging and scale by cell area |
| 2 | A whole-country run at 820 m cells found 0.07% unstable | Result implausibly low | Physics is skipped above 150 m cells with an explicit message; the national product is built tile by tile at 90 m instead |
| 3 | Bare rock and perennially unstable cells appeared as storm failures (48% of an area unstable at zero rain) | The Tier 2 library showed failure at 0 mm | Mobilisation rule: soil-bearing (at most 45 degrees) and stable before the event (Ch. {{ch:terrain_parameters}}.5); the national product was rebuilt with it |
| 4 | Time step 0.5 s gave a steady speed 12% low | Compared with the Voellmy analytic speed | Time step capped at 0.2 s |
| 5 | numba with 20 threads was 80 times slower than 1 thread on a small grid | Profiling a 24 s run that should have taken 2 s | Thread count chosen from grid size |
| 6 | GPU solver slower than the CPU | Timing | CUDA graphs, then `torch.compile` fusion for large grids (Ch. {{ch:gpu_implementation}}.2) |
| 7 | Out-of-memory when creating a CUDA context on the shared GPU | A second process failed in the tests | Fall back to CPU on any GPU failure; release cached memory after jobs; tests skip rather than fail |
| 8 | An in-memory result cache lacked the grid transform, so overlays returned errors after a restart | Overlay request failed | Results are always reloaded from the saved run |
| 9 | Year-only dates (such as "2010") parsed as 1 January | Date histogram showed 1929 to 2026 | Only full dates are day-resolved; precision is tracked; undated duplicates need the same stated year |
| 10 | The fast ensemble indexed some sampled parameters wrongly (harmless only because those parameters were constant) | Code review while adding the GPU path | Every sampled parameter is indexed per member; a test compares against the reference ensemble |
| 11 | Slab front slumped, failing a "rest" test | Test failed | The check now covers the interior, where friction holds; the front slumping is correct physics |
| 12 | A boundary polygon of 985,000 km2 exceeded the area cap | Whole-country request rejected | Cap set to 1.2 million km2 (the border file includes disputed territory) |
| 13 | `pgrep -f` and `pkill -f` with a plain pattern killed the tool's own shell | Shell exited with code 144 | Anchored patterns |
| 14 | Chart of an animation window began at "0:00" although it started hours into the storm | Reading a screenshot | Legend states the window start; calendar time is shown when a start date exists |
| 15 | The earthquake run's numbers had been quoted for a storm run in a draft of this document | Checking the figures against the stored comparison | Corrected in Ch. {{ch:tier3_pipeline}}.4 |
| 16 | A "6 m barrier" on a steep slope let 90% of a flow through | The new barrier test | A wall's height is measured above the ground upslope: the wall cell is raised by height plus the ground drop across a cell (Ch. {{ch:barriers}}) |
| 17 | IMERG sub-hourly values were intensities, not depths, so a 1 h design storm summed to 9.1 mm instead of 8.0 mm | Mass check of the hyetograph against the IDF depth | Convert intensity to depth by multiplying by duration before taking the shape (Ch. {{ch:design_storms_climate}}) |
| 18 | `np.interp` rejected an array `left` argument in the sub-hourly branch | First hyetograph call | Handle the shortest-window extrapolation explicitly |
| 19 | The reference storm (360 mm) is five times the observed 100-year 24 h depth at Gilgit | Compared with the new IDF table | Described as a stress test; use the observed design storms for realistic runs |
| 20 | The first debris viewer drew stacked depth contours: stepped pillars, then smooth blobs | Rendering and looking at it | Replaced by a displaced surface mesh with a rubble material (Ch. {{ch:visualization}}) |
| 21 | The new viewer's controls were blank | A render showed an empty timeline; no console message | An in-page error hook exposed a `const` used before its definition; the block was moved earlier |
| 22 | Rocks were invisible | Render showed only release markers | The lit instanced material rejected a hand-made colour buffer; colours are now set through three.js and rocks are drawn larger |
| 23 | A rockfall fence counted nothing as stopped | The barrier test | Stops at a fence were not added to the stop map |
| 24 | The deposit rebuild failed when the geometry helper arrays were cropped twice | Rebuilding a scene from saved frames | `viewer.build` takes already-cropped arrays; the crop only locates them |
| 25 | A patch list for the viewer applied in the wrong order and failed loudly (three times) | The build raised "patch target missing" | Patches that touch the same text were merged; the failing check is kept on purpose so a changed SAILAB viewer cannot silently break the scene |
| 26 | My own document builder deleted the new visualisation chapter | Two chapter files shared a slug | Rewritten; chapter slugs must be unique |
| 27 | With land-cover root cohesion the Gilgit failing area rose from 1.2 to 4.4 km2 | Comparing runs | Reported as a sensitivity, not hidden (Ch. {{ch:access_export}}) |
