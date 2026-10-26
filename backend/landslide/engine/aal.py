"""Average annual loss (AAL) from a set of return-period scenario losses.

EAL = integral of loss over annual exceedance probability p = 1/T:
  between the rarest and the most frequent scenario: trapezoid in p
  beyond the rarest (p < 1/Tmax): loss held at the rarest scenario's value (conservative flat tail, stated)
  between the most frequent scenario (p = 1/Tmin) and p = 1: loss falls linearly to zero at p = 1 (storms that frequent do little damage)
ASSUMPTION carried into every result: the frequency of a loss equals the frequency of the rainfall that drives it (a T-year storm gives the T-year loss).
That ignores antecedent wetness and the fact that most storms of a given depth cause no landslide, so it is an order-of-magnitude figure."""
from __future__ import annotations
import numpy as np


def eal(T, loss):
    T = np.asarray(T, float); L = np.asarray(loss, float)
    o = np.argsort(T); T, L = T[o], L[o]
    p = 1.0 / T                                         # descending in T -> ascending order below
    p_asc, L_asc = p[::-1], L[::-1]                     # p from rare to frequent
    body = float(np.trapezoid(L_asc, p_asc) if hasattr(np, "trapezoid") else np.trapz(L_asc, p_asc))
    tail_rare = float(L_asc[0] * p_asc[0])                              # 0 .. p_min at the rarest loss
    tail_freq = float(0.5 * L_asc[-1] * (1.0 - p_asc[-1]))              # p_max .. 1, linear to zero
    return {"eal": body + tail_rare + tail_freq, "parts": {"between_scenarios": body, "rare_tail": tail_rare, "frequent_tail": tail_freq}}


def loss_curve(T, loss):
    o = np.argsort(T)
    return [{"T": float(np.asarray(T)[i]), "p": 1.0 / float(np.asarray(T)[i]), "loss": float(np.asarray(loss)[i])} for i in o]


def compute(run_fn, T_list, progress=lambda s, f: None):
    """run_fn(T) -> {'loss_pkr':..., 'impacted_km2':..., 'failing_km2':..., 'depth_mm':..., 'run_id':...}. Returns the scenario table and the EAL."""
    rows = []
    for i, T in enumerate(T_list):
        progress(f"T={T} y", i / len(T_list))
        r = run_fn(T); r["T"] = T; rows.append(r)
    e = eal([r["T"] for r in rows], [r["loss_pkr"] for r in rows])
    return {"scenarios": rows, "eal_pkr": e["eal"], "parts": e["parts"], "curve": loss_curve([r["T"] for r in rows], [r["loss_pkr"] for r in rows]),
            "assumption": "loss frequency equals rainfall frequency; frequent-tail linear to zero at p=1; rare tail held flat"}
