# Scripts

Run from the project root, for example `~/flood/venv/bin/python scripts/validate_pga.py`. Each script's first lines say what it reads and writes. Results go to `docs/validation/`.

**Build national products and data**: `build_national.py` (90 m physics tiles), `build_districts.py`, `build_slope30.py`, `build_vs30_pk.py`, `build_glim_pk.py`, `build_registries.py`, `prepare_pakistan.py`, `infra_data.py`

**Download data**: `download_ground_data.py`, `download_soil_texture.py`, `download_bedrock_depth.py`, `download_hourly_climate.py`, `download_shakemaps_pk.py`, `download_shakemaps.py`, `download_s2_change.py`, `download_gilgit_data.py`

**Calibration**: `calibrate_stability.py`, `calibrate_physics.py`, `calibrate_ground.py`

**Validation**: `validate_simulation.py` (V1 to V45), `validate_spatial.py`, `validate_rain_threshold.py`, `validate_forecasts.py`, `validate_quake_landslides.py`, `validate_pga.py`, `validate_dem_change.py`, `validate_design_storms_aal.py`, `check_runout_relations.py`, `check_volume_area.py`, `check_population_vs_pbs.py`, `check_new_data.py`, `summarise_inventory.py`, `analyze_hourly_climate.py`

**Cross-checks against external tools**: `check_gmpe_oq.py` (OpenQuake), `check_landlab_slope.py` (Landlab), `compare_iverson.py` and `compare_trigrs.py` (USGS TRIGRS)

**Reports and demos**: `build_landlab_techref.py` (technical reference), `run_area_demo.py`, `run_pipeline.py`, `shot.py` (screenshots of pages and 3D scenes)

**Original Gilgit dashboard (kept because `validate_simulation.py` uses it)**: `aoi_*.py`, `build_dashboard_page.py`, `dashboard_template.html`, `validation_harness.js`, `_impact*.js`, `page_check.py`
