"""USGS ShakeMap PGA grids for all of Pakistan and its surroundings, stored compactly.

Query: ComCat events with a ShakeMap product, magnitude 5.5 or more, since 1973, inside 57-81 E, 20-41 N (Pakistan plus a 3 degree margin,
because large events beyond the border shake the country). For each event the grid.xml is downloaded, its PGA field (%g) is stored as a
float16 array with its grid origin and spacing in datasets/raw/pakistan/shakemap/<event_id>.npz, and the original XML is deleted.
Index: datasets/raw/pakistan/shakemap_index.csv (id, date, magnitude, place, depth, grid bounds, maximum PGA).
Existing .npz files are skipped, so the script can be re-run.   Usage: python -X utf8 scripts/download_shakemaps_pk.py
"""
import csv, datetime as dt, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from download_shakemaps import get, read_grid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/external/shakemap"
API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BBOX = dict(minlongitude=57, maxlongitude=81, minlatitude=20, maxlatitude=41)


def one(e):
    eid, p = e["id"], e["properties"]
    f = OUT / f"{eid}.npz"
    if f.exists(): return eid, "skip"
    try:
        det = get(p["detail"]).json()["properties"]["products"]["shakemap"][0]["contents"]
        tmp = Path(tempfile.mkdtemp()) / "grid.xml"
        tmp.write_bytes(get(det["download/grid.xml"]["url"]).content)
        lon, lat, pga, pgv, mmi = read_grid(tmp)
        tmp.unlink(); tmp.parent.rmdir()
        np.savez_compressed(f, lon0=lon[0], lat0=lat[0], dlon=float(np.median(np.diff(lon))), dlat=float(np.median(np.diff(lat))),
                            pga=np.where(np.isfinite(pga), pga, np.nan).astype(np.float16), mmi_max=float(np.nanmax(mmi)))
        return eid, "ok"
    except Exception as ex:
        return eid, f"FAILED {ex}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ev = get(API, params=dict(format="geojson", minmagnitude=5.5, starttime="1973-01-01", producttype="shakemap", orderby="time", limit=1000, **BBOX)).json()["features"]
    print(len(ev), "events with a ShakeMap")
    with ThreadPoolExecutor(4) as ex:
        for n, (eid, st) in enumerate(ex.map(one, ev), 1):
            print(n, len(ev), eid, st, flush=True)
    rows = []
    for e in ev:
        f = OUT / f"{e['id']}.npz"
        if not f.exists(): continue
        z = np.load(f); p = e["properties"]; pga = z["pga"].astype(float)
        ny, nx = pga.shape
        rows.append(dict(event_id=e["id"], date=dt.datetime.fromtimestamp(p["time"] / 1000, dt.UTC).date().isoformat(), mag=p["mag"], place=p["place"],
                         depth_km=e["geometry"]["coordinates"][2], lon_min=float(z["lon0"]), lat_min=float(z["lat0"]),
                         lon_max=float(z["lon0"] + (nx - 1) * z["dlon"]), lat_max=float(z["lat0"] + (ny - 1) * z["dlat"]), pga_max=round(float(np.nanmax(pga)), 2), mmi_max=round(float(z["mmi_max"]), 1)))
    with open(OUT.parent / "shakemap_index.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("wrote index with", len(rows), "events")


if __name__ == "__main__":
    main()
