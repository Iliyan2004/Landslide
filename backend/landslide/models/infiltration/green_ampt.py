"""Green-Ampt event infiltration + wetting-front pore-pressure SCENARIO (methodology §5.3).

f_c = Ks [1 + psi_f (theta_s - theta_i)/F].  Infiltration = min(rain rate, f_c). Excess leaves as runoff
(no ponding storage is simulated -> conservative for pore pressure, stated in outputs).
Pore pressure proxy: saturated depth = wetting-front depth Zf = F/(theta_s-theta_i), m = clip(Zf/z).
This is a bounded SCENARIO, NOT groundwater at the slip surface. Zero Ks => zero infiltration.
"""
from __future__ import annotations
import numpy as np

MIN_F = 1e-6   # m, numerical seed for F so that f_c is finite


def run(rain_mm_per_step, dt_s, Ks, psi_f, theta_s, theta_i, z_slip, m0=0.0, substeps=20):
    """Vectorised over cells. rain_mm_per_step: (T,) depth in mm per step (accumulated, NOT intensity).

    Returns dict with F(t), infiltration(t), runoff(t) [m], m(t) and mass-balance residual.
    Shapes: arrays broadcast against `Ks`; outputs are (T, *Ks.shape).
    """
    rain = np.asarray(rain_mm_per_step, dtype="float64") / 1000.0           # m per step
    if np.any(rain < 0) or not np.all(np.isfinite(rain)):
        raise ValueError("rainfall contains negative/NaN values (gate: precipitation provenance/QC)")
    Ks, psi_f, th_s, th_i, zs, m0 = [np.asarray(a, dtype="float64") for a in (Ks, psi_f, theta_s, theta_i, z_slip, m0)]
    dth = np.maximum(th_s - th_i, 1e-6)
    shape = np.broadcast(Ks, psi_f, dth, zs).shape
    F = np.full(shape, 0.0)
    T = rain.size
    infil = np.zeros((T,) + shape)
    runoff = np.zeros((T,) + shape)
    Fh = np.zeros((T,) + shape)
    mh = np.zeros((T,) + shape)
    h = dt_s / substeps
    sat_cap = dth * zs                       # max infiltrated depth before front reaches slip surface
    for t in range(T):
        avail = np.broadcast_to(rain[t] / substeps, shape).copy()
        inf_t = np.zeros(shape)
        for _ in range(substeps):
            Fe = np.maximum(F, MIN_F)
            fc = Ks * (1.0 + psi_f * dth / Fe) * h        # capacity this sub-step (m)
            take = np.minimum(avail, fc)
            take = np.where(Ks <= 0, 0.0, take)
            F = F + take
            inf_t += take
        infil[t] = inf_t
        runoff[t] = rain[t] - inf_t
        Fh[t] = F
        mh[t] = np.maximum(m0, np.clip(F / np.maximum(sat_cap, 1e-9), 0.0, 1.0))
    resid = rain.sum() - infil.sum(axis=0) - runoff.sum(axis=0)
    return {"F_m": Fh, "infiltration_m": infil, "runoff_m": runoff, "m": mh,
            "mass_balance_residual_m": resid,
            "assumptions": ["no ponding storage", "saturated above wetting front",
                            "m is a scenario proxy not groundwater head"]}


def m_from_water_table(z_slip, depth_to_water_table):
    """Baseline saturated fraction of slip-surface depth from a (scenario/measured) water table depth."""
    z = np.asarray(z_slip, float)
    return np.clip((z - np.asarray(depth_to_water_table, float)) / np.maximum(z, 1e-9), 0.0, 1.0)
