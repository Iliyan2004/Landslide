"""Build the dashboard data package and page for any area of interest in Pakistan.

build_aoi(geometry_lonlat, name, out_dir, progress, deep) reads the national DEM (datasets/dem_30m.tif, EPSG:32642, 30 m), cuts the AOI window,
derives terrain, fetches the other layers from Earth Engine (reduced to the AOI's coarse grid) and from the Pakistan-wide local files, and writes
a self-contained dashboard page for that AOI. The same model code and the same page as the Gilgit dashboard are used; only the data change.

Grid rules
  fine cell     30 m x s, where s = 1, 2, 3 ... is the smallest step that keeps the longest side at 3,600 cells or fewer (areas up to 500 km a side)
  coarse cell   6 fine cells (180 m for s = 1); this is the grid the scenario simulation runs on
  window        the drawn polygon's bounding box, at least 10 km on each side, aligned to the DEM and to the coarse cell
Cells outside the drawn polygon are no-data, so only the drawn area is analysed.
"""
from __future__ import annotations
import base64, hashlib, io, json, re, sys, time, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.windows import Window
from scipy import ndimage as _ndi
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).parent))
import aoi_ee as EEL
import infra_data as INF

ROOT = Path(__file__).resolve().parents[2]
LP = ROOT / "landslide-platform"
DEM = LP / "datasets/dem_30m.tif"
RAW = LP / "datasets/raw"
PK = RAW / "pakistan"
INV = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/landslide_inventory/landslide_inventory.gpkg"
EQ = ROOT / "LANDSLIDE PLATFORM/additional data/downloaded_data/earthquake_hazard/usgs_events.csv"
TEMPLATE = Path(__file__).with_name("dashboard_template.html")
CRS = "EPSG:32642"
LON0 = 69.0                      # central meridian of UTM zone 42
F = 6
MAXFINE = 3600
MIN_SIDE = 10000.0
MAX_SIDE = 500000.0
BLD_MAX_KM2 = 12000.0            # Open Buildings counts are skipped for larger areas: too many footprints for Earth Engine to count in reasonable time
SLOPE_PCT_BINS = [15, 35, 70]
COLS = np.array([[96, 160, 110], [222, 196, 84], [222, 126, 52], [176, 40, 40]], float)
RANK = {"su": 5, "ss": 3, "sm": 3, "sc": 2, "py": 4, "va": 2, "vi": 2, "vb": 2, "pa": 1, "pi": 1, "pb": 1, "mt": 3, "ev": 3}
GAM, GW, POR, INF, NMEM = 18.0, 9.81, 0.4, 0.5, 40
ROOT_C = {1: 5, 2: 3, 3: 2, 4: 1}
enc = lambda a: base64.b64encode(np.asarray(a).astype("uint8").tobytes()).decode()
to_utm = Transformer.from_crs(4326, CRS, always_xy=True).transform
to_ll = Transformer.from_crs(CRS, 4326, always_xy=True).transform


def png(a):
    b = io.BytesIO(); Image.fromarray(a.astype("uint8"), "RGBA").save(b, "PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode()


class AOIError(Exception):
    pass


# ------------------------------------------------------------------------------------------------------ grid
def make_grid(geom_ll: dict):
    poly_ll = shape(geom_ll)
    if not poly_ll.is_valid: poly_ll = poly_ll.buffer(0)
    if poly_ll.is_empty: raise AOIError("empty polygon")
    poly = shp_transform(to_utm, poly_ll)
    with rasterio.open(DEM) as r:
        dl, dt_, dr, db = r.bounds.left, r.bounds.top, r.bounds.right, r.bounds.bottom
        dem_box = box(dl, db, dr, dt_)
    if not poly.intersects(dem_box): raise AOIError("the polygon is outside the national DEM (Pakistan)")
    l, b, rgt, t = poly.bounds
    cx, cy = (l + rgt) / 2, (b + t) / 2
    w, h = max(rgt - l, MIN_SIDE), max(t - b, MIN_SIDE)
    if max(w, h) > MAX_SIDE: raise AOIError(f"the area is {max(w,h)/1000:.0f} km across; the limit is {MAX_SIDE/1000:.0f} km")
    s = int(np.ceil(max(w, h) / (30.0 * MAXFINE)))
    fine = 30.0 * s
    cs = fine * F
    x0 = dl + np.floor((cx - w / 2 - dl) / cs) * cs
    y1 = dt_ - np.floor((dt_ - (cy + h / 2)) / cs) * cs
    w2 = int(np.ceil((cx + w / 2 - x0) / cs)); h2 = int(np.ceil((y1 - (cy - h / 2)) / cs))
    return dict(poly_ll=poly_ll, poly=poly, s=s, fine=fine, cs=cs, x0=float(x0), y1=float(y1), w2=w2, h2=h2, dem_left=dl, dem_top=dt_)


def aoi_id(geom_ll, deep):
    key = json.dumps({"g": geom_ll, "d": bool(deep)}, sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# ------------------------------------------------------------------------------------------------------ main
def build_aoi(geom_ll: dict, name: str, out_dir: Path, progress=print, deep=True, aoi_key: str | None = None) -> dict:
    t_start = time.time()
    P = lambda m: progress(m)
    G = make_grid(geom_ll)
    s, fine, cs, x0, y1, w2, h2 = G["s"], G["fine"], G["cs"], G["x0"], G["y1"], G["w2"], G["h2"]
    W, H = w2 * F, h2 * F
    x1, y0 = x0 + w2 * cs, y1 - h2 * cs
    P(f"grid: {W} x {H} cells of {fine:.0f} m, web cells {cs:.0f} m ({w2} x {h2})")
    grid = EEL.Grid(CRS, x0, y1, cs, w2, h2)
    poly_ll_json = json.loads(gpd.GeoSeries([G["poly_ll"]]).to_json())["features"][0]["geometry"]

    # ---------- Earth Engine layers, started now so they run while the terrain is derived
    pool = ThreadPoolExecutor(6)
    jobs = {"worldcover": pool.submit(EEL.worldcover, grid), "lc_area": pool.submit(EEL.landcover_area_km2, poly_ll_json),
            "pop": pool.submit(EEL.population, grid), "soil": pool.submit(EEL.soil_texture, grid),
            "chirps": pool.submit(EEL.chirps_daily_mean, poly_ll_json)}
    area_km2 = G["poly"].area / 1e6
    bld_skipped = area_km2 > BLD_MAX_KM2
    if not bld_skipped: jobs["bld"] = pool.submit(EEL.buildings, grid)
    else: P(f"buildings skipped: the area is {area_km2:,.0f} km2 (limit {BLD_MAX_KM2:,.0f})")
    jobs["infra"] = pool.submit(INF.osm_infra, x0, y0, x1, y1, CRS, area_km2 > BLD_MAX_KM2)
    bpts_ok = area_km2 <= INF.BUILDING_MAX_KM2
    if bpts_ok: jobs["bpts"] = pool.submit(INF.buildings_ee, poly_ll_json, CRS, x0, y0, x1, y1)
    if deep:
        jobs["emb"] = pool.submit(EEL.embeddings, grid)
        jobs["scarA"] = pool.submit(EEL.scar_fraction, grid, 2017, 2020)
        jobs["scarB"] = pool.submit(EEL.scar_fraction, grid, 2020, 2024)

    # ---------- DEM window
    P("reading the national DEM")
    with rasterio.open(DEM) as r:
        px = 30.0
        col0 = int(round((x0 - G["dem_left"]) / px)); row0 = int(round((G["dem_top"] - y1) / px))
        wd, hd = int(round((x1 - x0) / px)), int(round((y1 - y0) / px))
        arr = r.read(1, window=Window(col0, row0, wd, hd), out_shape=(H, W), boundless=True, fill_value=-9999,
                     resampling=Resampling.average if s > 1 else Resampling.nearest).astype("float64")
    z = arr.copy(); nd = (z <= -9000) | ~np.isfinite(z); z[nd] = np.nan
    tf_fine = from_origin(x0, y1, fine, fine)
    inpoly = rasterize([(G["poly"], 1)], out_shape=(H, W), transform=tf_fine, fill=0, dtype="uint8").astype(bool)
    nd = nd | ~inpoly
    z[nd] = np.nan
    if (~nd).sum() < 400: raise AOIError("the polygon holds almost no DEM data")
    dx = fine
    zf = np.where(nd, np.nanmean(z), z)
    gy, gx = np.gradient(zf, dx)
    slope_pct = np.hypot(gx, gy) * 100
    cls = np.digitize(slope_pct, SLOPE_PCT_BINS); cls[nd] = -1; valid = ~nd
    sl = np.arctan(np.hypot(gx, gy)); asp = np.arctan2(-gx, gy); az, alt = np.radians(315), np.radians(40)
    hs = np.clip(np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp), 0, 1) * 255
    blocks = lambda a: a[:h2 * F, :w2 * F].reshape(h2, F, w2, F)
    hs_d = blocks(hs).mean(axis=(1, 3))
    nd_d = blocks(nd).mean(axis=(1, 3)) > 0.5
    blk = cls[:h2 * F, :w2 * F].reshape(h2, F, w2, F).transpose(0, 2, 1, 3).reshape(h2, w2, F * F)
    cls_d = np.apply_along_axis(lambda v: np.bincount(v + 1, minlength=5).argmax() - 1, 2, blk)
    g3 = hs_d[..., None] * np.ones(3)
    sdeg = np.degrees(sl); sdeg[nd] = np.nan
    with np.errstate(all="ignore"):
        sd_d = np.nanmean(blocks(sdeg), axis=(1, 3)); z_d = np.nanmean(blocks(z), axis=(1, 3))
    slope_deg = np.where(nd_d, 255, np.clip(np.round(np.nan_to_num(sd_d)), 0, 89))
    px_ = lambda x, y: [(x - x0) / (x1 - x0), (y1 - y) / (y1 - y0)]
    cellkm2 = (cs / 1000) ** 2
    ext = box(x0, y0, x1, y1)

    # ---------- heightfield for the 3D replay
    hs_step = 1 if max(W, H) <= 2000 else 2
    P(f"heightfield at {fine * hs_step:.0f} m")
    hh, ww = H // hs_step, W // hs_step
    if hs_step == 1:
        z_h = z
    else:
        with np.errstate(all="ignore"):
            z_h = np.nanmean(z[:hh * 2, :ww * 2].reshape(hh, 2, ww, 2), axis=(1, 3))
    zmin_fill = np.nanmin(z_h)
    zh = np.round(np.where(np.isfinite(z_h), z_h, zmin_fill)).astype(np.int16)
    dd = np.diff(zh.astype(np.int32), axis=1, prepend=0); dd = np.diff(dd, axis=0, prepend=0).astype(np.int16)
    elev53 = dict(w=ww, h=hh, res=fine * hs_step, x0=x0, y1=y1, z=base64.b64encode(zlib.compress(dd.astype("<i2").tobytes(), 9)).decode())

    # ---------- layers from Earth Engine
    P("fetching land cover, population, buildings, soil and rainfall")
    lc = jobs["worldcover"].result()
    lc_d = np.where(nd_d, 0, lc // 10)
    lc_area = {int(k): float(v) for k, v in jobs["lc_area"].result().items()}
    pop_d = np.where(nd_d, 0, jobs["pop"].result().astype("float64"))
    pop_total = float(pop_d.sum())
    bld = np.where(nd_d, 0, jobs["bld"].result()).astype("int64") if not bld_skipped else np.zeros((h2, w2), "int64")
    bld_total = int(bld.sum())
    ch = jobs["chirps"].result()
    ch = ch[ch.index <= ch.index.max()]
    tex = jobs["soil"].result()
    sand_d, clay_d = tex[0].astype(float), tex[2].astype(float)
    for a in (sand_d, clay_d): a[~np.isfinite(a) | (a < 0)] = np.nan
    soil_enc_c = soil_enc_p = None
    if np.isfinite(clay_d[~nd_d]).sum() > 10:
        ms, mc = np.nanmedian(sand_d[~nd_d]), np.nanmedian(clay_d[~nd_d])
        cfac = np.where(np.isfinite(clay_d), np.clip(clay_d / mc, .6, 1.5), 1.0)
        dphi = np.where(np.isfinite(sand_d), np.clip((sand_d - ms) / 100 * 2.0, -4, 4), 0.0)
        soil_enc_c = enc(np.where(nd_d, 255, np.round(cfac * 100))); soil_enc_p = enc(np.where(nd_d, 255, np.round((dphi + 4) * 20)))

    infra = jobs["infra"].result()
    bpts = None
    if bpts_ok:
        bx, by, ba = jobs["bpts"].result()
        def _inside(xx, yy):
            ci = np.clip(((y1 - yy) / fine).astype(int), 0, H - 1); cj = np.clip(((xx - x0) / fine).astype(int), 0, W - 1)
            return valid[ci, cj]
        bpts = INF.pack_buildings(bx, by, ba, x0, y1, _inside)
    # ---------- inventory, earthquakes
    inv = gpd.read_file(INV).to_crs(CRS)
    allmeta = gpd.read_file(INV)
    allpts = [dict(lon=round(float(r.longitude), 4), lat=round(float(r.latitude), 4), date=int(r.event_date), cat=str(r.landslide_category), trig=str(r.landslide_trigger), size=str(r.landslide_size),
                   title=str(r.event_title)[:70], acc=str(r.location_accuracy), fat=(float(r.fatality_count) if pd.notna(r.fatality_count) else None)) for r in allmeta.itertuples()]
    invw = inv.cx[x0 - 50000:x1 + 50000, y0 - 50000:y1 + 50000]
    pts = []
    for _, w in invw.iterrows():
        u, v = px_(w.geometry.x, w.geometry.y)
        inside = bool(0 <= u <= 1 and 0 <= v <= 1)
        if inside:
            ci, cj = min(H - 1, int(v * H)), min(W - 1, int(u * W))
            inside = bool(valid[ci, cj])
        pts.append(dict(u=round(u, 4), v=round(v, 4), inside=inside, date=str(w.event_date), cat=str(w.landslide_category), trig=str(w.landslide_trigger), size=str(w.landslide_size),
                        title=str(w.event_title)[:70], desc=str(w.event_description)[:240], loc=str(w.location_description)[:80], acc=str(w.location_accuracy), src=str(w.source_link)[:140],
                        fat=(float(w.fatality_count) if pd.notna(w.fatality_count) else None), inj=(float(w.injury_count) if pd.notna(w.injury_count) else None), photo=str(w.photo_link)[:140] if pd.notna(w.photo_link) else '', lon=round(float(w.longitude), 4), lat=round(float(w.latitude), 4)))
    cells = [(int(p["v"] * h2), int(p["u"] * w2)) for p in pts if p["inside"]]
    cells = [(min(h2 - 1, i), min(w2 - 1, j)) for i, j in cells if not nd_d[min(h2 - 1, i), min(w2 - 1, j)]]
    q = pd.read_csv(EQ)
    qx, qy = to_utm(q.longitude.values, q.latitude.values)
    qm = (qx >= x0) & (qx <= x1) & (qy >= y0) & (qy <= y1)
    qs = [dict(u=round(px_(x_, y_)[0], 4), v=round(px_(x_, y_)[1], 4), m=float(m), d=float(d), t=pd.to_datetime(t, unit="ms").strftime("%Y-%m-%d"))
          for x_, y_, m, d, t in zip(qx[qm], qy[qm], q.magnitude.values[qm], q.depth_km.values[qm], q.time.values[qm])]

    # ---------- rainfall statistics and threshold
    ann = ch.groupby(ch.index.year).max(); full = ch[ch.index.year < ch.index.max().year]
    rain = dict(first=str(ch.index.min().date()), last=str(ch.index.max().date()), years=[int(y) for y in ann.index], annmax=[round(float(v), 1) for v in ann.values],
                monthly=[round(float(v), 1) for v in (full.groupby(full.index.month).sum() / full.index.year.nunique()).values],
                max1=round(float(ch.max()), 1), max1_date=str(ch.idxmax().date()), max3=round(float(ch.rolling(3).sum().max()), 1), max7=round(float(ch.rolling(7).sum().max()), 1),
                p99_wet=round(float(ch[ch > 1].quantile(.99)), 1) if (ch > 1).any() else 0.0, wet_frac=round(float((ch > 1).mean()), 3))
    rthr = _rain_threshold(ch, pts)

    # ---------- ShakeMaps
    P("sampling ShakeMaps")
    shake = _shakemaps(x0, y0, cs, w2, h2, nd_d)

    # ---------- faults, rivers
    flp = PK.parent / "gilgit/gem_active_faults_pakistan.gpkg"
    fl = gpd.read_file(flp).to_crs(CRS)
    faults = []
    for _, w in fl.cx[x0 - 1000:x1 + 1000, y0 - 1000:y1 + 1000].iterrows():
        gm = w.geometry.intersection(ext)
        if gm.is_empty: continue
        for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if ln.geom_type != "LineString": continue
            ln = ln.simplify(max(150, fine * 5))
            faults.append(dict(name=w["name"] or "unnamed", slip=str(w["slip_type"]), catalog=str(w["catalog_name"]), km=round(ln.length / 1000, 1), xy=[[round(v, 4) for v in px_(x, y)] for x, y in ln.coords]))
    fl_near = int(len(fl.cx[x0 - 50000:x1 + 50000, y0 - 50000:y1 + 50000]))
    rivers = []
    hr = gpd.read_file(PK / "rivers_pakistan.gpkg", bbox=tuple(np.array(to_ll(x0, y0) + to_ll(x1, y1))[[0, 1, 2, 3]] + np.array([-.01, -.01, .01, .01]))).to_crs(CRS)
    pq = lambda x, y: [int(round(v * 10000)) for v in px_(x, y)]
    for _, w_ in hr.iterrows():
        gm = w_.geometry.intersection(ext)
        for ln in (gm.geoms if hasattr(gm, "geoms") else [gm]):
            if ln.geom_type != "LineString" or ln.length < 100: continue
            ln = ln.simplify(60)
            rivers.append(dict(q=round(float(w_["DIS_AV_CMS"]), 2), up=round(float(w_["UPLAND_SKM"]), 1), xy=[v for x_, y_ in ln.coords for v in pq(x_, y_)]))

    # ---------- GLiM lithology and the screening score
    P("lithology and screening")
    lit, idmap, lit_area = _glim(x0, y1, cs, w2, h2, x1, y0, nd_d, cellkm2)
    inv_idmap = {v: k for k, v in idmap.items()}
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
    scr[..., :3] = 0.62 * scr[..., :3] + 0.38 * g3; scr[..., 3] = np.where(~nd_d, 255, 0)
    ns = max(1, int(scored.sum()))
    scr_pct = [float((scls == k).sum() / ns * 100) for k in range(4)]
    unk_pct = float(unk.sum() / max(1, (~nd_d).sum()) * 100)
    sv = [float((score[scored] < score[i, j]).mean()) for i, j in cells if scored[i, j]]
    sv_slope = [float((cls_d[scored] < cls_d[i, j]).mean() + 0.5 * (cls_d[scored] == cls_d[i, j]).mean()) for i, j in cells if scored[i, j]]
    scr_val = dict(n=len(sv), median=float(np.median(sv)) if sv else None, slope_median=float(np.median(sv_slope)) if sv_slope else None, in_unknown=int(sum(1 for i, j in cells if unk[i, j])))

    # ---------- amplification classes, aspect
    zfd = np.where(np.isfinite(z_d), z_d, np.nanmean(z_d))
    tpi = zfd - _ndi.uniform_filter(zfd, size=5, mode="nearest")
    tpi_cls = np.where(nd_d, 255, np.where(tpi > 40, 2, np.where(tpi < -40, 0, 1)))
    soft = {"su": 2, "ss": 1, "sm": 1, "py": 1}
    site_cls = np.zeros((h2, w2), int)
    for i_, c_ in inv_idmap.items():
        if c_ in soft: site_cls[lit == i_] = soft[c_]
    site_cls = np.where(nd_d, 255, site_cls)
    nv = max(1, int((~nd_d).sum()))
    amp_stats = dict(crest_pct=float((tpi_cls[tpi_cls != 255] == 2).mean() * 100) if nv else 0, valley_pct=float((tpi_cls[tpi_cls != 255] == 0).mean() * 100) if nv else 0,
                     soft_pct=float((site_cls[site_cls != 255] == 2).mean() * 100), semi_pct=float((site_cls[site_cls != 255] == 1).mean() * 100))
    asp_s, asp_c = blocks(np.sin(asp)).mean(axis=(1, 3)), blocks(np.cos(asp)).mean(axis=(1, 3))
    aspect_q = np.where(nd_d, 255, np.round(((np.degrees(np.arctan2(asp_s, asp_c)) + 360) % 360) / 360 * 254))

    # ---------- embeddings similarity and satellite scars
    emb = None; calib = None
    if deep:
        P("satellite embeddings and Sentinel-2 scars")
        emb = _embedding_stats(jobs["emb"].result(), nd_d, cells, sd_d)
        scarA, scarB = jobs["scarA"].result(), jobs["scarB"].result()
        calib = _calibration(scarA, scarB, slope_deg, lc_d, nd_d, pts, h2, w2, sdeg, cellkm2, P)
    pool.shutdown(wait=False)

    # ---------- assemble
    P("assembling the page")
    pop_max = float(pop_d.max()) if pop_d.size else 0.0
    pop_scale = 10.0 if pop_max <= 25 else 254.0 / pop_max
    bmax = int(bld.max()) if bld.size else 0
    bld_scale = 1 if bmax <= 255 else int(np.ceil(bmax / 255))
    aid = aoi_key or aoi_id(geom_ll, deep)
    lon_lat_bounds = [*to_ll(x0, y0), *to_ll(x1, y1)]
    valid_cells = int(valid.sum())
    data = dict(stats=dict(zmin=float(np.nanmin(z)), zmax=float(np.nanmax(z)), zmean=float(np.nanmean(z)), slope_mean_pct=float(slope_pct[valid].mean()), area_km2=float(valid_cells * dx * dx / 1e6),
                           cls_pct=[float((cls == k).sum() / valid_cells * 100) for k in range(4)], W=W, H=H, res=dx, bounds=[x0, y0, x1, y1], eq_total=int(len(q)), eq_from=int(q.time.min()), eq_to=int(q.time.max())),
                pts=pts, qs=qs, slope_deg=enc(slope_deg), cell_m=cs, w=w2, h=h2, lc=enc(lc_d), lc_area=lc_area, bld=enc(np.clip(np.ceil(bld / bld_scale), 0, 255)), bld_scale=bld_scale,
                bld_total=bld_total, bld_skipped=bool(bld_skipped), pop=enc(np.clip(np.round(pop_d * pop_scale), 0, 255)), pop_scale=pop_scale, pop_total=pop_total, emb=emb, faults=faults, faults_near=fl_near, rain=rain, shake=shake,
                screen=png(scr), lit_area=lit_area, scr_pct=scr_pct, unk_pct=unk_pct, scr_val=scr_val, elev53=elev53,
                chirps=dict(start=str(ch.index.min().date()), v=base64.b64encode(np.clip(np.round(ch.fillna(0).values * 10), 0, 65535).astype('<u2').tobytes()).decode()),
                calib=calib, rivers=rivers, aspect=enc(aspect_q), tpi=enc(tpi_cls), site=enc(site_cls), amp_stats=amp_stats, soil_c=soil_enc_c, soil_p=soil_enc_p, rthr=rthr,
                hourly=_load(LP / "docs/hourly_climate_results.json"), validation=_load(LP / "docs/validation_results.json"), validation_scope="gilgit",
                proj=dict(epsg=32642, lon0=LON0), allpts=allpts, infra=infra, bpts=bpts,
                aoi=dict(id=aid, name=name, deep=bool(deep), polygon=poly_ll_json, bounds_ll=lon_lat_bounds, fine_cell=dx, step=s, built=time.strftime("%Y-%m-%d %H:%M"), seconds=round(time.time() - t_start)))
    out_dir.mkdir(parents=True, exist_ok=True)
    page = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", json.dumps(data))
    html = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><script src="/config.js"></script></head><body>\n' + page + '\n</body></html>'
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(dict(id=aid, name=name, deep=bool(deep), polygon=poly_ll_json, bounds_ll=lon_lat_bounds, area_km2=data["stats"]["area_km2"], built=data["aoi"]["built"],
                                                       seconds=data["aoi"]["seconds"], events=len([p for p in pts if p["inside"]]))), encoding="utf-8")
    P(f"done in {time.time() - t_start:.0f} s, page {len(html) / 1e6:.1f} MB")
    return dict(id=aid, path=str(out_dir / "index.html"))


def _load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ------------------------------------------------------------------------------------------------------ pieces
def _rain_threshold(ch, pts):
    def _ts(v):
        v = int(float(v)); return pd.Timestamp(v, unit="ms" if v > 1e11 else "s")
    DUR = [1, 2, 3, 5, 7, 10]
    roll = {d: ch.rolling(d).sum() / d for d in DUR}
    rows = []
    for p in pts:
        if not p["inside"] or not re.search(r"rain|downpour|monsoon|flood", p["trig"].lower()): continue
        try: dte = _ts(p["date"]).normalize()
        except Exception: continue
        if not (ch.index.min() <= dte <= ch.index.max()): continue
        I = {d: float(max(roll[d].get(dte, np.nan), roll[d].get(dte + pd.Timedelta(days=1), np.nan))) for d in DUR}
        if all(np.isfinite(v) for v in I.values()): rows.append((str(dte.date()), I))
    if len(rows) < 5: return None
    ev_dates = [pd.Timestamp(d_) for d_, _ in rows]
    near = np.zeros(len(ch), bool)
    for d_ in ev_dates: near |= (np.abs((ch.index - d_).days) <= 5)
    months = ch.index.month; base = (months >= 4) & (months <= 9) & ~near
    def auc(pos, neg):
        neg = np.sort(neg); lo = np.searchsorted(neg, pos, "left"); hi = np.searchsorted(neg, pos, "right"); return float(np.mean((lo + 0.5 * (hi - lo)) / len(neg)))
    per = []
    for d in DUR:
        pos = np.array([I[d] for _, I in rows]); neg = roll[d].values[base]; neg = neg[np.isfinite(neg)]
        cand = np.unique(np.concatenate([pos, np.quantile(neg, np.linspace(.5, .999, 200))]))
        tss = [(np.mean(pos >= c) - np.mean(neg >= c), c) for c in cand]; best, c_ = max(tss)
        per.append(dict(d=d, thr=float(c_), pod=float(np.mean(pos >= c_)), pofd=float(np.mean(neg >= c_)), tss=float(best), auc=auc(pos, neg)))
    bestd = max(per, key=lambda r_: r_["auc"])
    yrs = (ch.index.max() - ch.index.min()).days / 365.25
    return dict(per=per, best_d=bestd["d"], n_events=len(rows), exceed_days_per_year=float((roll[bestd["d"]].values >= bestd["thr"]).sum() / yrs), durations=DUR,
                events=[dict(date=dt_, I={str(d): round(v, 2) for d, v in I.items()}) for dt_, I in rows])


def _shakemaps(x0, y0, cs, w2, h2, nd_d):
    idxp = PK / "shakemap_index.csv"
    if not idxp.exists(): return []
    S0 = pd.read_csv(idxp)
    X, Y = np.meshgrid(x0 + (np.arange(w2) + .5) * cs, y0 + (np.arange(h2)[::-1] + .5) * cs)
    LON, LAT = Transformer.from_crs(CRS, 4326, always_xy=True).transform(X.ravel(), Y.ravel())
    LON, LAT = np.asarray(LON).reshape(h2, w2), np.asarray(LAT).reshape(h2, w2)
    ok = ~nd_d
    lo0, lo1, la0, la1 = LON[ok].min(), LON[ok].max(), LAT[ok].min(), LAT[ok].max()
    S0 = S0[(S0.lon_min <= lo0) & (S0.lon_max >= lo1) & (S0.lat_min <= la0) & (S0.lat_max >= la1)]
    rows = []
    for _, e in S0.iterrows():
        z = np.load(PK / "shakemap" / f"{e.event_id}.npz"); pga = z["pga"].astype(float)
        ny, nx = pga.shape
        lon = z["lon0"] + np.arange(nx) * z["dlon"]; lat = z["lat0"] + np.arange(ny) * z["dlat"]
        v = RegularGridInterpolator((lat, lon), pga, bounds_error=False, fill_value=np.nan)(np.column_stack([LAT.ravel(), LON.ravel()])).reshape(h2, w2)
        cover = float(np.isfinite(v[ok]).mean()) * 100
        if cover < 99: continue
        rows.append((e, v, float(np.nanmean(v[ok])), float(np.nanmax(v[ok]))))
    if not rows: return []
    rows.sort(key=lambda r: r[0].date)
    recent = rows[-1]
    top = sorted(rows, key=lambda r: -r[2])[:6]
    chosen = [recent] + [r for r in top if r[0].event_id != recent[0].event_id]
    out = []
    for e, v, mean, mx in chosen:
        arr = np.where(nd_d | ~np.isfinite(v), 255, np.clip(np.round(np.nan_to_num(v) * 10), 0, 254))
        out.append(dict(id=e.event_id, date=e.date, mag=float(e.mag), place=str(e.place), depth=float(e.depth_km), pga_max=round(mx, 2), pga_mean=round(mean, 2), mmi_max=float(e.mmi_max),
                        recent=bool(e.event_id == recent[0].event_id), pga=enc(arr)))
    return out


def _glim(x0, y1, cs, w2, h2, x1, y0, nd_d, cellkm2):
    p = PK / "glim_pakistan.gpkg"
    ref = gpd.read_file(p, rows=1)
    ll = Transformer.from_crs(CRS, 4326, always_xy=True).transform
    bb = gpd.GeoSeries([box(*ll(x0, y0), *ll(x1, y1))], crs=4326).to_crs(ref.crs).total_bounds
    gl = gpd.read_file(p, bbox=tuple(bb)).to_crs(CRS)
    codes = sorted(gl.xx.unique()) if len(gl) else []
    idmap = {c: i + 1 for i, c in enumerate(codes)}
    if len(gl):
        lit = rasterize(((g_, idmap[x_]) for g_, x_ in zip(gl.geometry, gl.xx)), out_shape=(h2, w2), transform=from_origin(x0, y1, cs, cs), fill=0, dtype="uint8")
    else:
        lit = np.zeros((h2, w2), "uint8")
    inv = {v: k for k, v in idmap.items()}
    area = {inv[i]: float(((lit == i) & ~nd_d).sum() * cellkm2) for i in inv}
    return lit, idmap, area


def _embedding_stats(emb, nd_d, cells, sd_d):
    En = emb / (np.linalg.norm(emb, axis=0) + 1e-9)
    vmask = ~nd_d & np.isfinite(emb[0]) & (np.abs(emb).sum(0) > 0)
    En = np.where(vmask[None], En, 0)
    cells = [(i, j) for i, j in cells if vmask[i, j]]
    if len(cells) < 3: return None
    def template(use):
        t = np.mean([En[:, i, j] for i, j in use], axis=0); return t / (np.linalg.norm(t) + 1e-9)
    loo = []
    for (i, j) in cells:
        use = [c for c in cells if max(abs(c[0] - i), abs(c[1] - j)) > 5]
        if not use: continue
        sc = np.tensordot(template(use), En, axes=1)
        loo.append(float((sc[vmask] < sc[i, j]).mean()))
    if not loo: return None
    slope_base = [float((sd_d[vmask] < sd_d[i, j]).mean()) for i, j in cells]
    return dict(n_template=len(cells), loo_median=float(np.median(loo)), loo_mean=float(np.mean(loo)), loo_n=len(loo), slope_median=float(np.median(slope_base)),
                loo_hit_top10=float(np.mean([v >= .9 for v in loo])), loo_hit_top25=float(np.mean([v >= .75 for v in loo])))


def _mulberry32(a):
    a &= 0xFFFFFFFF
    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rnd


def _calibration(scarA, scarB, slope_deg, lc_d, nd_d, pts, h2, w2, sdeg_fine, cellkm2, P):
    """Scar maps for the layer, and the soil calibration against them, on the coarse grid (as scripts/calibrate_stability.py does for Gilgit)."""
    from scipy.stats import qmc, rankdata
    SL = slope_deg.astype(float); valid = SL != 255
    elig = valid & (SL >= 10) & (SL <= 50) & (lc_d != 7) & (lc_d != 8) & (lc_d != 0)
    fr = {"A": np.where(valid, scarA, 0), "B": np.where(valid, scarB, 0)}
    steep = float(np.nansum(sdeg_fine >= 15))
    out = dict(windows={}, inventory_vs_candidates={})
    for k in "AB":
        km2 = float(fr[k].sum() * cellkm2)
        out["windows"][k] = dict(file=f"Sentinel-2 composites {'2017 to 2020' if k == 'A' else '2020 to 2024'}", scar_km2=km2, share_of_steep_pct=float(km2 / max(1e-9, steep * (cellkm2 / 36)) * 100), n_pixels=0)
    target = {k: v >= 0.04 for k, v in fr.items()}
    ins = [p for p in pts if p["inside"]]
    for k in "AB":
        f = _ndi.maximum_filter(target[k].astype(float), size=5) > 0
        hit = [f[min(h2 - 1, int(p["v"] * h2)), min(w2 - 1, int(p["u"] * w2))] for p in ins]
        out["inventory_vs_candidates"][k] = dict(points_near_candidate=round(float(np.mean(hit)) if hit else 0.0, 3), area_share=round(float(f[valid].mean()), 3))
    enc8 = lambda a: base64.b64encode(np.clip(np.round(a * 255 / 0.5), 0, 255).astype("uint8").tobytes()).decode()
    out["maps"] = dict(A=enc8(fr["A"]), B=enc8(fr["B"]))
    idx = np.where(elig.ravel())[0]
    if len(idx) < 400 or target["A"].sum() < 20 or target["B"].sum() < 20:
        out["calibration"] = None
        return out
    beta = np.radians(SL.ravel()[idx]); cs2 = np.cos(beta) ** 2; sc = np.sin(beta) * np.cos(beta)
    rc = np.array([ROOT_C.get(int(l), 0) for l in lc_d.ravel()[idx]], float)

    def pcrit(z0, c0, p0, m0):
        rn = _mulberry32(7); mem = []
        for _ in range(NMEM):
            zz = z0 * (1 + (rn() * 2 - 1) * .25); cc = c0 * (1 + (rn() * 2 - 1) * .25); tt = np.tan(np.radians(p0 + (rn() * 2 - 1) * 3)); mem.append((zz, cc, tt))
        zz, cc, tt = (np.array(a) for a in zip(*mem))
        den = GW * zz[None] * cs2[:, None] * tt[None]
        c_all = cc[None] + rc[:, None]
        mc0 = (GAM * zz[None] * cs2[:, None] * tt[None] + c_all - GAM * zz[None] * sc[:, None]) / den
        Pc = np.where(mc0 <= m0, 0.0, np.where(mc0 <= 1, (mc0 - m0) * POR * zz[None] * 1000 / INF, np.inf))
        return Pc, (Pc == 0).mean(axis=1) < .5
    def prob_map(theta):
        z0, c0, p0, m0, rain = theta
        Pc, keep = pcrit(z0, c0, p0, m0); p = (Pc <= rain).mean(axis=1); p[~keep] = np.nan; return p
    def auc(score, pos):
        ok = np.isfinite(score); s = score[ok]; y = pos[ok]
        if y.sum() < 20 or (~y).sum() < 20: return np.nan
        rk = rankdata(s); n1 = y.sum(); n0 = len(y) - n1
        return float((rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    bi = (np.arange(h2)[:, None] * 6 // h2); bj = (np.arange(w2)[None, :] * 6 // w2)
    block_a = ((bi + bj) % 2 == 0).ravel()[idx]; block_b = ~block_a
    pos = {k: target[k].ravel()[idx] for k in target}
    P("calibrating soil strength against the scar candidates")
    samples = qmc.scale(qmc.LatinHypercube(d=5, seed=11).random(120), np.array([0.5, 0.0, 24, 0.1, 30]), np.array([3.0, 20.0, 42, 0.8, 300]))
    rows = []
    for th in samples:
        pm = prob_map(tuple(th))
        rows.append(dict(theta=[round(float(v), 2) for v in th], auc_train=auc(pm[block_a], pos["A"][block_a]), auc_test_new_ground=auc(pm[block_b], pos["B"][block_b]), auc_test_new_window=auc(pm[block_a], pos["B"][block_a])))
    ok = [r_ for r_ in rows if np.isfinite(r_["auc_train"])]
    if not ok:
        out["calibration"] = None; return out
    ok.sort(key=lambda r_: -r_["auc_train"]); best = ok[0]; top = ok[:max(5, len(ok) // 20)]
    default = dict(theta=[1.5, 6, 32, 0.3, 240]); pm = prob_map(tuple(default["theta"]))
    default.update(auc_train=auc(pm[block_a], pos["A"][block_a]), auc_test_new_ground=auc(pm[block_b], pos["B"][block_b]), auc_test_new_window=auc(pm[block_a], pos["B"][block_a]))
    sl_ = SL.ravel()[idx]
    slope_only = dict(auc_train=auc(sl_[block_a], pos["A"][block_a]), auc_test_new_ground=auc(sl_[block_b], pos["B"][block_b]), auc_test_new_window=auc(sl_[block_a], pos["B"][block_a]))
    names = ["soil_depth_m", "cohesion_kPa", "friction_deg", "start_saturation", "storm_mm"]
    out["calibration"] = dict(n_samples=len(rows), best=best, default=default, slope_only=slope_only,
                              top5pct_ranges={n: [round(float(min(r_["theta"][i] for r_ in top)), 2), round(float(max(r_["theta"][i] for r_ in top)), 2)] for i, n in enumerate(names)},
                              positives_train=int(pos["A"][block_a].sum()), positives_test_ground=int(pos["B"][block_b].sum()), positives_test_window=int(pos["B"][block_a].sum()),
                              note="cells outside the modelled soil-covered set are not scored")
    return out
