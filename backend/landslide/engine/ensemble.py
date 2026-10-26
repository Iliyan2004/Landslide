"""Parameter-uncertainty ensemble for the rain trigger: probability of failure per cell and the spread of the failing area.

The single-scenario run (strength quantile q) moves every parameter together to one end of its prior range. Here each member draws EVERY prior
independently (Latin hypercube), so the result is a probability that integrates over what is not known:  p_fail(cell) = fraction of members in which
the cell is mobilisable (stable before the storm, soil-bearing) and its factor of safety falls below 1 during the storm.
Exactness shortcut (same as pipeline.stability_grid): the Green-Ampt front only advances and FS decreases with saturation, so a cell fails at some
time iff FS < 1 at the final saturation; one FS evaluation per member instead of one per time step.
GPU first (torch/CUDA), CPU tensors otherwise; same maths. The member's scenario point goes through the same `post` hook as the main run
(spatial ground, antecedent wetness) so the ensemble and the main run agree."""
from __future__ import annotations
import numpy as np
import torch
from . import trigger as TR
from ..models.infiltration import green_ampt
from ..units import GAMMA_W

KEYS_LOG = ("hydraulic_conductivity",)


def lhs(n, k, rng):
    """(n, k) Latin hypercube on [0,1): one point per stratum in every column, columns independently permuted."""
    u = (np.arange(n)[:, None] + rng.random((n, k))) / n
    for j in range(k):
        u[:, j] = u[rng.permutation(n), j]
    return u


def sample_points(spec, n, seed):
    """n scenario points (dicts shaped like trigger.scenario_point) with independent LHS draws of every ranged prior.
    Soil depth: the member's zmax is drawn from the depth range and zmin follows (zmin/zmax ratio of the prior), so slope-thinning keeps its meaning."""
    rng = np.random.default_rng(int(seed)); ranged = [k for k, v in spec.items() if isinstance(v, dict) and "min" in v]
    U = lhs(n, len(ranged), rng); out = []
    for i in range(n):
        p = {k: v for k, v in spec.items() if k not in ranged}
        for j, k in enumerate(ranged):
            p[k] = TR.at_quantile(spec[k], float(U[i, j]), log=(k in KEYS_LOG))
        if "soil_depth" in spec and isinstance(spec["soil_depth"], dict):
            lo, hi = float(spec["soil_depth"]["min"]), float(spec["soil_depth"]["max"]); zd = p["soil_depth"]
            p["soil_depth_max"] = zd; p["soil_depth_min"] = zd * lo / hi
        out.append(p)
    return out


def _dev():
    if torch.cuda.is_available():
        try:
            torch.zeros(1, device="cuda"); return torch.device("cuda")
        except Exception:
            pass
    return torch.device("cpu")


def _t(x, dev):
    return torch.as_tensor(np.asarray(x, "float32"), device=dev)


def pfail(slope, valid, steps_mm, dt_s, spec, n=48, seed=0, min_slope=10.0, max_soil_slope=45.0, depth_vs_slope=True, post=None, fields=None, cluster=1):
    """Returns {"p_fail": (ny,nx) float32, "area_km2_members": [...], "n": n, "device": str}. `post(sp) -> sp2` applies spatial ground/antecedent."""
    dev = _dev(); pts = sample_points(spec, n, seed); sl = _t(np.nan_to_num(slope), dev); vm = torch.as_tensor(valid, device=dev)
    b = torch.deg2rad(sl); sb, cb = torch.sin(b), torch.cos(b); cand = vm & (sl >= min_slope); soil = vm & (sl <= max_soil_slope)
    acc = torch.zeros(slope.shape, device=dev); areas = []
    for sp in pts:
        sp = post(sp) if post is not None else sp
        slope_e, c_root, wt, m_scale = TR._eff(slope, sp, fields)
        z = _t(TR.soil_depth_field(slope, sp, depth_vs_slope), dev)
        ga = green_ampt.run(steps_mm, dt_s, sp["hydraulic_conductivity"], sp["suction_head"], sp["theta_s"], sp["theta_i"], 1.0, m0=0.0)
        F_end = float(np.max(ga["F_m"])); dth = max(sp["theta_s"] - sp["theta_i"], 1e-6)
        m0 = torch.clamp((z - _t(wt, dev)) / torch.clamp(z, min=1e-9), 0, 1)
        m1 = torch.maximum(m0, torch.clamp(F_end / torch.clamp(dth * z, min=1e-9), 0, 1))
        if m_scale is not None:
            m1 = torch.clamp(m1 * _t(m_scale, dev), 0, 1)
        sbe, cbe = (sb, cb) if slope_e is slope else (torch.sin(torch.deg2rad(_t(slope_e, dev))), torch.cos(torch.deg2rad(_t(slope_e, dev))))
        gam = float(sp["unit_weight"]); c = _t(sp["effective_cohesion"], dev); cr = _t(c_root, dev); tphi = torch.tan(torch.deg2rad(_t(sp["friction_angle"], dev)))

        def fs(m):
            sig = torch.clamp(gam * z * cbe ** 2 - torch.clamp(m, 0, 1) * GAMMA_W * z * cbe ** 2, min=0.0)
            return (c + cr + sig * tphi) / torch.clamp(gam * z * sbe * cbe, min=1e-9)
        stable0 = soil & (fs(m0) >= 1.0)
        fail = stable0 & cand & (fs(m1) < 1.0)
        acc += fail.float()
        areas.append(float(fail.sum()))
    p = (acc / n).cpu().numpy().astype("float32"); p[~valid] = np.nan
    out = {"p_fail": p, "cells_members": areas, "n": n, "device": str(dev)}
    del acc
    if dev.type == "cuda":
        torch.cuda.empty_cache()
    return out
