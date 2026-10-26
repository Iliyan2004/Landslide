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

Tested on a synthetic valley with a toy objective: the corridor follows the downhill path, the budget is respected, and the optimiser lowers the objective. **Not yet run on a real area.**
