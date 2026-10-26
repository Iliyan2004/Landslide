#!/usr/bin/env python3
"""Check simulated debris-flow runout against the Corominas (1996) H = a L^b relations and tune (mu, xi) per type.   *** COMPUTE HEAVY: run only on request ***
Method: synthetic channelised slopes of several heights, volumes 1e4..1e6 m3 released as a slab; simulate to rest (GPU); H = elevation drop source->furthest depth>0.3 m cell,
L = path length. Ratio = H_sim / (a L_sim^b). A calibrated (mu, xi) puts the median ratio near 1 with a spread inside the published scatter (factor ~2).
Real Pakistani events (if the owner supplies deposits) can replace the synthetic slopes. Writes docs/validation/runout_calibration.json."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.engine.flow_torch import FlowStateGPU, available      # noqa: E402
from landslide.engine.flow import FlowState                          # noqa: E402

COR = {"debris_flow": (1.109, 0.857), "landslide": (2.606, 0.669), "rock_avalanche": (1.758, 0.859)}


def channel_slope(n=260, dx=20.0, h=800.0, L=2400.0, width=7):
    """V-shaped valley with a concave long profile (steep source, flattening toward the fan)."""
    x = np.arange(n) * dx; prof = h * np.exp(-x / (0.45 * L)); prof = prof - prof[-1]
    Z = np.tile(prof[None, :], (n, 1)); rows = np.abs(np.arange(n)[:, None] - n // 2); Z = Z + np.minimum(rows, 60) * dx * 0.55
    return Z.astype("float32"), dx


def one(mu, xi, vol, h, device):
    Z, dx = channel_slope(h=h); n = Z.shape[0]; S = FlowStateGPU(Z, dx) if device else FlowState(Z, dx)
    rel = np.zeros_like(Z); depth = 4.0; cells = int(vol / depth / dx**2); w = max(3, int(np.sqrt(cells))); l = max(3, cells // w); rel[n//2-w//2:n//2+w//2+1, 5:5+l] = depth
    S.add_release(rel)
    for _ in range(int(900 / 0.1)):
        S.step(0.1, mu, xi)
    fin = S.final() if device else {"Hmax": S.Hmax}; wet = np.argwhere(fin["Hmax"] > 0.3)
    if len(wet) == 0: return None
    c0 = 5; cmax = wet[:, 1].max(); Lr = (cmax - c0) * dx; Hdrop = float(Z[n//2, c0] - Z[n//2, cmax]); return Hdrop, Lr


def main():
    dev = available(); out = {"relation": "Corominas 1996 H = a L^b", "types": {}}
    for name, (mu, xi) in {"debris_flow": (0.12, 200.0), "landslide": (0.30, 300.0)}.items():
        a, b = COR["debris_flow" if name == "debris_flow" else "landslide"]; rat = []
        for vol in (1e4, 1e5, 1e6):
            for h in (500.0, 800.0, 1200.0):
                r = one(mu, xi, vol, h, dev)
                if r and r[1] > 0: rat.append(r[0] / (a * r[1] ** b))
        out["types"][name] = {"mu": mu, "xi": xi, "median_ratio": float(np.median(rat)) if rat else None, "ratios": [float(x) for x in rat]}
        print(name, out["types"][name]["median_ratio"], flush=True)
    out["debris_flow"] = out["types"]["debris_flow"]
    (ROOT / "docs/validation/runout_calibration.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
