#!/usr/bin/env python3
"""Clip GLiM v1.1 (Hartmann & Moosdorf 2012) to Pakistan and rasterise first-level lithology classes onto a 0.002 deg grid.
Output: datasets/external/glim/glim_pk.tif (uint8 class id, 0 = none) and glim_classes.json (id -> GLiM code + name)."""
import json
from pathlib import Path
import numpy as np, geopandas as gpd, rasterio
from rasterio import features
from rasterio.transform import from_origin
from pyproj import Transformer
ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "datasets/external/glim"
W, S, E, N = 60.5, 23.5, 77.9, 37.2
NAMES = {"su": "unconsolidated sediments", "ss": "siliciclastic sedimentary", "sm": "mixed sedimentary", "sc": "carbonate sedimentary", "py": "pyroclastic",
         "sy": "evaporites", "va": "acid volcanic", "vi": "intermediate volcanic", "vb": "basic volcanic", "pa": "acid plutonic", "pi": "intermediate plutonic",
         "pb": "basic plutonic", "mt": "metamorphic", "ev": "evaporites", "wb": "water bodies", "ig": "ice and glaciers", "nd": "no data"}
t = Transformer.from_crs(4326, "ESRI:54012", always_xy=True)
x0, y0 = t.transform(W, S); x1, y1 = t.transform(E, N)
xs, ys = zip(*[t.transform(x, y) for x in np.linspace(W, E, 20) for y in (S, N)]); bb = (min(xs) - 5e4, min(ys + (y0,)) - 5e4, max(xs) + 5e4, max(ys + (y1,)) + 5e4)
g = gpd.read_file(next(D.glob("*.gdb")), layer="GLiM_export", bbox=bb)
print("features", len(g), flush=True)
g = g.to_crs(4326); g["code"] = g["xx"].astype(str).str.strip().str.lower()
codes = sorted(g["code"].unique()); cid = {c: i + 1 for i, c in enumerate(codes)}
res = 0.002; w = int(round((E - W) / res)); h = int(round((N - S) / res)); tr = from_origin(W, N, res, res)
arr = features.rasterize(((geom, cid[c]) for geom, c in zip(g.geometry, g["code"])), out_shape=(h, w), transform=tr, fill=0, dtype="uint8")
with rasterio.open(D / "glim_pk.tif", "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8", crs="EPSG:4326", transform=tr, compress="deflate") as o:
    o.write(arr, 1)
cls = {str(i): {"code": c, "name": NAMES.get(c, c), "share": float((arr == i).mean())} for c, i in cid.items()}
json.dump(cls, open(D / "glim_classes.json", "w"), indent=1); print(json.dumps(cls, indent=1))
