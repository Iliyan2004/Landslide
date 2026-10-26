# System Architecture

## 2.1 Components

| Component | Where | Role |
|---|---|---|
| Web app | `backend/landslide/app/server.py`, `routes.py` | Flask, port 5070, serves the page, tiles, jobs, runs |
| Page | `app/static/app.html` | SAILAB-style layout: 2D map over a 3D pane, right-column panels, four tier tabs |
| Pipeline (Tier 1) | `app/pipeline.py` | AOI to arrays: terrain, ML layer, stability ensemble, exposure |
| Engine (Tiers 3 and 4) | `engine/trigger.py`, `flow.py`, `flow_torch.py`, `run.py` | Failure timing, runout solver (numba and CUDA), impacts |
| Run packaging | `app/runs.py`, `app/viewer.py` | Persist artefacts, build the 3D scene, Tier 2 library |
| Rainfall and layers | `app/rainfall.py`, `app/layers.py` | Rain sources, buildings, roads, facilities |
| Physics core (older) | `models/`, `data/preprocessing/`, `gates.py` | Infinite slope, Green-Ampt, Newmark, empirical runout, acceptance gates |
| Calibration | `calibration/` | Inventory, rain features, spatial validation, statistics |
| Scripts | `scripts/` | National builder, district statistics, slope raster, validation experiments, this document |

It runs on SAILAB's Python environment (`~/flood/venv`), which already has xarray, zarr, duckdb, weasyprint and CUDA torch. Only the environment is shared; no SAILAB code is imported.

## 2.2 Jobs, caching and idempotence

A heavy request starts a background thread and returns a job id; the page polls `/runs/<job>/progress.json`. One heavy job runs at a time because the server is shared. A run's id is the hash of its polygon, parameters and code version, so identical requests return the stored result. Each run directory holds `summary.json`, `manifest.json` (sources, grid, parameters, warnings), `arrays.npz`, `frames.npz` and `mapbox_3d.html`.

## 2.3 Hardware

The machine is an NVIDIA GB10 with unified memory shared by about ten users, often with only 1 to 2 GB of GPU memory free. The code therefore falls back to the CPU on any GPU failure, and releases cached GPU memory after each job. No temperature guard is applied, by the owner's decision; `LANDSLIDE_TEMP_GUARD=1` re-enables one.

## 2.4 Separation from flooding

LANDLAB has no flood tiers, no flood solver, no discharge or inundation outputs. Debris flows are modelled as a dense granular-fluid mixture with Coulomb-turbulent resistance (Ch. {{ch:runout_solver}}), not as water. River basins and districts appear only as ways to choose an area.
