"""One-time preparation of the Pakistan-wide vector data used when a user draws an AOI.

  glim_pakistan.gpkg       GLiM lithology clipped to Pakistan (the source is 1.1 GB, world-wide, in an Eckert IV projection)
  rivers_pakistan.gpkg     HydroRIVERS Asia reaches inside Pakistan
  pakistan_outline.geojson Country outline, simplified, for the national map view
Output folder: datasets/raw/pakistan.   Usage: python -X utf8 scripts/prepare_pakistan.py
"""
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "landslide-platform/datasets/raw"
OUT = RAW / "pakistan"; OUT.mkdir(parents=True, exist_ok=True)
BB = (60.5, 23.3, 78.0, 37.3)

pk = gpd.read_file(ROOT / "Shapefiles/Pakistan/Pakistan.shp").to_crs(4326)
pk["geometry"] = pk.geometry.simplify(0.01)
pk.to_file(OUT / "pakistan_outline.geojson", driver="GeoJSON"); print("outline", len(pk))

if not (OUT / "glim_pakistan.gpkg").exists():
    gdb = RAW / "gilgit/glim/extracted/LiMW_GIS 2015.gdb"
    ref = gpd.read_file(RAW / "gilgit/glim/glim_gilgit_bbox.gpkg")           # carries the Eckert IV CRS
    bb = gpd.GeoSeries([box(*BB)], crs=4326).to_crs(ref.crs).total_bounds
    g = gpd.read_file(gdb, bbox=tuple(bb)); g.crs = ref.crs
    g.to_file(OUT / "glim_pakistan.gpkg", driver="GPKG"); print("glim", len(g))

if not (OUT / "rivers_pakistan.gpkg").exists():
    HR = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/river/HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as.shp"
    r = gpd.read_file(HR, bbox=BB)
    r = r[["DIS_AV_CMS", "UPLAND_SKM", "geometry"]]
    r.to_file(OUT / "rivers_pakistan.gpkg", driver="GPKG"); print("rivers", len(r))
