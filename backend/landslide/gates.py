"""§4.7 acceptance gates. Return precise reasons; never quietly substitute another AOI or DEM."""
from __future__ import annotations
import numpy as np
from .errors import GateError

REQUIRED_GEOTECH = ("soil_depth", "effective_cohesion", "friction_angle",
                    "hydraulic_conductivity", "water_table")


def check_grid_compat(grids: dict, canonical_crs: str | None = None):
    """grids: name -> dict(crs, transform(tuple of 6), shape(tuple), units)."""
    problems = []
    ref_name, ref = next(iter(grids.items()))
    for n, g in grids.items():
        if canonical_crs and g["crs"] != canonical_crs:
            problems.append(f"{n}: CRS {g['crs']} != {canonical_crs}")
        if g["crs"] != ref["crs"]:
            problems.append(f"CRS mismatch {n}({g['crs']}) vs {ref_name}({ref['crs']})")
        if tuple(g["shape"]) != tuple(ref["shape"]):
            problems.append(f"shape mismatch {n}{g['shape']} vs {ref_name}{ref['shape']}")
        if not np.allclose(g["transform"], ref["transform"], atol=1e-6):
            problems.append(f"grid transform mismatch {n} vs {ref_name}")
    if problems:
        raise GateError(problems)


def check_nodata_fraction(arr, valid_mask, limit=0.10, name="layer"):
    frac = 1.0 - float(np.count_nonzero(valid_mask & np.isfinite(arr))) / max(arr.size, 1)
    if frac > limit:
        raise GateError([f"{name}: NODATA fraction {frac:.2%} exceeds {limit:.0%}"])
    return frac


def check_geotech(params: dict, mode: str):
    """Reject high-fidelity run if essential geotechnical variables are unknown.

    mode: 'measured' | 'scenario_ensemble'. In scenario mode values must be explicit
    ranges/distributions (dict with min/max or a list), never silent scalars from nowhere.
    """
    missing = [k for k in REQUIRED_GEOTECH if params.get(k) is None]
    if missing:
        raise GateError([f"missing geotechnical parameter: {k}" for k in missing])
    if mode not in ("measured", "scenario_ensemble"):
        raise GateError([f"invalid parameter_mode '{mode}'"])


def check_timestamps_utc(times, name="forcing"):
    t = np.asarray(times, dtype="datetime64[s]")
    if t.size == 0:
        raise GateError([f"{name}: empty time axis"])
    if np.any(np.diff(t) <= np.timedelta64(0, "s")):
        raise GateError([f"{name}: duplicate or non-monotonic timestamps"])


def check_provenance(meta: dict, name="forcing"):
    need = ("source_id", "version", "acquired_utc")
    miss = [k for k in need if not meta.get(k)]
    if miss:
        raise GateError([f"{name}: missing provenance {miss}"])


def check_flow_graph_acyclic(flow_dir_downstream: np.ndarray):
    """flow_dir_downstream: int array of downstream flat index per cell (-1 = outlet/sink)."""
    n = flow_dir_downstream.size
    state = np.zeros(n, dtype=np.int8)   # 0 unvisited,1 in-stack,2 done
    fd = flow_dir_downstream.ravel()
    for s in range(n):
        if state[s]:
            continue
        path, c = [], s
        while c != -1 and state[c] == 0:
            state[c] = 1
            path.append(c)
            c = int(fd[c])
        if c != -1 and state[c] == 1:
            raise GateError(["flow graph contains a cycle (unstable routing)"])
        for p in path:
            state[p] = 2


def check_runout_source(source_mask, volume_m3):
    reasons = []
    if source_mask is None or not np.any(source_mask):
        reasons.append("no runout source polygon/cells")
    if volume_m3 is None or np.any(np.asarray(volume_m3) <= 0):
        reasons.append("source volume missing or non-positive")
    if reasons:
        raise GateError(reasons)


def check_supervised_inventory(n_pos, min_pos=30):
    if n_pos < min_pos:
        raise GateError([f"inventory has {n_pos} positives (<{min_pos}); supervised ML refused; use M01 low-confidence"])
