"""Concrete fetchers. URL builders are pure functions (unit-tested offline). URL PATTERNS ARE FROM PUBLISHED CONVENTIONS
AND MUST BE VERIFIED against each provider before deployment; licence_checked in data_registry.yaml gates production use.
Credentialed sources (CDS, Earthdata, CDSE, GEE, OpenTopography) read tokens from the environment only."""
from __future__ import annotations
import json, math
from pathlib import Path
from urllib.parse import urlencode
from .base import Fetcher, FetchResult, http_download, require_env
from ...errors import SourceUnavailable


# ---------- pure URL/tile builders -------------------------------------------------------------------
def copernicus_dem_tile_names(bbox):
    """GLO-30 tiles are 1x1 degree, named by SW corner."""
    names = []
    for lat in range(math.floor(bbox[1]), math.ceil(bbox[3])):
        for lon in range(math.floor(bbox[0]), math.ceil(bbox[2])):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            stem = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
            names.append(f"https://copernicus-dem-30m.s3.amazonaws.com/{stem}/{stem}.tif")
    return names


def worldcover_tile_urls(bbox, year=2021, ver="v200"):
    """ESA WorldCover tiles are 3x3 degree, named by SW corner (multiples of 3)."""
    urls = []
    for lat in range(int(math.floor(bbox[1] / 3) * 3), math.ceil(bbox[3]), 3):
        for lon in range(int(math.floor(bbox[0] / 3) * 3), math.ceil(bbox[2]), 3):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            t = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
            urls.append(f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/{ver}/{year}/map/ESA_WorldCover_10m_{year}_{ver}_{t}_Map.tif")
    return urls


def usgs_event_query_url(start, end, bbox, min_mag=4.5):
    q = dict(format="geojson", starttime=start, endtime=end, minlatitude=bbox[1], maxlatitude=bbox[3],
             minlongitude=bbox[0], maxlongitude=bbox[2], minmagnitude=min_mag, orderby="time")
    return "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urlencode(q)


def chirps_daily_url(date):
    return (f"https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/{date.year}/"
            f"chirps-v2.0.{date:%Y.%m.%d}.tif.gz")


def open_meteo_url(lat, lon, hours=72, past_days=3):
    q = dict(latitude=lat, longitude=lon, hourly="precipitation,temperature_2m,soil_moisture_0_to_7cm",
             forecast_days=max(1, math.ceil(hours / 24)), past_days=past_days, timezone="UTC")
    return "https://api.open-meteo.com/v1/forecast?" + urlencode(q)


GEOFABRIK_PAKISTAN = "https://download.geofabrik.de/asia/pakistan-latest.osm.pbf"


# ---------- fetchers ---------------------------------------------------------------------------------
class CopernicusDEM(Fetcher):
    source_id, registry_ids = "copernicus_dem_glo30", ("D01",)
    def fetch(self, bbox, dest, **kw):
        dest = Path(dest); files, hashes = [], {}
        for u in copernicus_dem_tile_names(bbox):
            p = dest / u.rsplit("/", 1)[1]
            try:
                hashes[p.name] = http_download(u, p); files.append(str(p))
            except SourceUnavailable as e:
                if "404" in str(e):      # ocean tiles do not exist
                    continue
                raise
        if not files:
            raise SourceUnavailable("no DEM tiles retrieved for AOI")
        return FetchResult(self.source_id, "GLO-30_public", files, hashes, self.now(),
                           ["DSM: buildings/trees influence slope (§4.2)"])


class WorldCover(Fetcher):
    source_id, registry_ids = "esa_worldcover_2021_v200", ("D07",)
    def fetch(self, bbox, dest, **kw):
        dest = Path(dest); files, hashes = [], {}
        for u in worldcover_tile_urls(bbox):
            p = dest / u.rsplit("/", 1)[1]; hashes[p.name] = http_download(u, p); files.append(str(p))
        return FetchResult(self.source_id, "v200_2021", files, hashes, self.now())


class UsgsEvents(Fetcher):
    source_id, registry_ids = "usgs_comcat", ("D19",)
    def fetch(self, bbox, dest, start="2000-01-01", end="2026-12-31", min_mag=4.5, **kw):
        p = Path(dest) / "usgs_events.geojson"
        h = http_download(usgs_event_query_url(start, end, bbox, min_mag), p)
        return FetchResult(self.source_id, f"query_{end}", [str(p)], {p.name: h}, self.now())


class Geofabrik(Fetcher):
    source_id, registry_ids = "osm_geofabrik_pakistan", ("D23",)
    def fetch(self, bbox, dest, **kw):
        p = Path(dest) / "pakistan-latest.osm.pbf"
        h = http_download(GEOFABRIK_PAKISTAN, p, timeout=3600)
        return FetchResult(self.source_id, "latest", [str(p)], {p.name: h}, self.now(), ["ODbL attribution required"])


class OpenMeteo(Fetcher):
    source_id, registry_ids = "open_meteo_forecast", ("D17",)
    def fetch(self, bbox, dest, hours=72, **kw):
        lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
        p = Path(dest) / "open_meteo.json"
        h = http_download(open_meteo_url(lat, lon, hours), p)
        issued = json.loads(p.read_text()).get("generationtime_ms")
        return FetchResult(self.source_id, "model_forecast", [str(p)], {p.name: h}, self.now(),
                           [f"record issuance/validity times; check commercial terms; generationtime_ms={issued}"])


class ChirpsDaily(Fetcher):
    source_id, registry_ids = "chirps_v2_daily", ("D15",)
    def fetch(self, bbox, dest, dates=(), **kw):
        files, hashes = [], {}
        for d in dates:
            p = Path(dest) / f"chirps-v2.0.{d:%Y.%m.%d}.tif.gz"; hashes[p.name] = http_download(chirps_daily_url(d), p); files.append(str(p))
        return FetchResult(self.source_id, "v2.0", files, hashes, self.now())


class Era5Land(Fetcher):
    source_id, registry_ids, needs_credentials = "era5_land_hourly", ("D16",), True
    def fetch(self, bbox, dest, year=None, month=None, variables=None, **kw):
        require_env("CDSAPI_URL", "CDSAPI_KEY")
        try:
            import cdsapi
        except ImportError as e:
            raise SourceUnavailable("pip install cdsapi") from e
        p = Path(dest) / f"era5land_{year}{month:02d}.nc"; p.parent.mkdir(parents=True, exist_ok=True)
        cdsapi.Client().retrieve("reanalysis-era5-land", {
            "variable": variables or ["total_precipitation", "2m_temperature", "volumetric_soil_water_layer_1",
                                      "volumetric_soil_water_layer_2", "snow_depth_water_equivalent"],
            "year": str(year), "month": f"{month:02d}", "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)], "area": [bbox[3], bbox[0], bbox[1], bbox[2]],
            "data_format": "netcdf"}, str(p))
        from ..base_hash import sha
        return FetchResult(self.source_id, f"{year}-{month:02d}", [str(p)], {p.name: sha(p)}, self.now(),
                           ["total_precipitation is ACCUMULATED: use api_index.deaccumulate_era5"])


class Imerg(Fetcher):
    source_id, registry_ids, needs_credentials = "gpm_imerg", ("D14",), True
    def fetch(self, bbox, dest, start=None, end=None, run="Final", **kw):
        require_env("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD")
        try:
            import earthaccess
        except ImportError as e:
            raise SourceUnavailable("pip install earthaccess") from e
        earthaccess.login(strategy="environment")
        res = earthaccess.search_data(short_name="GPM_3IMERGHH", temporal=(start, end), bounding_box=tuple(bbox))
        files = earthaccess.download(res, str(dest))
        return FetchResult(self.source_id, f"V07_{run}", [str(f) for f in files], {}, self.now(),
                           ["Final run vs near-real-time Early/Late differ; record which"])


class SentinelCDSE(Fetcher):
    source_id, registry_ids, needs_credentials = "sentinel2_l2a_cdse", ("D09", "D10"), True
    def fetch(self, bbox, dest, **kw):
        require_env("CDSE_USERNAME", "CDSE_PASSWORD")
        raise NotImplementedError("Implement CDSE STAC/OData search + download; apply SCL cloud/snow QA (§4.6)")


REGISTRY = {c.source_id: c for c in (CopernicusDEM, WorldCover, UsgsEvents, Geofabrik, OpenMeteo, ChirpsDaily,
                                     Era5Land, Imerg, SentinelCDSE)}
