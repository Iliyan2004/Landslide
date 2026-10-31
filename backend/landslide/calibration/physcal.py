"""Batched physics for calibration: Green-Ampt wetting fronts for many (rain series x parameter set) pairs at once, then closed-form infinite-slope FS.
Everything is torch (GPU first, CPU fallback); no per-cell time stepping is needed because min FS over time = FS at the final saturation (see Ch. 5.4)."""
from __future__ import annotations
import numpy as np
import torch

GAMMA_W = 9806.65


def device():
    if torch.cuda.is_available():
        try:
            torch.zeros(1, device="cuda"); return torch.device("cuda")
        except Exception:
            pass
    return torch.device("cpu")


def ga_front(rain_mm_h, Ks, psi, dth, substeps=4):
    """rain_mm_h (S,T) hourly mm; Ks (m/s), psi (m), dth: (S,) -> final cumulative infiltration F (m), shape (S,)."""
    dev = rain_mm_h.device; S, T = rain_mm_h.shape
    F = torch.zeros(S, device=dev, dtype=torch.float64); h = 3600.0 / substeps
    r = rain_mm_h.double() / 1000.0 / substeps
    for t in range(T):
        for _ in range(substeps):
            fc = Ks * (1.0 + psi * dth / torch.clamp(F, min=1e-6)) * h
            F = F + torch.minimum(r[:, t], fc)
    return F


def min_fs_p10(slope_deg, F, params, soil_depth, dth, wt, max_soil_slope=45.0, twi_z=None, beta=0.0, suc=0.0):
    """slope_deg (S,K) -> score per sample: p10 of FS over mobilisable cells (stable when dry, soil-bearing); NaN->+inf if none.
    params: dict of (S,) tensors c (Pa), phi (deg), cr (Pa), gamma (N/m3)."""
    b = torch.deg2rad(slope_deg.double()); cb, sb = torch.cos(b), torch.sin(b)
    z = soil_depth[:, None]; c = params["c"][:, None]; cr = params["cr"][:, None]; g = params["gamma"][:, None]; tphi = torch.tan(torch.deg2rad(params["phi"]))[:, None]
    wtc = wt[:, None] if twi_z is None or beta == 0.0 else torch.clamp(wt[:, None] * torch.exp(-beta * twi_z), 0.3, 25.0)     # topographic water table (engine/wetness.py)
    m0 = torch.clamp((z - wtc) / z, 0, 1)
    m = torch.maximum(m0, torch.clamp(F[:, None] / (dth[:, None] * z), 0, 1))
    def fs(mm):
        u = mm * GAMMA_W * z * cb ** 2
        return (c + cr + suc * (1.0 - torch.clamp(mm, 0, 1)) + torch.clamp(g * z * cb ** 2 - u, min=0) * tphi) / (g * z * sb * cb).clamp(min=1e-9)
    ok = (fs(m0) >= 1.0) & (slope_deg <= max_soil_slope) & (slope_deg >= 5.0)
    f = torch.where(ok, fs(m), torch.full_like(m, float("inf")))
    q = torch.sort(f, dim=1).values
    cnt = ok.sum(1)
    idx = torch.clamp((cnt.double() * 0.10).floor().long(), min=0)
    p10 = q.gather(1, idx[:, None]).squeeze(1)
    return torch.where(cnt > 0, p10, torch.full_like(p10, float("inf")))


STORM_H = 72          # hours of the window treated as the storm (Green-Ampt front); everything before it is antecedent rain


def antecedent_wetness(rain_pre, k, api_wet):
    """rain_pre (S, Tpre) hourly mm in time order (last column = the hour before the storm) -> w in [0,1] per sample; API = sum_i P_i k^i over daily totals."""
    S, T = rain_pre.shape; nd = T // 24
    daily = rain_pre[:, T - nd * 24:].reshape(S, nd, 24).sum(2).double()
    wgt = torch.as_tensor(float(k) ** np.arange(nd, 0, -1), device=rain_pre.device, dtype=torch.float64)     # oldest day gets k^nd, the day before the storm k^1
    return torch.clamp((daily * wgt).sum(1) / float(api_wet), 0, 1)


def score_params(theta, rain, slopes, texture_ks_psi_dth, bounds_names=None, ground=None, twi_z=None):
    """theta: dict name->float. rain (S,T) hourly mm; the last STORM_H hours drive the wetting front, the earlier hours set the antecedent state (theta keys
    k, api_wet, s_dry, s_wet, f_wt; absent or api_wet >= 1e6 means no antecedent effect). Returns instability score per sample (higher = more unstable).
    ground: optional dict of (S,K) tensors multipliers {'c': ..., 'phi': ...} for spatially varying strength."""
    dev = rain.device; S = rain.shape[0]
    ks, psi, dth0 = texture_ks_psi_dth; por = float(theta.get("theta_s", dth0 + 0.25))
    storm, pre = rain[:, -STORM_H:], rain[:, :-STORM_H]
    if "api_wet" in theta and float(theta["api_wet"]) < 1e6 and pre.shape[1] >= 24:
        w = antecedent_wetness(pre, theta["k"], theta["api_wet"]); thr = 0.05
        th_i = torch.clamp(thr + (por - thr) * (theta["s_dry"] + (theta["s_wet"] - theta["s_dry"]) * w), max=por - 0.02)
        dth = por - th_i; wt = float(theta["wt"]) * (1.0 - float(theta["f_wt"]) * w)
    else:
        dth = torch.full((S,), float(dth0), device=dev, dtype=torch.float64); wt = torch.full((S,), float(theta["wt"]), device=dev, dtype=torch.float64)
    ks_t = torch.full((S,), float(theta.get("ks", ks)), device=dev, dtype=torch.float64)
    F = ga_front(storm, ks_t, psi, dth)
    P = {k_: torch.full((S,), float(theta[k_]), device=dev, dtype=torch.float64) for k_ in ("c", "phi", "cr")}
    P["gamma"] = torch.full((S,), 18000.0, device=dev, dtype=torch.float64)
    z = torch.full((S,), float(theta["z"]), device=dev, dtype=torch.float64)
    f = min_fs_p10(slopes, F, P, z, dth if torch.is_tensor(dth) else torch.full((S,), float(dth), device=dev, dtype=torch.float64), wt,
                   twi_z=twi_z, beta=float(theta.get("beta", 0.0)), suc=float(theta.get("suc", 0.0)))
    return -torch.where(torch.isinf(f), torch.full_like(f, 10.0), f.clamp(max=10.0))
