"""SoilGrids 2.0 sand / silt / clay (0-30 cm, depth-weighted mean, g/kg) on a 250 m UTM 43N grid covering gilgit_dem.tif.
Used to give cohesion and friction angle a spatial pattern instead of one regional value.   Output: datasets/raw/gilgit/soil_texture_250m.tif"""
import io, requests, rasterio, ee
from pathlib import Path
DEM = r"D:\Downloads\CMIP6\gilgit_dem.tif"; OUT = Path(r"D:\Downloads\datasets\raw\gilgit\soil_texture_250m.tif")
ee.Initialize(project="bamboo-storm-482319-s1")
with rasterio.open(DEM) as r:
    b = r.bounds; crs = r.crs.to_string()
W = (5 * 1 + 10 * 1 + 15 * 1) / 30.0
def mean030(name):
    im = ee.Image(f"projects/soilgrids-isric/{name}_mean")
    return im.select(f"{name}_0-5cm_mean").multiply(5).add(im.select(f"{name}_5-15cm_mean").multiply(10)).add(im.select(f"{name}_15-30cm_mean").multiply(15)).divide(30).rename(name)
img = ee.Image.cat([mean030("sand"), mean030("silt"), mean030("clay")]).float()
reg = ee.Geometry.Rectangle([b.left, b.bottom, b.right, b.top], crs, False)
url = img.getDownloadURL(dict(region=reg, crs=crs, scale=250, format="GEO_TIFF"))
rs = requests.get(url, timeout=300); rs.raise_for_status()
OUT.write_bytes(rs.content)
with rasterio.open(OUT) as s:
    a = s.read(); print(s.shape, s.count, [float(x) for x in a.reshape(3, -1).mean(1)])
