"""Build docs/gilgit_landslide_dashboard.html from local files only (no synthetic data).

Inputs: gilgit_dem.tif, COOLR inventory, USGS catalogue, and D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit
(WorldCover, WorldPop, Open Buildings, GEM faults, CHIRPS, satellite embeddings 2017 and 2024).
"""
import base64, io, json, re
from pathlib import Path
import geopandas as gpd, numpy as np, pandas as pd, rasterio
from PIL import Image
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit")
DEM = ROOT / "gilgit_dem.tif"
INV = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/landslide_inventory/landslide_inventory.gpkg"
EQ = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/earthquake_hazard/usgs_events.csv"
TEMPLATE = Path(__file__).with_name("dashboard_template.html")
OUT = ROOT / "landslide-platform/docs/gilgit_landslide_dashboard.html"
F = 6
SLOPE_PCT_BINS = [15, 35, 70]
COLS = np.array([[96, 160, 110], [222, 196, 84], [222, 126, 52], [176, 40, 40]], float)
enc = lambda a: base64.b64encode(np.asarray(a).astype("uint8").tobytes()).decode()

def png(a):
    b = io.BytesIO(); Image.fromarray(a.astype("uint8"), "RGBA").save(b, "PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode()

r = rasterio.open(DEM); z = r.read(1).astype("float64"); nd = z == r.nodata; z[nd] = np.nan
dx = r.res[0]; gy, gx = np.gradient(np.where(nd, np.nanmean(z), z), dx)
slope_pct = np.hypot(gx, gy) * 100
cls = np.digitize(slope_pct, SLOPE_PCT_BINS); cls[nd] = -1; valid = ~nd
sl = np.arctan(np.hypot(gx, gy)); asp = np.arctan2(-gx, gy); az, alt = np.radians(315), np.radians(40)
hs = np.clip(np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp), 0, 1) * 255
h2, w2 = r.height // F, r.width // F
blocks = lambda a: a[:h2 * F, :w2 * F].reshape(h2, F, w2, F)
hs_d = blocks(hs).mean(axis=(1, 3))
nd_d = blocks(nd).mean(axis=(1, 3)) > 0.5
blk = cls[:h2 * F, :w2 * F].reshape(h2, F, w2, F).transpose(0, 2, 1, 3).reshape(h2, w2, F * F)
cls_d = np.apply_along_axis(lambda v: np.bincount(v + 1, minlength=5).argmax() - 1, 2, blk)
g = hs_d[..., None] * np.ones(3)
hill = np.zeros((h2, w2, 4)); hill[..., :3] = g; hill[..., 3] = np.where(nd_d, 0, 255)
sp = np.zeros((h2, w2, 4))
for k in range(4): sp[cls_d == k, :3] = COLS[k]
sp[..., :3] = 0.62 * sp[..., :3] + 0.38 * g; sp[..., 3] = np.where(cls_d >= 0, 255, 0)
sdeg = np.degrees(sl); sdeg[nd] = np.nan
sd_d = np.nanmean(blocks(sdeg), axis=(1, 3))
z_d = np.nanmean(blocks(z), axis=(1, 3))
slope_deg = np.where(nd_d, 255, np.clip(np.round(np.nan_to_num(sd_d)), 0, 89))
ELEV0, ELEVSTEP = 1100, 26
elev = np.where(nd_d, 255, np.clip(np.round((np.nan_to_num(z_d) - ELEV0) / ELEVSTEP), 0, 254))

b = r.bounds
px = lambda x, y: [(x - b.left) / (b.right - b.left), (b.top - y) / (b.top - b.bottom)]

# ---- land cover (mode per block)
lc = rasterio.open(DATA / "worldcover_2021.tif").read(1)
lcb = lc[:h2 * F, :w2 * F].reshape(h2, F, w2, F).transpose(0, 2, 1, 3).reshape(h2, w2, F * F) // 10
lc_d = np.apply_along_axis(lambda v: np.bincount(v, minlength=11).argmax(), 2, lcb)  # class code / 10
lc_d = np.where(nd_d, 0, lc_d)
lc_area = {int(k): float(v) for k, v in zip(*np.unique(lc[valid], return_counts=True))}
lc_area = {k: v * dx * dx / 1e6 for k, v in lc_area.items()}

# ---- population: WorldPop 100 m values were resampled to 26.6 m, so rescale to people per fine cell
pop = rasterio.open(DATA / "worldpop_2020.tif").read(1).astype("float64")
pop = np.where(np.isfinite(pop) & (pop > 0), pop, 0) * (dx / 100.0) ** 2
pop_d = blocks(pop).sum(axis=(1, 3))
pop_total = float(pop[valid].sum())

# ---- buildings: centroid count per coarse cell
bg = gpd.read_file(DATA / "open_buildings_v3.geojson").to_crs(r.crs)
cen = bg.geometry.centroid
cc = np.floor((cen.x.values - b.left) / (dx * F)).astype(int)
rr = np.floor((b.top - cen.y.values) / (dx * F)).astype(int)
ok = (cc >= 0) & (cc < w2) & (rr >= 0) & (rr < h2)
bld = np.zeros((h2, w2), int); np.add.at(bld, (rr[ok], cc[ok]), 1)
bld_d = np.clip(bld, 0, 255)

# ---- faults
fl = gpd.read_file(DATA / "gem_active_faults_pakistan.gpkg").to_crs(r.crs)
ext = box(b.left, b.bottom, b.right, b.top)
faults = []
for _, w in fl.iterrows():
    gm = w.geometry.intersection(ext)
    if gm.is_empty: continue
    for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
        if ln.geom_type != "LineString": continue
        ln = ln.simplify(150)
        faults.append(dict(name=w["name"] or "unnamed", slip=str(w["slip_type"]), catalog=str(w["catalog_name"]), km=round(ln.length / 1000, 1),
                           xy=[[round(v, 4) for v in px(x, y)] for x, y in ln.coords]))
fl_near = fl.cx[b.left - 50000:b.right + 50000, b.bottom - 50000:b.top + 50000]

# ---- rainfall (CHIRPS areal mean)
ch = pd.read_csv(DATA / "chirps_daily_aoi_mean.csv", parse_dates=["date"]).set_index("date")["precip_mm"]
ann = ch.groupby(ch.index.year).max()
full = ch[ch.index.year < 2026]
rain = dict(first=str(ch.index.min().date()), last=str(ch.index.max().date()), years=[int(y) for y in ann.index], annmax=[round(float(v), 1) for v in ann.values],
            monthly=[round(float(v), 1) for v in (full.groupby(full.index.month).sum() / full.index.year.nunique()).values],
            max1=round(float(ch.max()), 1), max1_date=str(ch.idxmax().date()), max3=round(float(ch.rolling(3).sum().max()), 1), max7=round(float(ch.rolling(7).sum().max()), 1),
            p99_wet=round(float(ch[ch > 1].quantile(.99)), 1), wet_frac=round(float((ch > 1).mean()), 3))

# ---- satellite embeddings: 2017->2024 change (fine-scale cosine distance) and similarity to inventory scars
def dequant(q):
    q = q.astype("float32"); return np.sign(q) * (q / 127.5) ** 2
src17 = rasterio.open(DATA / "embedding_2017_int8.tif"); src24 = rasterio.open(DATA / "embedding_2024_int8.tif")
emb17 = np.zeros((64, h2, w2), np.float32); chg = np.zeros((h2, w2), np.float32)
STRIP = 40  # coarse rows per strip
for r0 in range(0, h2, STRIP):
    r1 = min(h2, r0 + STRIP); win = ((r0 * F, r1 * F), (0, w2 * F))
    a = dequant(src17.read(window=win)); c = dequant(src24.read(window=win))
    bad = (src17.read(1, window=win) == -128) | (src24.read(1, window=win) == -128)
    na = np.linalg.norm(a, axis=0) + 1e-9; nc = np.linalg.norm(c, axis=0) + 1e-9
    cosd = 1 - (a * c).sum(0) / (na * nc); cosd[bad] = np.nan
    chg[r0:r1] = np.nanmean(cosd.reshape(r1 - r0, F, w2, F), axis=(1, 3))
    a[:, bad] = np.nan
    emb17[:, r0:r1] = np.nanmean(a.reshape(64, r1 - r0, F, w2, F), axis=(2, 4))
vmask = ~nd_d & np.isfinite(chg) & np.isfinite(emb17[0])
En = emb17 / (np.linalg.norm(emb17, axis=0) + 1e-9)
En = np.where(vmask[None], En, 0)

inv = gpd.read_file(INV).to_crs(r.crs).cx[b.left - 50000:b.right + 50000, b.bottom - 50000:b.top + 50000]
pts = []
for _, w in inv.iterrows():
    u, v = px(w.geometry.x, w.geometry.y)
    pts.append(dict(u=round(u, 4), v=round(v, 4), inside=bool(0 <= u <= 1 and 0 <= v <= 1), date=str(w.event_date), cat=str(w.landslide_category),
                    trig=str(w.landslide_trigger), size=str(w.landslide_size), title=str(w.event_title)[:70], desc=str(w.event_description)[:240], loc=str(w.location_description)[:80], acc=str(w.location_accuracy), src=str(w.source_link)[:140],
                    fat=(float(w.fatality_count) if pd.notna(w.fatality_count) else None), inj=(float(w.injury_count) if pd.notna(w.injury_count) else None), photo=str(w.photo_link)[:140] if pd.notna(w.photo_link) else '', lon=round(float(w.longitude), 4), lat=round(float(w.latitude), 4)))
cells = [(int(p["v"] * h2), int(p["u"] * w2)) for p in pts if p["inside"]]
cells = [(i, j) for i, j in cells if vmask[i, j]]
def template(use):
    t = np.mean([En[:, i, j] for i, j in use], axis=0); return t / (np.linalg.norm(t) + 1e-9)
def pct_rank(s, mask):
    v = s[mask]; order = v.argsort().argsort() / (len(v) - 1); out = np.full(s.shape, np.nan); out[mask] = order; return out
loo = []
for k, (i, j) in enumerate(cells):
    use = [c for c in cells if max(abs(c[0] - i), abs(c[1] - j)) > 5]
    if not use: continue
    s = np.tensordot(template(use), En, axes=1)
    loo.append(float((s[vmask] < s[i, j]).mean()))
slope_base = [float((sd_d[vmask] < sd_d[i, j]).mean()) for i, j in cells]
sim = np.tensordot(template(cells), En, axes=1)
sim_pct = pct_rank(sim, vmask); chg_pct = pct_rank(chg, vmask)
to8 = lambda a: np.where(np.isfinite(a), np.round(np.nan_to_num(a) * 254), 255)

q = pd.read_csv(EQ)
qg = gpd.GeoDataFrame(q, geometry=gpd.points_from_xy(q.longitude, q.latitude), crs=4326).to_crs(r.crs).cx[b.left:b.right, b.bottom:b.top]
qs = [dict(u=round(px(p.x, p.y)[0], 4), v=round(px(p.x, p.y)[1], 4), m=float(m), d=float(d), t=pd.to_datetime(t, unit="ms").strftime("%Y-%m-%d"))
      for p, m, d, t in zip(qg.geometry, qg.magnitude, qg.depth_km, qg.time)]

# ---- USGS ShakeMap PGA for the strongest events at the study area
import sys
sys.path.insert(0, str(Path(__file__).parent))
shake = []
smcsv = DATA / "shakemap_summary.csv"
if smcsv.exists():
    from download_shakemaps import read_grid, sample
    from pyproj import Transformer
    S0 = pd.read_csv(smcsv)
    S0 = S0[S0.covers_aoi_pct >= 99]
    recent_id = S0.sort_values("date").iloc[-1].event_id          # most recent event whose ShakeMap covers the area
    S = pd.concat([S0[S0.event_id == recent_id], S0.sort_values("pga_mean_pctg", ascending=False).head(6)]).drop_duplicates("event_id")
    tr = Transformer.from_crs(r.crs, 4326, always_xy=True)
    X, Y = np.meshgrid(b.left + (np.arange(w2) + .5) * dx * F, b.top - (np.arange(h2) + .5) * dx * F)
    LON, LAT = tr.transform(X.ravel(), Y.ravel())
    for _, e in S.iterrows():
        lo, la, pga, pgv, mmi = read_grid(DATA / "shakemap" / e.event_id / "grid.xml")
        v = sample(lo, la, pga, LON, LAT).reshape(h2, w2)
        arr = np.where(nd_d | ~np.isfinite(v), 255, np.clip(np.round(np.nan_to_num(v) * 10), 0, 254))
        shake.append(dict(id=e.event_id, date=e.date, mag=float(e.mag), place=str(e.place), depth=float(e.depth_km), pga_max=float(e.pga_max_pctg),
                          pga_mean=float(e.pga_mean_pctg), mmi_max=float(e.mmi_max), recent=bool(e.event_id == recent_id), pga=enc(arr)))
        print("shake", e.event_id, e.date, e.mag, "pga mean", e.pga_mean_pctg, "max cell value", float(np.nanmax(v)))

# ---- GLiM lithology -> legacy screening score (configs/legacy_susceptibility.yaml, placeholder ratings pending expert review)
from rasterio.features import rasterize
from rasterio.transform import from_origin
RANK = {"su": 5, "ss": 3, "sm": 3, "sc": 2, "py": 4, "va": 2, "vi": 2, "vb": 2, "pa": 1, "pi": 1, "pb": 1, "mt": 3, "ev": 3}
gl = gpd.read_file(DATA / "glim" / "glim_gilgit_bbox.gpkg").to_crs(r.crs)
codes = sorted(gl.xx.unique()); idmap = {c: i + 1 for i, c in enumerate(codes)}
tfc = from_origin(b.left, b.top, dx * F, dx * F)
lit = rasterize(((g_, idmap[x_]) for g_, x_ in zip(gl.geometry, gl.xx)), out_shape=(h2, w2), transform=tfc, fill=0, dtype="uint8")
inv_idmap = {v: k for k, v in idmap.items()}
cellkm2 = (dx * F / 1000) ** 2
lit_area = {inv_idmap[i]: float(((lit == i) & ~nd_d).sum() * cellkm2) for i in inv_idmap}
rank = np.full((h2, w2), np.nan)
for i, c_ in inv_idmap.items():
    if c_ in RANK: rank[lit == i] = RANK[c_]
scored = ~nd_d & np.isfinite(rank)
score = 0.6 * (cls_d / 3.0) + 0.4 * ((rank - 1) / 4.0)
scls = np.where(scored, np.digitize(score, [0.25, 0.5, 0.75]), -1)
scr = np.zeros((h2, w2, 4))
for k in range(4): scr[scls == k, :3] = COLS[k]
unk = ~nd_d & ~scored
scr[unk, :3] = (110, 120, 128)
scr[..., :3] = 0.62 * scr[..., :3] + 0.38 * g; scr[..., 3] = np.where(~nd_d, 255, 0)
scr_pct = [float((scls == k).sum() / scored.sum() * 100) for k in range(4)]
unk_pct = float(unk.sum() / (~nd_d).sum() * 100)
sv = [float((score[scored] < score[i, j]).mean()) for i, j in cells if scored[i, j]]
sv_slope = [float((cls_d[scored] < cls_d[i, j]).mean() + 0.5 * (cls_d[scored] == cls_d[i, j]).mean()) for i, j in cells if scored[i, j]]
scr_val = dict(n=len(sv), median=float(np.median(sv)) if sv else None, slope_median=float(np.median(sv_slope)) if sv_slope else None,
               in_unknown=int(sum(1 for i, j in cells if unk[i, j])))

# ---- OpenStreetMap basemap (roads, rivers, lakes, places) from the local Geofabrik extract
OSM = DATA / "osm" / "pakistan.gpkg"
ll = (73.85, 35.5, 74.95, 36.35)
ext_geom = box(b.left, b.bottom, b.right, b.top)
pq = lambda x, y: [int(round(v * 10000)) for v in px(x, y)]
def lines(gdf, tol):
    out = []
    for gm in gdf.geometry:
        gm = gm.intersection(ext_geom)
        if gm.is_empty: continue
        for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if ln.geom_type != "LineString" or ln.length < 150: continue
            ln = ln.simplify(tol)
            out.append([v for x_, y_ in ln.coords for v in pq(x_, y_)])
    return out
rd = gpd.read_file(OSM, layer="gis_osm_roads_free", bbox=ll).to_crs(r.crs)
major = rd[rd.fclass.isin(["motorway", "trunk", "primary", "secondary", "tertiary"])]
minor = rd[rd.fclass.isin(["unclassified", "residential", "track", "track_grade2", "track_grade3"])]
ww = gpd.read_file(OSM, layer="gis_osm_waterways_free", bbox=ll).to_crs(r.crs)
wa = gpd.read_file(OSM, layer="gis_osm_water_a_free", bbox=ll).to_crs(r.crs)
wa = wa[wa.fclass.isin(["water", "reservoir", "river", "dock"])]
pl = gpd.read_file(OSM, layer="gis_osm_places_free", bbox=ll).to_crs(r.crs)
polys = []
for gm in wa.geometry:
    gm = gm.intersection(ext_geom)
    for pg in (gm.geoms if hasattr(gm, "geoms") else [gm]):
        if pg.geom_type == "Polygon" and pg.area > 2e4:
            polys.append([v for x_, y_ in pg.simplify(80).exterior.coords for v in pq(x_, y_)])
places = []
for _, w in pl.iterrows():
    if not w["name"] or w.fclass not in ("city", "town", "village", "hamlet", "suburb"): continue
    u, v = px(w.geometry.x, w.geometry.y)
    if 0 <= u <= 1 and 0 <= v <= 1:
        places.append(dict(n=str(w["name"]), c=str(w.fclass), u=round(u, 4), v=round(v, 4)))
basemap = dict(major=lines(major, 80), minor=lines(minor, 100), rivers=lines(ww[ww.fclass.isin(["river", "canal"])], 100),
               streams=lines(ww[ww.fclass == "stream"], 120), lakes=polys, places=places)
print("basemap", {k: len(v) for k, v in basemap.items()}, "screening", [round(p, 1) for p in scr_pct], "unknown %", round(unk_pct, 1), scr_val)

# ---- 53 m heightfield for the 3D view (2x2 mean of the DEM, whole metres, horizontal then vertical delta, zlib)
import zlib
h53, w53 = r.height // 2, r.width // 2
z53 = np.nanmean(z[:h53 * 2, :w53 * 2].reshape(h53, 2, w53, 2), axis=(1, 3))
z53 = np.round(np.where(np.isfinite(z53), z53, np.nanmin(z53))).astype(np.int16)
dd = np.diff(z53.astype(np.int32), axis=1, prepend=0); dd = np.diff(dd, axis=0, prepend=0).astype(np.int16)   # prepend 0 keeps the first column and row absolute
elev53 = dict(w=w53, h=h53, res=dx * 2, x0=b.left, y1=b.top, z=base64.b64encode(zlib.compress(dd.astype("<i2").tobytes(), 9)).decode())
print("elev53", z53.shape, len(elev53["z"]) // 1024, "KB")

# ---- extra OSM-style map content: land use, glaciers, peaks
luq = gpd.read_file(OSM, layer="gis_osm_landuse_a_free", bbox=ll).to_crs(r.crs)
gla = gpd.read_file(OSM, layer="gis_osm_natural_a_free", bbox=ll).to_crs(r.crs)
pk = gpd.read_file(OSM, layer="gis_osm_natural_free", bbox=ll).to_crs(r.crs)
def polys_of(gdf, tol, minarea):
    out = []
    for gm, fc in zip(gdf.geometry, gdf.fclass):
        gm = gm.intersection(ext_geom)
        for pg in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if pg.geom_type == "Polygon" and pg.area > minarea:
                out.append([fc, [v for x_, y_ in pg.simplify(tol).exterior.coords for v in pq(x_, y_)]])
    return out
basemap["landuse"] = polys_of(luq, 100, 3e4)
basemap["glaciers"] = [p[1] for p in polys_of(gla, 120, 1e5)]
basemap["peaks"] = [dict(n=str(w["name"]), u=round(px(w.geometry.x, w.geometry.y)[0], 4), v=round(px(w.geometry.x, w.geometry.y)[1], 4))
                    for _, w in pk.iterrows() if w.fclass == "peak" and w["name"] and 0 <= px(w.geometry.x, w.geometry.y)[0] <= 1 and 0 <= px(w.geometry.x, w.geometry.y)[1] <= 1]
print("landuse", len(basemap["landuse"]), "glaciers", len(basemap["glaciers"]), "peaks", len(basemap["peaks"]))

# ---- rainfall intensity-duration threshold fitted to the rain-triggered report dates (CHIRPS area mean)
def _ts(v):
    v = int(float(v)); return pd.Timestamp(v, unit="ms" if v > 1e11 else "s")
DUR = [1, 2, 3, 5, 7, 10]
_roll = {d: ch.rolling(d).sum() / d for d in DUR}                    # mean intensity over the last d days, mm/day
ev_rows = []
for p in pts:
    if not p["inside"] or not re.search(r"rain|downpour|monsoon|flood", p["trig"].lower()): continue
    try: dte = _ts(p["date"]).normalize()
    except Exception: continue
    if not (ch.index.min() <= dte <= ch.index.max()): continue
    I = {d: float(max(_roll[d].get(dte, np.nan), _roll[d].get(dte + pd.Timedelta(days=1), np.nan))) for d in DUR}
    if all(np.isfinite(v) for v in I.values()): ev_rows.append((str(dte.date()), I))
ev_dates = [pd.Timestamp(d_) for d_, _ in ev_rows]
near = np.zeros(len(ch), bool)
for d_ in ev_dates: near |= (np.abs((ch.index - d_).days) <= 5)
months = ch.index.month; base_mask = (months >= 4) & (months <= 9) & ~near                  # non-event days in the report season
def _auc(pos, neg):
    neg = np.sort(neg); lo = np.searchsorted(neg, pos, "left"); hi = np.searchsorted(neg, pos, "right")
    return float(np.mean((lo + 0.5 * (hi - lo)) / len(neg)))
per = []
for d in DUR:
    pos = np.array([I[d] for _, I in ev_rows]); neg = _roll[d].values[base_mask]; neg = neg[np.isfinite(neg)]
    cand = np.unique(np.concatenate([pos, np.quantile(neg, np.linspace(.5, .999, 200))]))
    tss = [(np.mean(pos >= c) - np.mean(neg >= c), c) for c in cand]; best, c_ = max(tss)
    per.append(dict(d=d, thr=float(c_), pod=float(np.mean(pos >= c_)), pofd=float(np.mean(neg >= c_)), tss=float(best), auc=_auc(pos, neg)))
bestd = max(per, key=lambda r_: r_["auc"])
exc = np.zeros(len(ch), bool)
for r_ in per: exc |= (_roll[r_["d"]].values >= r_["thr"])
yrs = (ch.index.max() - ch.index.min()).days / 365.25
rthr = dict(per=per, best_d=bestd["d"], n_events=len(ev_rows), exceed_days_per_year=float((_roll[bestd["d"]].values >= bestd["thr"]).sum() / yrs), durations=DUR,
            events=[dict(date=dt_, I={str(d): round(v, 2) for d, v in I.items()}) for dt_, I in ev_rows])
print("rain threshold:", [(r_["d"], round(r_["thr"], 2), round(r_["pod"], 2), round(r_["pofd"], 3), round(r_["auc"], 2)) for r_ in per])

# ---- shaking amplification classes: topographic position (crest / mid-slope / valley) and soft-ground class from GLiM
from scipy import ndimage as _ndi
zf = np.where(np.isfinite(z_d), z_d, np.nanmean(z_d))
tpi = zf - _ndi.uniform_filter(zf, size=5, mode="nearest")                   # 5 x 5 cells = 800 m neighbourhood
tpi_cls = np.where(nd_d, 255, np.where(tpi > 40, 2, np.where(tpi < -40, 0, 1)))
soft = {"su": 2, "ss": 1, "sm": 1, "py": 1}
site_cls = np.zeros((h2, w2), int)
for i_, c_ in inv_idmap.items():
    if c_ in soft: site_cls[lit == i_] = soft[c_]
site_cls = np.where(nd_d, 255, site_cls)
amp_stats = dict(crest_pct=float((tpi_cls[tpi_cls != 255] == 2).mean() * 100), valley_pct=float((tpi_cls[tpi_cls != 255] == 0).mean() * 100),
                 soft_pct=float((site_cls[site_cls != 255] == 2).mean() * 100), semi_pct=float((site_cls[site_cls != 255] == 1).mean() * 100))
print("amplification classes", {k: round(v, 1) for k, v in amp_stats.items()})

# ---- spatial soil strength from SoilGrids texture (0-30 cm): clay raises cohesion, sand raises friction angle; both relative to the regional median
soil_enc_c = soil_enc_p = None
SOILTIF = DATA / "soil_texture_250m.tif"
if SOILTIF.exists():
    with rasterio.open(SOILTIF) as sr:
        sa = sr.read().astype(float); sa[~np.isfinite(sa) | (sa < 0)] = np.nan
        jj_, ii_ = np.meshgrid(np.arange(w2), np.arange(h2))
        xs_ = b.left + (jj_ + .5) * F * dx; ys_ = b.top - (ii_ + .5) * F * dx
        rr_, cc_ = rasterio.transform.rowcol(sr.transform, xs_.ravel(), ys_.ravel())
        rr_ = np.clip(rr_, 0, sr.height - 1).reshape(h2, w2); cc_ = np.clip(cc_, 0, sr.width - 1).reshape(h2, w2)
        sand_d, clay_d = sa[0][rr_, cc_], sa[2][rr_, cc_]
    ms, mc = np.nanmedian(sand_d), np.nanmedian(clay_d)
    cfac = np.where(np.isfinite(clay_d), np.clip(clay_d / mc, .6, 1.5), 1.0)
    dphi = np.where(np.isfinite(sand_d), np.clip((sand_d - ms) / 100 * 2.0, -4, 4), 0.0)
    soil_enc_c = enc(np.where(nd_d, 255, np.round(cfac * 100)))
    soil_enc_p = enc(np.where(nd_d, 255, np.round((dphi + 4) * 20)))
    np.savez_compressed(DATA / "soil_factors.npz", cfac=cfac, dphi=dphi)
    print("soil texture: clay median g/kg", round(mc), "sand", round(ms), "cohesion factor p5-p95", np.nanpercentile(cfac[~nd_d], [5, 95]).round(2), "dphi", np.nanpercentile(dphi[~nd_d], [5, 95]).round(1))

# ---- dip direction of the ground (azimuth of steepest descent, clockwise from north), vector mean per block, for the joint kinematic test
asp_s, asp_c = blocks(np.sin(asp)).mean(axis=(1, 3)), blocks(np.cos(asp)).mean(axis=(1, 3))
aspect_d = (np.degrees(np.arctan2(asp_s, asp_c)) + 360) % 360
aspect_q = np.where(nd_d, 255, np.round(aspect_d / 360 * 254))

# ---- HydroRIVERS reaches (mean discharge and upstream area) for the landslide-dam analysis
HR = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/river/HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as_shp/HydroRIVERS_v10_as.shp"
rivers = []
if HR.exists():
    hr = gpd.read_file(HR, bbox=(73.85, 35.5, 74.95, 36.35)).to_crs(r.crs)
    for _, w_ in hr.iterrows():
        gm = w_.geometry.intersection(ext_geom)
        for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if ln.geom_type != "LineString" or ln.length < 100: continue
            ln = ln.simplify(60)
            rivers.append(dict(q=round(float(w_["DIS_AV_CMS"]), 2), up=round(float(w_["UPLAND_SKM"]), 1), xy=[v for x_, y_ in ln.coords for v in [int(round(c * 10000)) for c in px(x_, y_)]]))
print("river reaches", len(rivers))

# ---- exposure data for the impact assessment (roads, bridges, facilities, places, building footprints), metres from the extent corner
import infra_data as INF
INFRA = INF.osm_infra(b.left, b.bottom, b.right, b.top, r.crs.to_string())
_bx, _by, _ba = INF.buildings_local(DATA / "open_buildings_v3.geojson", r.crs.to_string(), b.left, b.bottom, b.right, b.top, None)
BPTS = INF.pack_buildings(_bx, _by, _ba, b.left, b.top, lambda xx, yy: valid[np.clip(((b.top - yy) / dx).astype(int), 0, valid.shape[0] - 1), np.clip(((xx - b.left) / dx).astype(int), 0, valid.shape[1] - 1)])
print("infra", {k: len(v) for k, v in INFRA.items()}, "buildings", BPTS["n"] if BPTS else None)

np.savez_compressed(DATA / "validation_inputs.npz", score=np.where(scored, score, np.nan), sd=sd_d, nd=nd_d, cells=np.array(cells))

data = dict(stats=dict(zmin=float(np.nanmin(z)), zmax=float(np.nanmax(z)), zmean=float(np.nanmean(z)), slope_mean_pct=float(slope_pct[valid].mean()),
                       area_km2=float(valid.sum() * dx * dx / 1e6), cls_pct=[float((cls == k).sum() / valid.sum() * 100) for k in range(4)], W=r.width, H=r.height,
                       res=dx, bounds=[b.left, b.bottom, b.right, b.top], eq_total=len(q), eq_from=int(q.time.min()), eq_to=int(q.time.max())),
            pts=pts, qs=qs, slope_deg=enc(slope_deg), cell_m=dx * F, w=w2, h=h2,
            lc=enc(lc_d), lc_area=lc_area, bld=enc(bld_d), bld_total=int(len(bg)), pop=enc(np.clip(np.round(pop_d * 10), 0, 255)), pop_total=pop_total,
            emb=dict(n_template=len(cells), loo_median=float(np.median(loo)), loo_mean=float(np.mean(loo)), loo_n=len(loo), slope_median=float(np.median(slope_base)),
                                                                  loo_hit_top10=float(np.mean([v >= .9 for v in loo])), loo_hit_top25=float(np.mean([v >= .75 for v in loo]))),
            faults=faults, faults_near=int(len(fl_near)), rain=rain, shake=shake, screen=png(scr), lit_area=lit_area, scr_pct=scr_pct, unk_pct=unk_pct, scr_val=scr_val, elev53=elev53, chirps=dict(start=str(ch.index.min().date()), v=base64.b64encode(np.clip(np.round(ch.fillna(0).values * 10), 0, 65535).astype('<u2').tobytes()).decode()), calib=(json.loads((ROOT / 'landslide-platform/docs/calibration_results.json').read_text(encoding='utf-8')) if (ROOT / 'landslide-platform/docs/calibration_results.json').exists() else None), rivers=rivers, aspect=enc(aspect_q), tpi=enc(tpi_cls), site=enc(site_cls), amp_stats=amp_stats, infra=INFRA, bpts=BPTS, proj=dict(epsg=32643, lon0=75.0), pop_scale=10, bld_scale=1, validation_scope='gilgit', allpts=[dict(lon=round(float(r.longitude), 4), lat=round(float(r.latitude), 4), date=int(r.event_date), cat=str(r.landslide_category), trig=str(r.landslide_trigger), size=str(r.landslide_size), title=str(r.event_title)[:70], acc=str(r.location_accuracy), fat=(float(r.fatality_count) if pd.notna(r.fatality_count) else None)) for r in gpd.read_file(INV).itertuples()], aoi=dict(id='gilgit', name='Gilgit (sample area)', deep=True, polygon=json.loads(gpd.GeoSeries([gpd.read_file(ROOT / 'Shapefiles/Gilgit shp/Gilgit.shp').to_crs(4326).geometry.union_all().simplify(0.003)]).to_json())['features'][0]['geometry'], built='built in'), hourly=(json.loads((ROOT / 'landslide-platform/docs/hourly_climate_results.json').read_text(encoding='utf-8')) if (ROOT / 'landslide-platform/docs/hourly_climate_results.json').exists() else None), soil_c=soil_enc_c, soil_p=soil_enc_p, rthr=rthr, validation=(json.loads((ROOT / 'landslide-platform/docs/validation_results.json').read_text(encoding='utf-8')) if (ROOT / 'landslide-platform/docs/validation_results.json').exists() else None))
OUT.write_text(TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", json.dumps(data)), encoding="utf-8")
SITE_DIR = ROOT / "landslide-platform/site"
SITE_DIR.mkdir(exist_ok=True)
page = OUT.read_text(encoding="utf-8")
(SITE_DIR / "index.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><script src="config.js"></script></head><body>\n' + page + '\n</body></html>', encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
cfg = SITE_DIR / "config.js"
if not cfg.exists():
    cfg.write_text("// Paste a Mapbox public access token (pk.) between the quotes to use Mapbox basemaps. Leave empty for the free fallback.\nwindow.MAPBOX_TOKEN = '';\n", encoding="utf-8")
print("wrote", SITE_DIR / "index.html")
print("pop_total", round(pop_total), "bld", len(bg), "template cells", len(cells), "LOO", [round(v, 2) for v in loo])
print("faults in extent", len(faults), "near(50km)", len(fl_near), "rain", rain["max1"], rain["max3"], rain["max7"], rain["p99_wet"])
