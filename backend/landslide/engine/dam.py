"""Landslide-dam screening from a finished run: does the deposit block a drainage line, how big is the dam and the lake it would hold,
and is the dam likely to be stable?  (Formation and stability only: routing a breach flood downstream is flood modelling and is outside
this product; the breach peak is given as a single number.)

Channels: D8 flow accumulation on the pre-event DEM, cells draining at least `min_drainage_km2`.  Drainage area is truncated at the edge of the
analysed area, so Ab is a lower bound.  Dam = connected deposit of at least `min_dam_m` that sits on a channel.
  Hd   maximum deposit thickness on the channel cells of the dam
  Vd   volume of the connected deposit
  DBI  = log10(Ab Hd / Vd)      Ab km2 -> m2, Hd m, Vd m3          Ermini and Casagli (2003): stable < 2.75, unstable > 3.08
  lake level = crest = max post-event bed on the channel cells; lake = cells connected upstream of the dam with pre-event bed below the crest
  Qp   = 0.607 V^0.295 h^1.24   (Froehlich 1995, embankment breach; used here as a screening number for a landslide dam)"""
from __future__ import annotations
import numpy as np
from scipy import ndimage
from ..data.preprocessing import terrain


def classify(dbi):
    return "likely stable" if dbi < 2.75 else ("likely unstable" if dbi > 3.08 else "uncertain")


def froehlich_qp(v_m3, h_m):
    return 0.607 * v_m3 ** 0.295 * h_m ** 1.24


def assess(z_pre, deposit, valid, dx, min_drainage_km2=0.5, min_dam_m=2.0):
    zf = terrain.fill_pits(np.where(np.isfinite(z_pre), z_pre, np.nanmax(z_pre)))
    d8 = terrain.d8_flow(zf, dx, dx)
    acc_km2 = d8["flow_accum_cells"] * dx * dx / 1e6
    channel = valid & (acc_km2 >= min_drainage_km2)
    dep = np.where(valid, deposit, 0.0)
    cand = dep >= min_dam_m
    lab, n = ndimage.label(cand, structure=np.ones((3, 3)))
    dams = []
    z_post = z_pre + dep
    for k in range(1, n + 1):
        m = lab == k
        on_ch = m & channel
        if not on_ch.any():
            continue
        Hd = float(dep[on_ch].max())
        Vd = float(dep[m].sum() * dx * dx)
        Ab = float(acc_km2[on_ch].max())
        dbi = float(np.log10(max(Ab * 1e6 * Hd / max(Vd, 1.0), 1e-12)))
        crest = float(z_post[on_ch].max())
        thalweg = float(z_pre[on_ch].min())
        # lake: flood-fill upstream cells below the crest, 8-connected from the dam, excluding the dam body
        low = (z_pre < crest) & valid & ~m
        seed = ndimage.binary_dilation(m, structure=np.ones((3, 3))) & low
        lake, _ = ndimage.label(low, structure=np.ones((3, 3)))
        ids = np.unique(lake[seed]); ids = ids[ids > 0]
        lake_mask = np.isin(lake, ids)
        # keep only cells that drain through the dam (upstream), approximated by cells with higher accumulation-path ancestry: z_pre >= local thalweg
        lake_mask &= z_pre >= thalweg
        vol = float(np.sum((crest - z_pre)[lake_mask]) * dx * dx)
        area = float(lake_mask.sum() * dx * dx)
        h_breach = max(crest - thalweg, 0.5)
        dams.append({"cells": int(m.sum()), "dam_height_m": Hd, "dam_volume_m3": Vd, "upstream_area_km2": Ab, "dbi": dbi, "stability": classify(dbi),
                     "crest_m": crest, "lake_volume_m3": vol, "lake_area_m2": area, "breach_height_m": h_breach,
                     "breach_peak_m3s": float(froehlich_qp(vol, h_breach)) if vol > 0 else 0.0,
                     "centroid_rc": [float(np.mean(np.where(m)[0])), float(np.mean(np.where(m)[1]))]})
    dams.sort(key=lambda d: -d["dam_height_m"])
    return {"dams": dams, "n_blocking": len(dams), "channel_cells": int(channel.sum()),
            "notes": ["drainage area truncated at the analysed area (Ab is a lower bound)", "Froehlich (1995) is an embankment relation, used as a screening number",
                      "downstream flood routing is not part of this product"]}
