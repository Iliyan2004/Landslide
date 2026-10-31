# Barriers and Automatic Placement

## The barrier model

A barrier (check dam, retaining wall) is a polyline drawn across the flow path with a height and width. It is applied by raising the bed under the wall in the runout solver, so the flow stops against it, ponds, or overtops it as the physics decides; no special rule makes it hold.

**Height is measured above the ground immediately upslope of the wall.** On a grid the bed falls by tan(slope) x cell size across one cell, so the wall cell is raised by `height + tan(slope) x cell`. Without this a wall lower than the ground drop across one cell does not even stand above its upslope neighbour: a test with a "6 m wall" on a 0.35 slope and 20 m cells let 90% of a flow pass before the rule was added. With it, the 6 m wall holds back more than 80% of a 2 m deep, 11 m/s slug and a 12 m wall holds back more than a 6 m wall. Overtopping by momentum (run-up v2/2g is about 6 m at 11 m/s) is physical and is not suppressed.

A wall narrower than a cell is widened to one cell. Barriers are not drawn in the 3D scene; they appear on the 2D map, and their effect shows in the flow.

## Automatic placement

The optimiser searches the position along the main flow corridor, the height (2 to 12 m) and the length (40 to 400 m) of up to four barriers with differential evolution, under a hard limit on the number of simulations.

- The corridor is the steepest-descent path from the failing cell nearest the centroid of the baseline run's failing cells, followed while the baseline flow reached 0.3 m.
- **There is no surrogate model:** every candidate is a full simulation (about 24 s on the GPU for the reference area), so 30 simulations take about 12 minutes. The result is a good option under the budget, not a proven optimum.
- The objective is direct loss plus a blocked-road penalty plus a wall cost; **the wall cost is a user input because no cost data exist here.** With a zero cost the optimiser will pick the largest walls, and the page says so.

Tested on a synthetic valley with a toy objective: the corridor follows the downhill path, the budget is respected, and the optimiser lowers the objective.

## First run on a real area

The same 57 km2 Gilgit area, 60 mm/h triangular storm for 12 h, 2 barriers, a budget of 16 simulations (`area_demo.json`, 37 minutes). The first attempt returned barriers of zero length: cells outside the area had been filled with a high elevation, so the pit-filling step flooded the whole area flat and no flow path existed. That bug is fixed (`flow_corridor` now leaves outside cells empty so they act as outlets; the corridor is 7 cells, 210 m). The result:

| | Baseline | With the best 2 barriers |
|---|---|---|
| Direct loss (PKR M) | {{area_demo.json:optimise_barriers.result.baseline.loss_pkr|0}} | {{area_demo.json:optimise_barriers.result.optimised.loss_pkr|0}} |
| Buildings with damage state 3 or worse | {{area_demo.json:optimise_barriers.result.baseline.buildings_ds3|0}} | {{area_demo.json:optimise_barriers.result.optimised.buildings_ds3|0}} |
| Impacted area (km2) | {{area_demo.json:optimise_barriers.result.baseline.impacted_km2|1}} | {{area_demo.json:optimise_barriers.result.optimised.impacted_km2|1}} |

Two barriers (one 11 m high and about 400 m long, one 3 m high) cut the loss by about 2.7%. That is small because the slide here is 8.6 km2 of failing hillside sending 21 million m3 across a 26 km2 area: the failure is spread over thousands of release cells, so a barrier on one flow path intercepts only a share of it. The optimiser works as a tool, but this storm scenario is too large for barriers to matter; it is meant for one gully-sized failure, and the scenario is useful mainly as a limit on what barriers can do. With a 16 simulation budget the result is "a better option", not an optimum.
