"""Terrain & hydrology derivatives (methodology §3, §4.2, §5.1). Pure numpy; metric CRS required.

All functions take `dem` (2D float array, metres) and `dx`, `dy` (cell size, metres). NaN = NODATA.
Row index increases southward (north-up raster).
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage as ndi

D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _pad(dem):
    return np.pad(dem, 1, mode="edge")


def gradients(dem, dx, dy):
    """Horn (1981) 3x3 finite differences -> dz/dx (east), dz/dy (north)."""
    p = _pad(dem)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * dy)   # north positive (rows go south)
    return dzdx, dzdy


def slope_aspect(dem, dx, dy):
    dzdx, dzdy = gradients(dem, dx, dy)
    beta = np.arctan(np.hypot(dzdx, dzdy))
    slope_deg = np.rad2deg(beta)
    aspect = np.rad2deg(np.arctan2(-dzdx, -dzdy))   # downslope azimuth, clockwise from north
    aspect = np.mod(aspect, 360.0)
    aspect = np.where(slope_deg < 1e-6, np.nan, aspect)
    return {"slope_deg": slope_deg, "slope_pct": 100.0 * np.tan(beta), "aspect_deg": aspect}


def curvature(dem, dx, dy):
    """Zevenbergen & Thorne (1987) plan & profile curvature (1/m). Sign: convex up +  (profile)."""
    p = _pad(dem)
    z1, z2, z3 = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    z4, z5, z6 = p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:]
    z7, z8, z9 = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    L = dx
    D = ((z4 + z6) / 2 - z5) / L**2
    E = ((z2 + z8) / 2 - z5) / L**2
    F = (-z1 + z3 + z7 - z9) / (4 * L**2)
    G = (-z4 + z6) / (2 * L)
    H = (z2 - z8) / (2 * L)
    den = G**2 + H**2
    safe = np.where(den < 1e-12, np.nan, den)
    profile = -2 * (D * G**2 + E * H**2 + F * G * H) / safe
    plan = 2 * (D * H**2 + E * G**2 - F * G * H) / safe
    return {"profile_curvature": profile, "plan_curvature": plan}


def roughness_indices(dem, win=3):
    """TRI (Riley 1999), TPI (Weiss 2001) and std-dev roughness over `win` cells."""
    mean = ndi.uniform_filter(dem, win, mode="nearest")
    tpi = dem - mean
    tri = np.sqrt(ndi.uniform_filter((dem - mean) ** 2, win, mode="nearest"))
    sq = ndi.uniform_filter(dem ** 2, win, mode="nearest")
    rough = np.sqrt(np.maximum(sq - mean**2, 0))
    return {"TPI": tpi, "TRI": tri, "roughness": rough}


def local_relief(dem, window_cells):
    """H = max(z)-min(z) in window; window scale MUST be recorded in metadata (§5.1)."""
    return ndi.maximum_filter(dem, window_cells) - ndi.minimum_filter(dem, window_cells)


def fill_pits(dem):
    """Priority-flood fill of spurious depressions (Barnes et al. 2014, epsilon=0). Raw DEM untouched."""
    import heapq
    nr, nc = dem.shape
    filled = dem.copy()
    seen = np.zeros(dem.shape, bool)
    heap = []
    for r in range(nr):
        for c in range(nc):
            if r in (0, nr - 1) or c in (0, nc - 1) or np.isnan(dem[r, c]):
                heapq.heappush(heap, (dem[r, c] if not np.isnan(dem[r, c]) else -np.inf, r, c))
                seen[r, c] = True
    while heap:
        z, r, c = heapq.heappop(heap)
        for dr, dc in D8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < nr and 0 <= cc < nc and not seen[rr, cc]:
                seen[rr, cc] = True
                if filled[rr, cc] < z:
                    filled[rr, cc] = z
                heapq.heappush(heap, (filled[rr, cc], rr, cc))
    return filled


def d8_flow(dem, dx, dy):
    """D8 downstream index per cell (-1 = outlet/flat sink) and flow accumulation (cell counts).

    Cells are processed high->low so accumulation is exact and cycle-free on a filled DEM.
    """
    nr, nc = dem.shape
    flat = dem.ravel()
    down = -np.ones(dem.size, dtype=np.int64)
    dist = {(dr, dc): np.hypot(dr * dy, dc * dx) for dr, dc in D8}
    best = np.zeros(dem.shape)
    for dr, dc in D8:
        sh = np.full(dem.shape, np.nan)
        r0, r1 = max(0, -dr), nr - max(0, dr)
        c0, c1 = max(0, -dc), nc - max(0, dc)
        sh[r0:r1, c0:c1] = dem[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        drop = (dem - sh) / dist[(dr, dc)]
        better = np.nan_to_num(drop, nan=-np.inf) > best
        better &= np.isfinite(dem)
        rr, cc = np.nonzero(better)
        down[(rr * nc + cc)] = (rr + dr) * nc + (cc + dc)
        best = np.where(better, drop, best)
    order = np.argsort(-np.nan_to_num(flat, nan=-np.inf), kind="stable")
    acc = np.where(np.isfinite(flat), 1.0, 0.0)
    for i in order:
        j = down[i]
        if j >= 0:
            acc[j] += acc[i]
    return {"downstream": down.reshape(dem.shape), "flow_accum_cells": acc.reshape(dem.shape)}


def hydrology_indices(slope_deg, accum_cells, dx, dy, min_tan=1e-3):
    """Specific contributing area a = A/width (m); TWI=ln(a/tan b) with floors; SPI=a tan b."""
    A = accum_cells * dx * dy                     # m^2
    a = A / dx                                    # m (specific catchment area)
    tanb = np.maximum(np.tan(np.deg2rad(slope_deg)), min_tan)
    return {"contributing_area_m2": A, "specific_area_m": a,
            "TWI": np.log(np.maximum(a, dx) / tanb), "SPI": a * tanb}


def ls_factor(slope_deg, accum_cells, dx, dy, variant="desmet_govers_1996"):
    """RUSLE LS (variant logged!). Desmet & Govers (1996) with McCool slope term."""
    if variant != "desmet_govers_1996":
        raise ValueError("only desmet_govers_1996 implemented; log variant if adding others")
    beta = np.deg2rad(slope_deg)
    sinb = np.sin(beta)
    m = (np.sin(beta) / 0.0896) / (3 * sinb**0.8 + 0.56)
    m = m / (1 + m)
    cell = dx
    A = accum_cells * dx * dy
    Ain = np.maximum(A, cell**2)
    L = ((Ain + cell**2) ** (m + 1) - Ain ** (m + 1)) / (cell ** (m + 2) * 22.13 ** m)
    S = np.where(np.tan(beta) < 0.09, 10.8 * sinb + 0.03, 16.8 * sinb - 0.50)
    return np.maximum(L * S, 0)


def derive_all(dem, dx, dy, relief_window_cells=11):
    """Full derived-layer bundle. Returns dict of arrays; caller attaches metadata (§3)."""
    out = {"elevation": dem}
    out.update(slope_aspect(dem, dx, dy))
    out.update(curvature(dem, dx, dy))
    out.update(roughness_indices(dem))
    out["local_relief"] = local_relief(dem, relief_window_cells)
    cond = fill_pits(dem)
    fl = d8_flow(cond, dx, dy)
    out.update(fl)
    out.update(hydrology_indices(out["slope_deg"], fl["flow_accum_cells"], dx, dy))
    out["LS_factor"] = ls_factor(out["slope_deg"], fl["flow_accum_cells"], dx, dy)
    out["_meta"] = {"relief_window_cells": relief_window_cells, "LS_variant": "desmet_govers_1996",
                    "curvature": "zevenbergen_thorne_1987", "flow": "d8_priority_flood_filled",
                    "TWI_note": "topographic index, NOT groundwater depth"}
    return out
