# Landslide Modelling Platform

Implementation of `docs/LANDSLIDE_PLATFORM_FULL_METHODOLOGY.md` (v1.0): one web interface around several distinct hazard
engines (susceptibility, rainfall stability, seismic, runout, sediment, exposure, monitoring), with explicit data gates,
scenario-ensemble uncertainty and per-run manifests.

**Status: working, tested physics/gating core + API/frontend scaffold. Not a finished product** — see "Not done" below.

## Quick start
```bash
make registries    # regenerate docs/data_registry.yaml + licensing_register.csv from the methodology table
make test          # 115 tests (stdlib unittest; also runs under pytest)
make demo          # synthetic-DEM end-to-end run -> runs/<id>/{manifest,summary}.json + arrays.npz
make api           # needs: pip install -e ".[api]"
make frontend      # needs node 20
```

## Web app (SAILAB-style, whole of Pakistan)
Runs on SAILAB's own venv (xarray, zarr, duckdb, weasyprint, CUDA torch):
```bash
~/flood/venv/bin/python landslide_app.py          # http://<host>:5070   (Flask + Mapbox GL; token in .env, git-ignored)
nice ~/flood/venv/bin/python scripts/build_national.py   # tiled 90 m national physics product (GPU first), resumable
~/flood/venv/bin/python scripts/build_districts.py       # 164-district statistics (re-run after the national build says DONE)
```
**Layout and functions mirror SAILAB:** header, 2D Mapbox map above an animated Mapbox 3D pane (SAILAB's own viewer assets, patched for
debris flow), resizers, right column of panels: draw/upload area (zip/GeoJSON), district discovery, HydroSHEDS basins, rainfall context
(Open-Meteo, ERA5 wettest event, I-D thresholds, antecedent index), live monitoring (forecast watch -> auto physics run, webhook),
four tier tabs, run history, compare runs, PDF report.

| Tier | What it does |
|---|---|
| 1 Screening | national CNN/DNN susceptibility (north only; elsewhere NODATA), terrain, stability ensemble, population exposure |
| 2 Instant | rain-ladder library of FS maps, slider interpolation, critical-rain map |
| 3 Physics | rainfall (design / forecast / recent / ERA5 / CHIRPS / CSV) -> Green-Ampt -> FS(t) -> failure timing -> **time-stepped Voellmy runout** (entrainment, pore-pressure fluidisation) -> depth/speed/deposit over time -> buildings (Open Buildings), roads, hospitals/schools damage and loss |
| 5 Mitigate | nature-based levers (planting, regrading, drainage), barriers drawn on the map, ranking of combinations, optional automatic barrier placement, average annual loss from observed-IDF design storms |
| 4 Quake | magnitude + epicentre -> Joyner-Boore 1981 PGA from a Wells-Coppersmith rupture on the nearest mapped fault -> Newmark (Jibson 2007) -> coseismic failures -> same runout engine |

- **Compute order: GPU, then RAM, then CPU.** The runout solver and the stability ensemble run on CUDA (CUDA graphs; `torch.compile`
  fused kernels for grids >= 300k cells: 0.27 ms/step at 640k cells vs 2.7 ms on the 20-core numba path); frames and rasters sit in
  host RAM; numba/NumPy is the automatic fallback (also on GPU out-of-memory, the GPU is shared). No temperature guard by user decision
  (`LANDSLIDE_TEMP_GUARD=1` re-enables it).
- **Rule used everywhere:** a rain/quake event can only mobilise slopes that were stable before it (FS >= 1 at the baseline water table)
  and that carry soil (<= 45 deg). Bare rock and already-unstable ground are counted separately, not as storm failures.
- Engine checks (tests/test_engine.py): mass conservation, well-balanced rest, Voellmy steady speed (<5 % at dt 0.1 s), rest below the
  friction slope, entrainment mass balance, GPU == CPU.
- Honest limits: soil strength, friction (mu, xi), fragility medians and unit cost are scenario values, none calibrated (`screening_only`);
  quake PGA has no site amplification; rainfall is spatially uniform over the area; nothing is validated against observed events.

**Also:** earthquake and debris visualisation, access/isolation impacts, GIS export, `docs/USER_GUIDE.md`.

**Landslide only.** Flooding is a separate product (SAILAB) and nothing here is coupled to it.

**Technical reference:** `docs/LANDLAB_Technical_Reference.{pdf,html,md}`, rebuilt by `~/flood/venv/bin/python scripts/build_landlab_techref.py` from `docs/landlab/*.md`; its numbers are read from `docs/validation/*.json`, so it cannot drift from results (missing results render as "pending").

**Compute-heavy work is run only on request** (spatial validation, physics and runout calibration, CMIP6 climate multiplier, average annual loss, automatic barrier placement, mitigated-versus-unmitigated pairs).

## Layout
```
docs/       methodology, data_registry.yaml (D01-D40), model_registry.yaml (M01-M22), licensing_register.csv,
            validation_protocol.md, RUNBOOK.md
configs/    inputs.example.yaml (§3.1 schema), legacy_susceptibility.yaml (editable M01 table)
scripts/    build_registries.py, run_pipeline.py
backend/landslide/
  units.py gates.py manifest.py errors.py
  data/preprocessing/  terrain, aoi, soil, inventory, forcing
  data/fetchers/       base + 9 source fetchers (URL builders unit-tested; network paths NOT tested)
  models/              susceptibility, stability(+bishop, ensemble), infiltration, seismic, runout(+adapters), sediment, exposure, monitoring
  api/                 service.py (pure), jobs.py, main.py (FastAPI §7.2 endpoints)
backend/tests/         70 tests: analytic checks, §6.2 physics guards, §11.2 integrity tests
frontend/              React + MapLibre scaffold (AOI, rainfall stability, results)
datasets/ runs/        immutable raw / prepared / indices / user_private; per-run outputs
```

## Design rules enforced in code
- Unknown geotechnical inputs are rejected (`GateError`/`InsufficientData`), never defaulted; ranges are explicit scenarios.
- Outputs carry `not_for_engineering_design`, `calibration_status`, `validation_status`; "fraction FS<1" is labelled conditional on priors, never a probability.
- NODATA never becomes "low risk"; flat slope ≠ FS 0; per-width bedload never reported as volume; no damage without hazard-specific fragility.
- Rainfall exceedance = watch tier only; alerts are `experimental_unvalidated` until hindcast-validated.
- Runs are idempotent (cache key = model + version + source hashes + AOI hash + params).

## Not done / needs you
1. **Raster I/O** (rasterio window reads, reprojection, COG/NetCDF writers, tiles) — modules take numpy arrays.
2. **Licence audit** — every source is `licence_checked: false`; fetcher URL patterns need provider verification.
3. **Credentialed fetchers** (CDS, Earthdata, CDSE) need accounts; Sentinel fetcher is a stub; GLiM must be fetched manually.
4. **External engines** (r.avaflow, Richards, TRIGRS) are adapters only; Janbu/Spencer, SINMAP, CNN scar segmentation, LHASA benchmark not implemented.
5. **M01 table** is placeholder (not copied from SAILAB) — reconcile and expert-review.
6. **Susceptibility API endpoint** returns 501 until a feature stack + inventory are wired.
7. **API (FastAPI) and frontend were syntax-checked only**, not run (deps unavailable offline); Docker/compose untested.
8. **Local calibration** against Pakistani inventories/events (pilot basins, §10) is the scientific work that remains.
