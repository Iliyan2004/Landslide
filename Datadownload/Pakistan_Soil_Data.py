from pathlib import Path
import argparse
import csv
import io
import os
import time
import zipfile

# PostgreSQL/PostGIS sets PROJ_LIB to its own (older) proj.db, which
# breaks rasterio/pyproj. Point PROJ at pyproj's bundled data instead.
import pyproj

os.environ["PROJ_DATA"] = pyproj.datadir.get_data_dir()
os.environ["PROJ_LIB"] = os.environ["PROJ_DATA"]

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests

from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import mapping


# ============================================================
# 1. OUTPUT FOLDER
# ============================================================

ROOT = (
    Path(__file__).resolve().parent
    / "Pakistan_Subsurface_Data"
)

ROOT.mkdir(exist_ok=True)


# ============================================================
# 2. DATASET URLS
# ============================================================

BOUNDARY_API = (
    "https://www.geoboundaries.org/api/current/"
    "gbOpen/PAK/ADM0/"
)

WOSIS_URL = (
    "https://files.isric.org/public/wosis_snapshot/"
    "WoSIS_2023_December.zip"
)

# Two alternative depth-to-bedrock raster sources.
# First source: millimetres
# Second source: centimetres

SOIL_SOURCES = [
    (
        "https://data.naturalcapitalalliance.stanford.edu/"
        "download/global/isric-soil-grids/depth_to_bedrock/"
        "isric_soil_absolute_depth_to_bedrock_250m_mm.tif",
        0.001,
    ),
    (
        "https://files.isric.org/soilgrids/former/"
        "2017-03-10/data/BDTICM_M_250m_ll.tif",
        0.01,
    ),
]


# ============================================================
# 3. DOWNLOAD PAKISTAN BOUNDARY
# ============================================================

def pakistan_boundary():

    output = ROOT / "pakistan_boundary.geojson"

    if not output.exists():

        print("Downloading Pakistan boundary...")

        response = requests.get(
            BOUNDARY_API,
            timeout=60
        )

        response.raise_for_status()

        information = response.json()

        download_url = information["gjDownloadURL"]

        response = requests.get(
            download_url,
            timeout=120
        )

        response.raise_for_status()

        output.write_bytes(response.content)

    boundary = gpd.read_file(output)

    boundary = boundary.to_crs("EPSG:4326")

    return boundary.geometry.union_all()


# ============================================================
# 4. DOWNLOAD PAKISTAN SOIL DEPTH / THICKNESS PROXY
# ============================================================

def download_soil_depth():

    output = (
        ROOT /
        "pakistan_depth_to_bedrock_250m.tif"
    )

    if output.exists():

        print("Soil depth raster already downloaded.")
        print(output)

        return

    polygon = pakistan_boundary()

    errors = []

    for url, conversion_factor in SOIL_SOURCES:

        try:

            print("\nAccessing soil depth dataset...")
            print(url)

            print("Extracting Pakistan region...")

            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_TIMEOUT="120",
            ):

                with rasterio.open(
                    "/vsicurl/" + url
                ) as source:

                    geometry = transform_geom(
                        "EPSG:4326",
                        source.crs,
                        mapping(polygon)
                    )

                    data, transform = mask(
                        source,
                        [geometry],
                        crop=True,
                        filled=False,
                        indexes=1
                    )

                    # Convert to metres

                    data = np.ma.masked_invalid(
                        data.astype("float32")
                    )

                    data *= conversion_factor

                    if data.count() == 0:

                        raise ValueError(
                            "No valid pixels found for Pakistan"
                        )

                    array = data.filled(
                        -9999
                    ).astype("float32")

                    metadata = source.profile.copy()

                    metadata.update(
                        driver="GTiff",
                        height=array.shape[0],
                        width=array.shape[1],
                        count=1,
                        dtype="float32",
                        transform=transform,
                        nodata=-9999,
                        compress="deflate",
                        predictor=3,
                        tiled=True,
                    )

                    with rasterio.open(
                        output,
                        "w",
                        **metadata
                    ) as destination:

                        destination.write(array, 1)

                        destination.set_band_description(
                            1,
                            "Estimated depth to bedrock (m)"
                        )

                        destination.update_tags(
                            source=url,
                            units="metres",
                            note=(
                                "Modelled depth to bedrock; "
                                "not measured borehole thickness"
                            )
                        )

            print("\nSOIL DEPTH DOWNLOAD SUCCESSFUL")
            print("Saved:", output)

            return

        except Exception as error:

            errors.append(str(error))

            print("\nSource failed:", error)
            print("Trying alternative source...")

    raise RuntimeError(
        "Both raster sources failed. "
        "The server may not support remote raster reading.\n"
        + "\n".join(errors)
    )


# ============================================================
# 5. DOWNLOAD GLOBAL WOSIS SOIL PROFILE DATABASE
# ============================================================

def download_archive():

    output = ROOT / "WoSIS_2023_December.zip"

    if output.exists() and zipfile.is_zipfile(output):

        print("WoSIS archive already downloaded.")

        return output

    temporary = output.with_suffix(".zip.part")

    print("\nDownloading WoSIS soil profile dataset...")
    print("Archive size: approximately 456 MB")

    # Only consecutive attempts that gain no bytes count as failures;
    # the server drops the connection every few MB, so progress
    # attempts are expected.
    max_attempts = 20

    attempt = 0

    while True:

        # Resume from whatever is already on disk
        downloaded = (
            temporary.stat().st_size if temporary.exists() else 0
        )

        start_size = downloaded

        headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}

        try:

            with requests.get(
                WOSIS_URL,
                headers=headers,
                stream=True,
                timeout=(30, 180)
            ) as response:

                if response.status_code == 416:
                    break  # already complete

                response.raise_for_status()

                # Server ignored Range: start over
                if downloaded and response.status_code != 206:
                    downloaded = 0

                # Total archive size, from Content-Range on a
                # resumed request or Content-Length on a fresh one
                content_range = response.headers.get("Content-Range", "")

                if "/" in content_range:
                    total = int(content_range.rsplit("/", 1)[1])
                else:
                    total = downloaded + int(
                        response.headers.get("Content-Length", 0)
                    )

                mode = "ab" if downloaded else "wb"

                next_progress = (
                    (downloaded // (50 * 1024 * 1024) + 1)
                    * 50 * 1024 * 1024
                )

                with temporary.open(mode) as file:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):

                        if chunk:

                            file.write(chunk)

                            downloaded += len(chunk)

                            if downloaded >= next_progress:

                                print(
                                    f"Downloaded: "
                                    f"{downloaded / 1000000:.0f} MB"
                                )

                                next_progress += 50 * 1024 * 1024

            # Stream can end early without raising; resume if short
            if total and downloaded < total:
                raise requests.exceptions.ConnectionError(
                    f"Stream ended at {downloaded:,} of {total:,} bytes"
                )

            break  # finished without error

        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as error:

            current = (
                temporary.stat().st_size if temporary.exists() else 0
            )

            attempt = 0 if current > start_size else attempt + 1

            print(
                f"Connection dropped at {current / 1000000:.0f} MB "
                f"(stalled attempts {attempt}/{max_attempts}): "
                f"{error}\nResuming..."
            )

            if attempt >= max_attempts:
                raise

            time.sleep(min(5 * max(attempt, 1), 30))

    if not zipfile.is_zipfile(temporary):

        raise RuntimeError(
            "WoSIS download is incomplete or invalid."
        )

    temporary.replace(output)

    print("WoSIS download completed.")

    return output


# ============================================================
# 6. READ TSV FILES INSIDE ZIP
# ============================================================

def read_tsv(archive, filename):

    matching_files = [
        name
        for name in archive.namelist()
        if name.lower().endswith(filename.lower())
    ]

    if not matching_files:

        raise FileNotFoundError(
            f"{filename} not found inside archive"
        )

    with archive.open(matching_files[0]) as file:

        with io.TextIOWrapper(
            file,
            encoding="utf-8-sig",
            errors="replace",
            newline=""
        ) as text:

            reader = csv.DictReader(
                text,
                delimiter="\t"
            )

            for row in reader:

                yield row


# ============================================================
# 7. EXPORT DATA TO CSV
# ============================================================

def save_csv(filename, records):

    if not records:

        print("No records found:", filename)

        return

    output = ROOT / filename

    with output.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(records[0])
        )

        writer.writeheader()

        writer.writerows(records)

    print(
        f"Saved {len(records):,} records:",
        output
    )


# ============================================================
# 8. EXTRACT PAKISTAN SOIL PROFILE DATA
# ============================================================

def download_soil_profiles():

    archive_path = download_archive()

    print("\nExtracting Pakistan soil observations...")

    with zipfile.ZipFile(archive_path) as archive:

        # --------------------------------------------
        # A. Pakistan soil observation sites
        # --------------------------------------------

        sites = [
            row
            for row in read_tsv(
                archive,
                "wosis_202312_sites.tsv"
            )
            if (
                row.get("country_name") or ""
            ).strip().casefold() == "pakistan"
        ]

        site_ids = {
            row["site_id"]
            for row in sites
        }

        print("Pakistan sites:", len(sites))

        # --------------------------------------------
        # B. Pakistan soil profiles
        # --------------------------------------------

        profiles = [
            row
            for row in read_tsv(
                archive,
                "wosis_202312_profiles.tsv"
            )
            if (
                row.get("site_id") in site_ids
                or (
                    row.get("country_name") or ""
                ).strip().casefold() == "pakistan"
                or (
                    row.get("country_iso3") or ""
                ).upper() == "PAK"
            )
        ]

        profile_ids = {
            row["profile_id"]
            for row in profiles
        }

        print("Pakistan profiles:", len(profiles))

        # --------------------------------------------
        # C. Pakistan soil horizons / layers
        # --------------------------------------------

        layers = [
            row
            for row in read_tsv(
                archive,
                "wosis_202312_layers.tsv"
            )
            if row.get("profile_id") in profile_ids
        ]

        print("Pakistan soil layers:", len(layers))

    # --------------------------------------------
    # Save CSV outputs
    # --------------------------------------------

    save_csv(
        "pakistan_wosis_sites.csv",
        sites
    )

    save_csv(
        "pakistan_wosis_profiles.csv",
        profiles
    )

    save_csv(
        "pakistan_wosis_layers.csv",
        layers
    )

    # --------------------------------------------
    # Convert soil profile points to GeoPackage
    # --------------------------------------------

    if not profiles:

        print("No Pakistan profiles found.")

        return

    dataframe = pd.DataFrame(profiles)

    if (
        "longitude" not in dataframe.columns
        or "latitude" not in dataframe.columns
    ):

        raise ValueError(
            "Profile coordinates not available."
        )

    dataframe["longitude"] = pd.to_numeric(
        dataframe["longitude"],
        errors="coerce"
    )

    dataframe["latitude"] = pd.to_numeric(
        dataframe["latitude"],
        errors="coerce"
    )

    dataframe = dataframe.dropna(
        subset=["longitude", "latitude"]
    )

    dataframe = dataframe[
        dataframe["longitude"].between(-180, 180)
        & dataframe["latitude"].between(-90, 90)
    ]

    if not dataframe.empty:

        geo_dataframe = gpd.GeoDataFrame(
            dataframe,
            geometry=gpd.points_from_xy(
                dataframe.longitude,
                dataframe.latitude
            ),
            crs="EPSG:4326"
        )

        output = (
            ROOT /
            "pakistan_wosis_profile_points.gpkg"
        )

        geo_dataframe.to_file(
            output,
            layer="soil_profiles",
            driver="GPKG"
        )

        print("\nSOIL PROFILE POINTS EXPORTED")

        print("Total points:", len(geo_dataframe))

        print("Saved:", output)

    print(
        "\nNOTE: WoSIS profiles are soil observations,"
        " not deep geophysical borehole logs."
    )


# ============================================================
# 9. MAIN EXECUTION
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--only",
        choices=["all", "soil", "boreholes"],
        default="all"
    )

    args = parser.parse_args()

    jobs = []

    if args.only in ("all", "soil"):

        jobs.append(
            ("SOIL DEPTH", download_soil_depth)
        )

    if args.only in ("all", "boreholes"):

        jobs.append(
            ("SOIL PROFILE POINTS", download_soil_profiles)
        )

    for label, job in jobs:

        try:

            print("\n================================")
            print(label)
            print("================================")

            job()

        except Exception as error:

            print(f"\nERROR in {label}: {error}")

    print("\n================================")
    print("PROCESS FINISHED")
    print("================================")

    print("Output folder:", ROOT)