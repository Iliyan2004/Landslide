"""District census attributes (Pakistan Bureau of Statistics, 2023 census; datasets/external/pbs) for exposure and damage.

  housing_mix(district)  shares of pakka, semi-pakka and kacha households (permanent, mixed, mud / temporary construction)
  hh_size(district)      average household size
  density(district)      people per km2 (Pop_2023_Total / Area)
A building is assigned to the district polygon that contains its centroid. The census tables cover 142 districts and have NO row for Gilgit-Baltistan or Azad Kashmir (23 of
the 164 district polygons, the highest-landslide areas): for those the national mean is used and the result says so. The household shares are district-wide, not
per building: a mud-built hamlet in a pakka district is still counted as the district mix."""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

PBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "datasets", "external", "pbs")
_cache = {}
CLASSES = ("pakka", "semi", "kacha")


def _tables():
    if "t" not in _cache:
        import geopandas as gpd
        pop = pd.read_csv(os.path.join(PBS, "district_population.csv")); hs = pd.read_csv(os.path.join(PBS, "district_housing_type.csv"))
        for d in (pop, hs):
            d["key"] = d["name"].str.lower().str.strip()
        g = gpd.read_file(os.path.join(PBS, "district_shp", "District_Boundary.shp")).to_crs(4326); g["key"] = g["name"].str.lower().str.strip()
        mix = {}
        for _, r in hs.iterrows():
            t = float(r["Pakka_HH_AllLocalities"] + r["Semi_Pakka_HH_AllLocalities"] + r["Kacha_HH_AllLocalities"])
            if t > 0:
                mix[r["key"]] = (r["Pakka_HH_AllLocalities"] / t, r["Semi_Pakka_HH_AllLocalities"] / t, r["Kacha_HH_AllLocalities"] / t)
        tot = hs[["Pakka_HH_AllLocalities", "Semi_Pakka_HH_AllLocalities", "Kacha_HH_AllLocalities"]].sum(); nat = tuple(float(x) for x in (tot / tot.sum()))
        info = {r["key"]: {"hh": float(r["Avg_HH_Size"]), "density": float(r["Pop_Density"]), "pop": float(r["Pop_2023_Total"]), "area_km2": float(r["Area_sq_km"])} for _, r in pop.iterrows()}
        _cache["t"] = {"geo": g[["key", "name", "geometry"]], "mix": mix, "national_mix": nat, "info": info, "national_hh": float(np.average(pop["Avg_HH_Size"], weights=pop["Pop_2023_Total"]))}
    return _cache["t"]


def districts_for(lon, lat):
    """District key per point (None outside every polygon)."""
    import geopandas as gpd
    T = _tables(); pts = gpd.GeoDataFrame({"i": np.arange(len(lon))}, geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, T["geo"], how="left", predicate="within").drop_duplicates("i").set_index("i")
    return [None if pd.isna(k) else k for k in j["key"].reindex(range(len(lon))).values]


def housing_mix(key):
    T = _tables(); m = T["mix"].get(key)
    return (m, True) if m is not None else (T["national_mix"], False)


def hh_size(key):
    T = _tables(); i = T["info"].get(key)
    return (i["hh"], True) if i else (T["national_hh"], False)


def density(key):
    i = _tables()["info"].get(key); return i["density"] if i else None


def population_field(grid, valid):
    """People per analysis cell from the district density (census population / district area) where the population raster has no data (the south). Uniform within a
    district, so it ignores where people actually live: a total for the district area, not a map of settlements. Cells in no census district (or Gilgit-Baltistan and
    Azad Kashmir, which have no row) stay NaN. Returns (array, share of valid cells filled)."""
    from pyproj import Transformer
    ny, nx = valid.shape; r, c = np.where(valid)
    if len(r) == 0:
        return np.full(valid.shape, np.nan, "float32"), 0.0
    xs, ys = grid["affine"] * (c + 0.5, r + 0.5); lon, lat = Transformer.from_crs(grid["crs"], 4326, always_xy=True).transform(xs, ys)
    keys = districts_for(np.asarray(lon), np.asarray(lat)); cell_km2 = grid["resolution_m"] ** 2 / 1e6; out = np.full(valid.shape, np.nan, "float32"); n = 0
    for k, (ri, ci) in zip(keys, zip(r, c)):
        d = density(k) if k else None
        if d is not None:
            out[ri, ci] = d * cell_km2; n += 1
    return out, n / len(r)
