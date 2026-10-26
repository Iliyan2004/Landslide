"""Download USGS ShakeMap grids (PGA, PGV, MMI) for earthquakes near Gilgit and summarise the shaking at the study area.

Source: USGS ComCat (https://earthquake.usgs.gov/fdsnws/event/1/), product 'shakemap', file download/grid.xml.
Output: D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit/shakemap/<event_id>/{grid.xml,info.json}, plus shakemap_summary.csv.
Existing files are skipped, so the script can be re-run.

Usage: python scripts/download_shakemaps.py [--minmag 5.5] [--radius-km 400]
"""
import argparse, csv, datetime as dt, json, re, sys
from pathlib import Path

import numpy as np
import requests
import rasterio

OUT = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit/shakemap")
DEM = Path(__file__).resolve().parents[2] / "gilgit_dem.tif"
API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
CENTRE = (35.92, 74.31)  # Gilgit


def get(url, retries=4, **kw):
    for k in range(retries):
        try:
            r = requests.get(url, timeout=120, **kw)
            r.raise_for_status()
            return r
        except Exception:
            if k == retries - 1:
                raise


def read_grid(path):
    """Return lon, lat, pga(%g), pgv(cm/s), mmi as 2-D arrays from a ShakeMap grid.xml."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    fields = re.findall(r'<grid_field index="(\d+)" name="(\w+)"', txt)
    names = {n: int(i) - 1 for i, n in fields}
    body = txt.split("<grid_data>")[1].split("</grid_data>")[0]
    a = np.fromstring(body, sep=" ").reshape(-1, len(names))
    lon, lat = a[:, names["LON"]], a[:, names["LAT"]]
    ulon, ulat = np.unique(lon), np.unique(lat)
    shape = (len(ulat), len(ulon))
    def f(n):
        out = np.full(shape, np.nan)
        out[np.searchsorted(ulat, lat), np.searchsorted(ulon, lon)] = a[:, names[n]]
        return out
    return ulon, ulat, f("PGA"), f("PGV"), f("MMI")


def sample(ulon, ulat, grid, lon, lat):
    from scipy.interpolate import RegularGridInterpolator
    return RegularGridInterpolator((ulat, ulon), grid, bounds_error=False, fill_value=np.nan)(np.column_stack([lat, lon]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minmag", type=float, default=5.5)
    ap.add_argument("--radius-km", type=float, default=400)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ev = get(API, params=dict(format="geojson", latitude=CENTRE[0], longitude=CENTRE[1], maxradiuskm=a.radius_km, minmagnitude=a.minmag,
                              starttime="1973-01-01", producttype="shakemap", orderby="time", limit=500)).json()["features"]
    print(len(ev), "events with a ShakeMap")
    from pyproj import Transformer
    with rasterio.open(DEM) as r:
        b = r.bounds
        t = Transformer.from_crs(r.crs, 4326, always_xy=True)
        xs, ys = np.meshgrid(np.linspace(b.left, b.right, 40), np.linspace(b.bottom, b.top, 40))
        glon, glat = t.transform(xs.ravel(), ys.ravel())
    rows = []
    for e in ev:
        eid, p = e["id"], e["properties"]
        d = OUT / eid
        d.mkdir(exist_ok=True)
        try:
            if not (d / "grid.xml").exists():
                det = get(p["detail"]).json()["properties"]["products"]["shakemap"][0]["contents"]
                (d / "grid.xml").write_bytes(get(det["download/grid.xml"]["url"]).content)
                if "download/info.json" in det:
                    (d / "info.json").write_bytes(get(det["download/info.json"]["url"]).content)
            lon, lat, pga, pgv, mmi = read_grid(d / "grid.xml")
            sp, sm = sample(lon, lat, pga, glon, glat), sample(lon, lat, mmi, glon, glat)
            ok = np.isfinite(sp)
            rows.append(dict(event_id=eid, date=dt.datetime.fromtimestamp(p["time"] / 1000, dt.UTC).date().isoformat(), mag=p["mag"], place=p["place"],
                             depth_km=e["geometry"]["coordinates"][2], covers_aoi_pct=round(100 * ok.mean(), 1),
                             pga_max_pctg=round(float(np.nanmax(sp)), 2) if ok.any() else "", pga_mean_pctg=round(float(np.nanmean(sp)), 2) if ok.any() else "",
                             mmi_max=round(float(np.nanmax(sm)), 1) if ok.any() else ""))
            print(eid, p["mag"], rows[-1]["pga_max_pctg"], "%g")
        except Exception as ex:
            print("FAILED", eid, ex, file=sys.stderr)
    rows.sort(key=lambda r: -(r["pga_max_pctg"] or 0))
    with open(OUT.parent / "shakemap_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print("wrote", OUT.parent / "shakemap_summary.csv")


if __name__ == "__main__":
    main()
