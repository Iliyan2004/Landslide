# Gilgit City minimal landslide demo configuration

This is a **configuration starter**, not a downloaded dataset or a functioning simulated result. It follows the supplied landslide-platform methodology and the `landslide-platform.zip` example input schema.

## Included (3 functional files)
- `configs/gilgit_demo.yaml`: editable paths, model selections, and presentation toggles.
- `data/aois/gilgit_demo_aoi.geojson`: **illustrative rectangular area**, not an administrative/city boundary; replace it with your actual Gilgit study AOI.
- `check_demo_inputs.py`: light file-existence checker; does not process or download data.

## Placement
Copy `configs/gilgit_demo.yaml` into your existing `landslide-platform/configs/`, copy the AOI to `landslide-platform/data/aois/`, and copy `check_demo_inputs.py` to the platform root. Keep your existing datasets in their current folders and paste their **actual paths** into the YAML. On Windows, use forward slashes (`D:/GIS/data/dem.tif`) to avoid escape issues. `data_root` is descriptive and is **not automatically prefixed** to input paths.

## Check

```powershell
pip install pyyaml
python check_demo_inputs.py --config configs/gilgit_demo.yaml
```

## Suggested small presentation
1. AOI + DEM hillshade/slope
2. GLiM/land-cover/historical landslide overlay (if files available)
3. Legacy susceptibility screening, labelled uncalibrated
4. Optional physical FS if measured parameters or clearly labelled scenario ranges exist
5. Downloadable map and reproducibility manifest

**Important integration limitation:** Your earlier `landslide-platform.zip` has a configuration example, but its existing `scripts/run_pipeline.py` currently generates a synthetic DEM and does not parse this YAML. Simply copying the configuration will **not** automatically power the website. Connect a real-data loader/API adapter to these path mappings before presenting computational model results. The custom `datasets` and `demo` sections are forward-looking optional keys, not existing API capabilities.

**Do not** present a 30 m raster as higher-resolution data. Do not enable sediment capacity without discharge/channel geometry/riverbed D50 or runout without a credible source and source-volume assumptions. Missing geotechnical measurements must remain unavailable or explicitly scenario-based.
