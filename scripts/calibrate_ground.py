#!/usr/bin/env python3
"""Calibrate the SPATIAL ground model (lithology, soil texture, regolith depth, land-cover roots) against the report inventory.

Design (spatial, no rainfall): events = unique inventory reports (rain / unknown / quake triggers, location accuracy given) inside the northern study
area; controls = uniformly random points over the same valid mask, 10 per event, with the events' radius distribution. Every point is scored over 160
random cells inside its accuracy disc by the 90th percentile of the physical instability index (1 - m_crit: how little saturation brings the cell to
FS = 1; engine/ground.py supplies the per-cell cohesion, friction, slip depth and root cohesion from the ground layers).
Fits (differential evolution, maximising AUC on training blocks with a small ridge penalty) five nested variants:
    base              slope-only physics with fitted c, phi, z (no ground layers)
    +lithology        + GLiM group weights
    +texture          + SoilGrids clay / sand / coarse-fragment coefficients
    +regolith         + slip depth capped by depth-to-bedrock
    +roots            + land-cover root-cohesion scale
    all               everything
Skill is the AUC on HELD-OUT 1-degree spatial blocks (5 folds); a ground layer is adopted only if it beats the base by more than 0.01 AUC held out.
The inventory is mostly road- and village-reported (report-aware), so the AUC measures agreement with REPORTED landslides.
Writes docs/validation/ground_calibration.json (and the adopted coefficient block, to be copied into configs/ground_classes.yaml).   *** run only on request ***"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd, torch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D, spatial as SP, stats as ST        # noqa: E402
from landslide.engine import ground as GR                                           # noqa: E402
from scipy.optimize import differential_evolution                                   # noqa: E402

K, N_C = 160, 10
GAMMA, GAMMA_W = 18000.0, 9806.65
EXT = ROOT / "datasets/external"
EXTRA = {"clay": [EXT / "soilgrids" / f"clay_{d}.tif" for d in GR.TEX_DEPTHS], "sand": [EXT / "soilgrids" / f"sand_{d}.tif" for d in GR.TEX_DEPTHS],
         "cf": [EXT / "soilgrids" / f"cfvo_15-30cm.tif"], "bd": [EXT / "soilgrids" / "bdticm_cm.tif"], "glim": [EXT / "glim" / "glim_pk.tif"]}
GROUPS = GR.GROUP_NAMES
LULC_ROOT_KPA = GR.load_cfg()["landcover_root_cohesion_kpa"]

# name: (low, high, default). Defaults = the platform's shipped scenario values / neutral ground.
BASE = {"c": (500.0, 15000.0, 3000.0), "phi": (18.0, 42.0, 30.0), "z": (0.5, 4.0, 1.5)}
LITH = {f"w_{g}": (-1.5, 1.5, 0.0) for g in GROUPS} | {"kphi": (0.0, 0.3, 0.0)}
TEX = {"a_c": (-1.5, 1.5, 0.0), "a_phi": (-0.5, 0.5, 0.0), "a_cf": (-0.5, 0.5, 0.0)}
REG = {"bd_scale": (0.3, 5.0, 1.0)}
ROOT_ = {"s_cr": (0.0, 3.0, 1.0)}
VARIANTS = {"base": BASE, "+lithology": BASE | LITH, "+texture": BASE | TEX, "+regolith": BASE | REG, "+roots": BASE | ROOT_, "all": BASE | LITH | TEX | REG | ROOT_}


def build_points():
    rng = np.random.default_rng(7)
    df = D.load(); df = df[df.trigger.isin(["rain", "unknown", "quake"])].reset_index(drop=True)
    st = SP.Stack(layers=["slope", "lulc"], with_ml=False)
    df = df[st.sample(df.lon.values, df.lat.values, ["slope"])["_inside"]].reset_index(drop=True)
    clon, clat, crad = SP.random_controls(st, len(df) * N_C, df.radius_km.values, rng)
    lon = np.r_[df.lon.values, clon]; lat = np.r_[df.lat.values, clat]; rad = np.r_[df.radius_km.values, crad]
    y = np.r_[np.ones(len(df)), np.zeros(len(clon))].astype(int)
    pl, pb = [], []
    for i in range(len(lon)):
        a, b = SP.disc_points(lon[i], lat[i], rad[i], K, rng); pl.append(a); pb.append(b)
    pl = np.concatenate(pl); pb = np.concatenate(pb)
    S = st.sample(pl, pb, ["slope", "lulc"]); n = len(lon)
    out = {"slope": S.get("slope30", S["slope"]).reshape(n, K), "lulc": S["lulc"].reshape(n, K), "inside": S["_inside"].reshape(n, K)}
    pr = SP.PointRasters({k: str(v[0]) for k, v in EXTRA.items()})
    for name, paths_ in EXTRA.items():
        if name in ("glim",):
            continue
        parts = [SP.PointRasters({name: str(p)}).sample(pl, pb, name) for p in paths_ if p.exists()]
        if parts:
            v = np.nanmean(np.stack(parts), 0)
            out[name] = (v * (0.1 if name in ("clay", "sand", "cf") else 0.01)).astype("float32").reshape(n, K)    # g/kg -> %, cm3/dm3 -> %, cm -> m
    if "glim" in pr.arr:
        code = {int(k): v["code"] for k, v in json.load(open(EXT / "glim" / "glim_classes.json")).items()}
        g = pr.sample(pl, pb, "glim"); gi = np.full(g.shape, -1, "int8")
        for k_, c_ in code.items():
            if c_ in GR.GROUPS:
                gi[np.isfinite(g) & (np.rint(np.nan_to_num(g)) == k_)] = GROUPS.index(GR.GROUPS[c_])
        out["grp"] = gi.reshape(n, K)
    meta = pd.DataFrame({"lon": lon, "lat": lat, "rad": rad, "y": y, "block": SP.blocks(lon, lat, 1.0)})
    return meta, out


def to_dev(arrs, dev):
    T = {}
    for k, v in arrs.items():
        T[k] = torch.as_tensor(np.nan_to_num(v, nan=-1) if v.dtype == np.int8 else v, device=dev)
    return T


def root_table(dev):
    lut = torch.zeros(16, device=dev, dtype=torch.float32)
    for k, kpa in LULC_ROOT_KPA.items():
        lut[int(k)] = float(kpa) * 1000.0
    return lut


def score(theta, T, lut, variant_keys):
    """p90 over each disc of the instability index. theta: dict (missing -> default)."""
    th = {k: (theta[k] if k in theta else v[2]) for k, v in (BASE | LITH | TEX | REG | ROOT_).items()}
    sl = T["slope"]; b = torch.deg2rad(torch.nan_to_num(sl, nan=0.0)); cb, tb = torch.cos(b), torch.tan(b)
    c = torch.full_like(sl, th["c"]); phi = torch.full_like(sl, th["phi"]); fm = torch.ones_like(sl)
    if "w_unconsolidated" in variant_keys and "grp" in T:
        w = torch.zeros_like(sl)
        for j, g in enumerate(GROUPS):
            w = torch.where(T["grp"] == j, torch.full_like(sl, th[f"w_{g}"]), w)
        c = c * torch.exp(w); fm = fm * (1.0 + th["kphi"] * w)
    if "a_c" in variant_keys and "clay" in T:
        clay = torch.where(torch.isfinite(T["clay"]), T["clay"], torch.full_like(sl, 20.0)); sand = torch.where(torch.isfinite(T["sand"]), T["sand"], torch.full_like(sl, 40.0))
        cf = torch.where(torch.isfinite(T["cf"]), T["cf"], torch.zeros_like(sl)) if "cf" in T else torch.zeros_like(sl)
        c = c * torch.exp(th["a_c"] * (clay - 20.0) / 20.0); fm = fm * (1.0 + th["a_phi"] * (sand - 40.0) / 40.0 + th["a_cf"] * cf / 30.0)
    phi = torch.clamp(phi * fm, 12.0, 45.0); tphi = torch.tan(torch.deg2rad(phi))
    z = torch.full_like(sl, th["z"])
    if "bd_scale" in variant_keys and "bd" in T:
        cap = torch.clamp(th["bd_scale"] * T["bd"], min=0.3); z = torch.minimum(z, torch.where(torch.isfinite(cap), cap, z))
    if "s_cr" in variant_keys:
        lc = torch.nan_to_num(T["lulc"], nan=0.0).long().clamp(0, 15); cr = lut[lc] * th["s_cr"]
    else:
        cr = torch.where(torch.isfinite(T["lulc"]), lut[torch.nan_to_num(T["lulc"], nan=0.0).long().clamp(0, 15)], torch.zeros_like(sl))      # shipped root table, scale 1
    mc = ((c + cr) / (GAMMA * z * cb ** 2) + tphi - tb) * GAMMA / (GAMMA_W * tphi)
    idx = 1.0 - torch.clamp(mc, 0.0, 1.0); idx = torch.where(mc <= 0.0, torch.ones_like(idx), idx)
    idx = torch.where((sl > 45.0) | (sl < 5.0) | ~torch.isfinite(sl), torch.zeros_like(idx), idx)
    idx = torch.where(T["inside"], idx, torch.full_like(idx, float("nan")))
    ok = torch.isfinite(idx); cnt = ok.sum(1)                                              # sort-based p90 over the valid cells (nanquantile is ~100x slower)
    srt = torch.sort(torch.where(ok, idx, torch.full_like(idx, -1.0)), dim=1).values
    pos = (idx.shape[1] - cnt) + torch.floor(0.9 * (cnt - 1).clamp(min=0).float()).long()
    q = srt.gather(1, pos.clamp(max=idx.shape[1] - 1)[:, None]).squeeze(1)
    return torch.where(cnt > 0, q, torch.full_like(q, float("nan"))).cpu().numpy()


def main():
    t0 = time.time(); dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    try:
        torch.zeros(1, device=dev)
    except Exception:
        dev = torch.device("cpu")
    meta, arrs = build_points(); print("points", len(meta), "events", int(meta.y.sum()), "device", dev, round(time.time() - t0), "s", flush=True)
    cover = {k: float(np.isfinite(v).mean()) for k, v in arrs.items() if v.dtype != np.int8} | ({"grp": float((arrs["grp"] >= 0).mean())} if "grp" in arrs else {})
    use = arrs["inside"].mean(1) > 0.5; meta = meta[use].reset_index(drop=True); arrs = {k: v[use] for k, v in arrs.items()}
    T = to_dev(arrs, dev); lut = root_table(dev); y = meta.y.values
    ub = np.unique(meta.block); rng = np.random.default_rng(1); perm = rng.permutation(len(ub)); fold_of = {g: i % 5 for g, i in zip(ub[perm], range(len(ub)))}; f = meta.block.map(fold_of).values
    res = {"n_points": int(len(meta)), "n_events": int(y.sum()), "layer_coverage": cover, "variants": {}}
    a_s, lo_s, hi_s = ST.auc_ci(y, np.nan_to_num(arrs["slope"].mean(1)), n_boot=200, group=meta.block.values)
    res["slope_mean_auc_no_fit"] = {"auc": a_s, "ci95": [lo_s, hi_s]}
    for vname, space in VARIANTS.items():
        if vname == "+lithology" and "grp" not in T or vname == "+texture" and "clay" not in T or vname == "+regolith" and "bd" not in T:
            res["variants"][vname] = {"skipped": "layer missing"}; print(vname, "skipped", flush=True); continue
        names = list(space); bnd = [(space[k][0], space[k][1]) for k in names]; keys = set(names)
        def pen(x):
            return 0.002 * sum(((v - space[k][2]) / max(space[k][1] - space[k][0], 1e-9)) ** 2 for k, v in zip(names, x) if k not in BASE)
        folds = []
        for k in range(5):
            tr, te = f != k, f == k
            if y[te].sum() < 3:
                continue
            def loss(x):
                s = score(dict(zip(names, x)), T, lut, keys); m = tr & np.isfinite(s); return -ST.auc(y[m], s[m]) + pen(x)
            r = differential_evolution(loss, bnd, seed=k, maxiter=80, popsize=12, tol=1e-5, polish=False)
            s = score(dict(zip(names, r.x)), T, lut, keys); s0 = score({}, T, lut, keys); m = te & np.isfinite(s)
            folds.append({"fold": k, "auc_heldout": ST.auc(y[m], s[m]), "auc_default_heldout": ST.auc(y[m], s0[m]), "params": dict(zip(names, map(float, r.x))), "events_test": int(y[te].sum())})
            print(vname, k, round(folds[-1]["auc_default_heldout"], 3), "->", round(folds[-1]["auc_heldout"], 3), flush=True)
        res["variants"][vname] = {"folds": folds, "auc_heldout": float(np.mean([x["auc_heldout"] for x in folds])), "auc_default_heldout": float(np.mean([x["auc_default_heldout"] for x in folds]))}
    ok = {k: v for k, v in res["variants"].items() if "auc_heldout" in v}
    best = max(ok, key=lambda k: ok[k]["auc_heldout"]); base_auc = ok["base"]["auc_heldout"]; res["best_variant"] = best
    res["adopt"] = bool(best != "base" and ok[best]["auc_heldout"] > base_auc + 0.01)
    if res["adopt"] or best == "base":
        names = list(VARIANTS[best]); keys = set(names)
        def loss_all(x):
            s = score(dict(zip(names, x)), T, lut, keys); m = np.isfinite(s); return -ST.auc(y[m], s[m]) + 0.002 * sum(((v - VARIANTS[best][k][2]) / max(VARIANTS[best][k][1] - VARIANTS[best][k][0], 1e-9)) ** 2 for k, v in zip(names, x) if k not in BASE)
        r = differential_evolution(loss_all, [(VARIANTS[best][k][0], VARIANTS[best][k][1]) for k in names], seed=99, maxiter=100, popsize=12, tol=1e-5, polish=False)
        res["final_fit_all_data"] = {"variant": best, "params": dict(zip(names, map(float, r.x))), "train_auc": -r.fun,
                                     "note": "fitted on all data (in-sample); the held-out AUC above is the honest skill"}
    res["note"] = ("spatial skill against REPORTED landslides (report-aware inventory; random-location controls); ground layers adopted only if > +0.01 held-out AUC over the base fit; "
                   "lithology weights are cohesion multipliers exp(w) by GLiM group")
    (ROOT / "docs/validation/ground_calibration.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: (v if k != "variants" else {n: {kk: vv for kk, vv in d.items() if kk != "folds"} for n, d in v.items()}) for k, v in res.items()}, indent=1)[:2500])


if __name__ == "__main__":
    main()
