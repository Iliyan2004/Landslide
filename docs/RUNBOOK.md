# Runbook

## 0. Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api,geo,fetch,ml]"        # geo extras need GDAL
cp .env.example .env                              # fill credentials (server-side only)
make registries && make test && make demo
```

## 1. Licence audit (before ANY deployment)
Open `docs/licensing_register.csv`; for each source you will use record licence, redistribution and commercial-integration
permission, attribution text, checker and date; set `licence_checked: true` in `docs/data_registry.yaml`.
Free access ≠ unrestricted reuse (OpenTopography commercial terms, Open-Meteo commercial plan, ODbL, Open Buildings terms).

## 2. Data staging (§2.1)
1. **Baseline (once):** Pakistan boundary, GLiM (manual download via the DOI in D04), Copernicus DEM tiles, SoilGrids layers via WCS/WebDAV (not the beta REST API), WorldCover, HydroRIVERS/BASINS, Geofabrik OSM, inventories (COOLR D11, D13, D40).
   `from landslide.data.fetchers.sources import REGISTRY; REGISTRY["copernicus_dem_glo30"]().fetch(bbox, "datasets/raw/D01")`
2. **Historical archives:** Sentinel-2, Landsat, CHIRPS 20-40 yr, event IMERG, ERA5-Land, USGS events/ShakeMaps.
3. **Per AOI:** subset stored data first; fetch only gaps; cache by source version + AOI hash (`manifest.cache_key`).
4. Record version, acquisition date, CRS, units, uncertainty, sha256 into `data_registry.yaml` for every raw file.

## 3. Model runs
| Goal | Required inputs | Command / endpoint |
|---|---|---|
| Rapid screening | slope %, GLiM class (+ inventory for ML) | `landslide.models.susceptibility.legacy` / `statistical` |
| Rainfall stability | DEM slope, rainfall, soil ranges (explicit) | `POST /api/models/stability` |
| Earthquake | PGA or acceleration series + strengths | `POST /api/models/seismic` |
| Runout | source mask + volume + alpha range | `POST /api/models/runout` |
| Sediment | RUSLE factors and/or hydraulics + measured d50 + width | `POST /api/models/sediment` |
Missing essentials → job state `insufficient_data`/`gate_rejected` with the exact reasons. Nothing is silently defaulted.

## 4. Wiring real rasters (what this scaffold does NOT do for you)
The physics modules are array-based. Production use needs a thin loader (rasterio window read → metric-CRS reproject → grid_spec
(`aoi.grid_spec`) → COG/NetCDF writer) in `data/preprocessing/`. `run_pipeline.py` shows the call order with a synthetic DEM.
The `/api/models/susceptibility` endpoint returns 501 until a feature stack + inventory are wired.

## 5. External engines
r.avaflow, Richards, TRIGRS: build a pinned container image, validate against a documented benchmark, then set
`engines.<name>.image`. Adapters run with `--network=none` and refuse to start with missing inputs.

## 6. Acceptance
Walk `docs/LANDSLIDE_PLATFORM_FULL_METHODOLOGY.md` §13 checklist; `make test` must be green.
