"""Satellite change SIGNALS (§4.6): candidate movement evidence only. Cloud/snow QA is the caller's job."""
import numpy as np


def ndvi(nir, red):
    with np.errstate(divide="ignore", invalid="ignore"):
        return (nir - red) / (nir + red)


def nbr(nir, swir2):
    with np.errstate(divide="ignore", invalid="ignore"):
        return (nir - swir2) / (nir + swir2)


def candidate_scars(ndvi_pre, ndvi_post, valid_mask, drop_threshold=0.25, min_cells=5):
    """Flag NDVI drops as CANDIDATES. Returns mask + labelled-component count; false alarms are expected."""
    from scipy import ndimage as ndi
    d = (ndvi_pre - ndvi_post) >= drop_threshold
    d &= valid_mask & np.isfinite(ndvi_pre) & np.isfinite(ndvi_post)
    lab, n = ndi.label(d)
    sizes = ndi.sum(d, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_cells])
    return {"candidate_mask": keep, "status": "candidate_not_confirmed"}


def backscatter_change_db(post_db, pre_db):
    return post_db - pre_db
