"""Spatial validation machinery: predictor layers held in RAM, disc sampling under an event's location-uncertainty radius,
matched controls, and spatial block cross-validation.

Why discs: an inventory point with a stated accuracy of r km only tells us the slide is SOMEWHERE within r km. A model is credited if it
ranks the disc well, and controls are scored over discs of the same radius distribution, so large radii cannot manufacture skill."""
from __future__ import annotations
import os
import numpy as np
import rasterio
from pyproj import Transformer
from ..app import paths

LSM = os.path.join(paths.SHARE, "MERGED LANDSLIDE LAYERS", "LSM_CNN_DNN", "outputs", "01_layers")
SLOPE30 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "datasets", "derived", "slope29_north_x2.tif")
LAYERS = ["slope", "elevation", "curvature", "profile_curv", "plan_curv", "geology", "lulc", "twi", "spi", "dist_faults", "dist_rivers",
          "dist_drainage", "dist_roads", "dist_cities", "rainfall", "relief", "roughness", "aspect"]


class Stack:
    """All layers in host RAM. Sampling takes lon/lat arrays and returns {layer: values} (NaN outside/NODATA)."""

    def __init__(self, layers=LAYERS, with_slope30=True, with_ml=True):
        self.arr, self.meta = {}, {}
        for n in layers:
            with rasterio.open(os.path.join(LSM, n + ".tif")) as r:
                a = r.read(1).astype("float32"); a[a <= -9998] = np.nan
                self.arr[n] = a
                self.t, self.crs, self.shape = r.transform, r.crs, r.shape
        with rasterio.open(os.path.join(LSM, "mask.tif")) as r:
            self.mask = r.read(1) > 0
        self.to_lsm = Transformer.from_crs(4326, self.crs, always_xy=True)
        self.inv_t = ~self.t
        if with_ml:
            with rasterio.open(paths.get("LSM_PROB")) as r:
                a = r.read(1).astype("float32"); a[a < 0] = np.nan; self.arr["ml_prob"] = a
        self.s30 = None
        if with_slope30 and os.path.exists(SLOPE30):
            with rasterio.open(SLOPE30) as r:
                self.s30 = r.read(1); self.s30_t = ~r.transform
                self.to_s30 = Transformer.from_crs(4326, r.crs, always_xy=True)

    def _idx(self, lon, lat):
        x, y = self.to_lsm.transform(lon, lat)
        c, r = self.inv_t * (x, y)
        r = np.floor(r).astype(int); c = np.floor(c).astype(int)
        ok = (r >= 0) & (r < self.shape[0]) & (c >= 0) & (c < self.shape[1])
        return np.where(ok, r, 0), np.where(ok, c, 0), ok

    def sample(self, lon, lat, names=None):
        r, c, ok = self._idx(lon, lat)
        out = {}
        for n in (names or list(self.arr)):
            v = self.arr[n][r, c].copy(); v[~ok] = np.nan; out[n] = v
        inside = ok & self.mask[r, c]
        out["_inside"] = inside
        if self.s30 is not None:
            x, y = self.to_s30.transform(lon, lat)
            cc, rr = self.s30_t * (x, y)
            rr = np.floor(rr).astype(int); cc = np.floor(cc).astype(int)
            k = (rr >= 0) & (rr < self.s30.shape[0]) & (cc >= 0) & (cc < self.s30.shape[1])
            v = np.where(k, self.s30[np.where(k, rr, 0), np.where(k, cc, 0)], 255).astype("float32")
            v[v >= 255] = np.nan; out["slope30"] = v / 2.0
        return out


def disc_points(lon0, lat0, radius_km, k, rng):
    """k uniform random points in a disc (flat-earth, fine for <=50 km)."""
    rr = radius_km * np.sqrt(rng.uniform(size=k)); th = rng.uniform(0, 2 * np.pi, k)
    dlat = rr * np.sin(th) / 110.57
    dlon = rr * np.cos(th) / (111.32 * np.cos(np.radians(lat0)))
    return lon0 + dlon, lat0 + dlat


def random_controls(stack, n, radii, rng, margin_km=0.0):
    """Uniform random points in the valid mask with radii drawn from the events' radius distribution."""
    rows, cols = np.where(stack.mask)
    pick = rng.choice(len(rows), n, replace=False)
    x, y = stack.t * (cols[pick] + 0.5, rows[pick] + 0.5)
    lon, lat = Transformer.from_crs(stack.crs, 4326, always_xy=True).transform(x, y)
    return lon, lat, rng.choice(radii, n, replace=True)


def disc_features(stack, lon, lat, radius_km, k=160, seed=0, physics_fn=None, extra=None):
    """Per-point aggregates over k disc samples: dict of arrays. physics_fn(slope_deg_array, layers_dict)->instability index per sample."""
    rng = np.random.default_rng(seed)
    n = len(lon); npts = n
    pl, pb = [], []
    for i in range(n):
        a, b = disc_points(lon[i], lat[i], radius_km[i], k, rng); pl.append(a); pb.append(b)
    pl = np.concatenate(pl); pb = np.concatenate(pb)
    S = stack.sample(pl, pb)
    inside = S["_inside"].reshape(npts, k)
    out = {}
    def agg(name, vals, fn):
        v = vals.reshape(npts, k).astype("float64"); v = np.where(inside, v, np.nan)
        with np.errstate(all="ignore"):
            return fn(v)
    s30 = S.get("slope30", S["slope"])
    out["frac_inside"] = inside.mean(1)
    out["slope_mean"] = agg("s", s30, lambda v: np.nanmean(v, 1)); out["slope_p90"] = agg("s", s30, lambda v: np.nanpercentile(v, 90, axis=1))
    out["slope_max"] = agg("s", s30, lambda v: np.nanmax(v, 1))
    out["slope_frac_15_45"] = agg("s", s30, lambda v: np.nanmean((v >= 15) & (v <= 45), 1))
    for n in ("elevation", "twi", "spi", "curvature", "profile_curv", "plan_curv", "dist_faults", "dist_rivers", "dist_drainage", "rainfall", "relief", "roughness", "dist_roads", "dist_cities", "ml_prob"):
        if n in S:
            out[n + "_mean"] = agg(n, S[n], lambda v: np.nanmean(v, 1))
    out["ml_prob_max"] = agg("m", S["ml_prob"], lambda v: np.nanmax(v, 1)) if "ml_prob" in S else None
    for n, vals in (("geology", range(1, 18)), ("lulc", (1, 2, 4, 5, 7, 8, 9, 10, 11))):
        for v_ in vals:
            out[f"{n}_{v_}"] = agg(n, S[n], lambda v, v_=v_: np.nanmean(v == v_, 1))
    if extra is not None:                                                       # PointRasters: soil texture, bedrock depth, Vs30, lithology group fractions
        for nm in extra.arr:
            vals = extra.sample(pl, pb, nm)
            if nm == "glim":
                for gi, gname in enumerate(extra.groups):
                    out[f"lith_{gname}"] = agg(nm, np.where(np.isnan(vals), np.nan, extra.group_of(vals) == gi).astype("float64"), lambda v: np.nanmean(v, 1))
            else:
                out[nm + "_mean"] = agg(nm, vals, lambda v: np.nanmean(v, 1))
    if physics_fn is not None:
        ph = physics_fn(s30.astype("float64"), S)
        out["phys_mean"] = agg("p", ph, lambda v: np.nanmean(v, 1)); out["phys_p90"] = agg("p", ph, lambda v: np.nanpercentile(v, 90, axis=1))
        out["phys_frac_unstable"] = agg("p", ph, lambda v: np.nanmean(v > 0.5, 1))
    return {k_: v for k_, v in out.items() if v is not None}, S


def blocks(lon, lat, size_deg=1.0):
    return (np.floor(lon / size_deg).astype(int) * 1000 + np.floor(lat / size_deg).astype(int))


class PointRasters:
    """Extra EPSG:4326 GeoTIFF layers (soil texture, lithology, bedrock depth, Vs30) held in RAM and sampled at lon/lat points.
    layers: {name: path}. Values equal to the file nodata (or NaN) come back NaN. Nearest-cell sampling."""

    def __init__(self, layers):
        self.arr, self.inv = {}, {}
        for n, p in layers.items():
            if not os.path.exists(p):
                continue
            with rasterio.open(p) as r:
                a = r.read(1).astype("float32")
                if r.nodata is not None and np.isfinite(r.nodata):
                    a[a == r.nodata] = np.nan
                self.arr[n] = a; self.inv[n] = ~r.transform

    groups = ()
    group_of = staticmethod(lambda v: v)

    def set_lithology_groups(self, groups, class_to_group):
        """GLiM class ids -> group index (groups = names); group_of(values) maps a sampled class-id array to group indices (-1 unknown)."""
        self.groups = tuple(groups); lut = np.full(256, -1, "int16")
        for k_, g_ in class_to_group.items():
            lut[int(k_)] = g_
        self.group_of = staticmethod(lambda v: lut[np.clip(np.nan_to_num(v, nan=0).astype(int), 0, 255)])

    def sample(self, lon, lat, name):
        a = self.arr[name]; c, r = self.inv[name] * (np.asarray(lon, float), np.asarray(lat, float))
        r = np.floor(r).astype(int); c = np.floor(c).astype(int)
        ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
        v = a[np.where(ok, r, 0), np.where(ok, c, 0)].copy(); v[~ok] = np.nan
        return v
