"""Map Sentinel-2 scar candidates and calibrate the soil-strength scenario against them.

Step 1  Scar candidates: cells where NDVI fell and the bare-soil index rose between two July-September composites,
        on slopes of at least 15 degrees, outside snow, ice and water, in connected groups of 4 or more pixels (2,800 m2).
        Two windows: 2017 to 2020 (calibration) and 2020 to 2024 (test).
Step 2  Calibration: a Latin-hypercube search over cohesion, friction angle, soil depth, starting saturation and storm depth.
        The stability model here is the same equations as the dashboard (verified against it below).
        Train on window 2017-2020 in half of the map blocks; test on window 2020-2024 in the other half (a different time
        window and different ground), and on 2020-2024 in the training blocks.
Writes docs/calibration_results.json and the coarse scar maps the dashboard draws.
"""
import base64, json, re
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage as ndi
from scipy.stats import qmc, rankdata

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "landslide-platform/docs"
DATA = Path("D:/Downloads/CMIP6/landslide-platform/datasets/raw/gilgit")
F = 6
dec = lambda b: np.frombuffer(base64.b64decode(b), np.uint8)

page = (ROOT / "landslide-platform/site/index.html").read_text(encoding="utf-8")
D = json.loads(re.search(r"const D=(\{.*?\});\nconst S=", page, re.S).group(1))
W, H = D["w"], D["h"]
SL = dec(D["slope_deg"]).reshape(H, W).astype(float); LC = dec(D["lc"]).reshape(H, W)
valid = SL != 255
elig = valid & (SL >= 10) & (SL <= 50) & (LC != 7) & (LC != 8) & (LC != 0)

# ------------------------------------------------------------------ Step 1: scar candidates
with rasterio.open(ROOT / "gilgit_dem.tif") as r:
    z = r.read(1).astype("float32"); z[z == r.nodata] = np.nan; res = r.res[0]
gy, gx = np.gradient(np.where(np.isfinite(z), z, np.nanmean(z)), res)
slope_deg = np.degrees(np.arctan(np.hypot(gx, gy)))
wc = rasterio.open(DATA / "worldcover_2021.tif").read(1)
def scars(path):
    with rasterio.open(path) as s:
        a = s.read().astype("float32") / 1000
    dndvi, dbsi, ndvi0, bsi1 = a
    ok = np.isfinite(dndvi) & (a[0] != -32.768)
    m = ok & (dndvi <= -0.12) & (dbsi >= 0.10) & (slope_deg >= 15) & (wc != 70) & (wc != 80) & (wc != 0) & np.isfinite(z) & (z < 4800)
    m = ndi.binary_opening(m, np.ones((2, 2)))
    lab, n = ndi.label(m); size = ndi.sum(m, lab, range(1, n + 1)); keep = np.isin(lab, 1 + np.where(size >= 4)[0])
    return keep
def coarse_fraction(m):
    h2, w2 = H, W
    return m[:h2 * F, :w2 * F].reshape(h2, F, w2, F).mean(axis=(1, 3))
out = dict(windows={})
fr = {}
for name, f in (("A", "s2_change_2017_2020.tif"), ("B", "s2_change_2020_2024.tif")):
    m = scars(DATA / f); fr[name] = coarse_fraction(m)
    out["windows"][name] = dict(file=f, scar_km2=float(m.sum() * res * res / 1e6), share_of_steep_pct=float(m[slope_deg >= 15].mean() * 100), n_pixels=int(m.sum()))
    print(name, out["windows"][name])
target = {k: v >= 0.04 for k, v in fr.items()}

# how do the scar candidates relate to the inventory points?
pts = [p for p in D["pts"] if p["inside"]]
def near_share(mask, tol=2):
    f = ndi.maximum_filter(mask.astype(float), size=2 * tol + 1) > 0
    hit = [f[min(H - 1, int(p["v"] * H)), min(W - 1, int(p["u"] * W))] for p in pts]
    return float(np.mean(hit)), float(f[valid].mean())
inv = {}
for k in ("A", "B"):
    hit, area = near_share(target[k]); inv[k] = dict(points_near_candidate=round(hit, 3), area_share=round(area, 3))
out["inventory_vs_candidates"] = inv

# ------------------------------------------------------------------ Step 2: stability model (same equations as the dashboard)
def mulberry32(a):
    a &= 0xFFFFFFFF
    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rnd
GAM, GW, POR, INF, NMEM = 18.0, 9.81, 0.4, 0.5, 40
ROOT_C = {1: 5, 2: 3, 3: 2, 4: 1}
idx = np.where(elig.ravel())[0]
beta = np.radians(SL.ravel()[idx]); cs2 = np.cos(beta) ** 2; sc = np.sin(beta) * np.cos(beta)
rc = np.array([ROOT_C.get(int(l), 0) for l in LC.ravel()[idx]], float)
def pcrit(z0, c0, p0, m0, root=True):
    rn = mulberry32(7); mem = []
    for _ in range(NMEM):
        zz = z0 * (1 + (rn() * 2 - 1) * .25); cc = c0 * (1 + (rn() * 2 - 1) * .25); tt = np.tan(np.radians(p0 + (rn() * 2 - 1) * 3)); mem.append((zz, cc, tt))
    zz, cc, tt = (np.array(a) for a in zip(*mem))
    den = GW * zz[None] * cs2[:, None] * tt[None]
    c_all = cc[None] + (rc[:, None] if root else 0)
    mc0 = (GAM * zz[None] * cs2[:, None] * tt[None] + c_all - GAM * zz[None] * sc[:, None]) / den
    P = np.where(mc0 <= m0, 0.0, np.where(mc0 <= 1, (mc0 - m0) * POR * zz[None] * 1000 / INF, np.inf))
    keep = (P == 0).mean(axis=1) < .5            # cells already unstable before rain are excluded, as in the dashboard
    return P, keep
def prob_map(theta):
    z0, c0, p0, m0, rain = theta
    P, keep = pcrit(z0, c0, p0, m0)
    p = (P <= rain).mean(axis=1); p[~keep] = np.nan
    return p
def auc(score, pos):
    ok = np.isfinite(score); s = score[ok]; y = pos[ok]
    if y.sum() < 20 or (~y).sum() < 20: return np.nan
    rk = rankdata(s); n1 = y.sum(); n0 = len(y) - n1
    return float((rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

# cross-check against the browser model (S1 saved by validate_simulation.py)
js = DATA / "S1_prob.npy"
if js.exists():
    pj = np.load(js).astype(float) / 255; pm = prob_map((1.5, 6, 32, 0.3, 240))
    full = np.full(H * W, np.nan); full[idx] = pm; diff = np.nanmax(np.abs(full - pj.ravel()[...]) [np.isfinite(full)]) if np.isfinite(full).any() else None
    out["python_vs_browser_max_abs_diff"] = float(diff) if diff is not None else None
    print("python vs browser S1 max abs diff", out["python_vs_browser_max_abs_diff"])

# blocks for the spatial split: 6 x 6 blocks, checkerboard
bi = (np.arange(H)[:, None] * 6 // H); bj = (np.arange(W)[None, :] * 6 // W); block_a = ((bi + bj) % 2 == 0).ravel()[idx]; block_b = ~block_a
pos = {k: target[k].ravel()[idx] for k in target}
sampler = qmc.LatinHypercube(d=5, seed=11)
lo = np.array([0.5, 0.0, 24, 0.1, 30]); hi = np.array([3.0, 20.0, 42, 0.8, 300])
samples = qmc.scale(sampler.random(300), lo, hi)
rows = []
for th in samples:
    pm = prob_map(tuple(th)); rows.append(dict(theta=[round(float(v), 2) for v in th], auc_train=auc(pm[block_a], pos["A"][block_a]),
                                                auc_test_new_ground=auc(pm[block_b], pos["B"][block_b]), auc_test_new_window=auc(pm[block_a], pos["B"][block_a])))
valid_rows = [r_ for r_ in rows if np.isfinite(r_["auc_train"])]
valid_rows.sort(key=lambda r_: -r_["auc_train"]); best = valid_rows[0]; top = valid_rows[:max(5, len(valid_rows) // 20)]
default = dict(theta=[1.5, 6, 32, 0.3, 240]); pm = prob_map(tuple(default["theta"]))
default.update(auc_train=auc(pm[block_a], pos["A"][block_a]), auc_test_new_ground=auc(pm[block_b], pos["B"][block_b]), auc_test_new_window=auc(pm[block_a], pos["B"][block_a]))
sl_ = SL.ravel()[idx].astype(float); slope_only = dict(auc_train=auc(sl_[block_a], pos["A"][block_a]), auc_test_new_ground=auc(sl_[block_b], pos["B"][block_b]), auc_test_new_window=auc(sl_[block_a], pos["B"][block_a]))
names = ["soil_depth_m", "cohesion_kPa", "friction_deg", "start_saturation", "storm_mm"]
out["calibration"] = dict(n_samples=len(rows), best=best, default=default, slope_only=slope_only,
                          top5pct_ranges={n: [round(float(min(r_["theta"][i] for r_ in top)), 2), round(float(max(r_["theta"][i] for r_ in top)), 2)] for i, n in enumerate(names)},
                          positives_train=int(pos["A"][block_a].sum()), positives_test_ground=int(pos["B"][block_b].sum()), positives_test_window=int(pos["B"][block_a].sum()),
                          note="cells outside the modelled soil-covered set are not scored")
print("best", best); print("default", default); print("slope only", slope_only); print("top ranges", out["calibration"]["top5pct_ranges"])

# coarse scar maps for the dashboard
enc = lambda a: base64.b64encode(np.clip(np.round(a * 255 / 0.5), 0, 255).astype("uint8").tobytes()).decode()
out["maps"] = dict(A=enc(np.where(valid, fr["A"], 0)), B=enc(np.where(valid, fr["B"], 0)))
(DOCS / "calibration_results.json").write_text(json.dumps(out), encoding="utf-8")
print("wrote calibration_results.json")
