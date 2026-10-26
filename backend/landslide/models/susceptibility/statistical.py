"""M02-M04 inventory-driven susceptibility with spatial-block validation and OOD masking (§4.5, §6.1, §9.2).

Rules enforced: min positives gate, negatives only from observed-coverage cells outside positional-uncertainty buffers,
spatial-block (GroupKFold) CV, imputation/scaling fitted inside folds only, PR-AUC+ROC-AUC+Brier, OOD suppression,
calibration only if enough positives. Output is a RELATIVE score unless `calibrated` is True.
"""
from __future__ import annotations
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from ...gates import check_supervised_inventory

MODELS = {
    "logistic": lambda: make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                      LogisticRegression(max_iter=2000, class_weight="balanced")),
    "random_forest": lambda: make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                                           RandomForestClassifier(500, min_samples_leaf=5, n_jobs=-1,
                                                                  class_weight="balanced_subsample", random_state=0)),
    "gradient_boosting": lambda: make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                                               GradientBoostingClassifier(random_state=0)),
}


def spatial_blocks(x, y, block_size_m):
    """Integer block id per sample from projected coordinates (metres)."""
    bx, by = np.floor(np.asarray(x) / block_size_m), np.floor(np.asarray(y) / block_size_m)
    _, ids = np.unique(np.c_[bx, by], axis=0, return_inverse=True)
    return ids.ravel()


def sample_negatives(candidate_xy, covered_mask, positive_xy, exclusion_m, n, seed=0):
    """Negatives only from observation-covered candidates farther than `exclusion_m` from any positive."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    cand = np.asarray(candidate_xy)[np.asarray(covered_mask, bool)]
    d, _ = cKDTree(np.asarray(positive_xy)).query(cand)
    cand = cand[d > exclusion_m]
    if len(cand) < n:
        raise ValueError(f"only {len(cand)} eligible negative candidates (<{n})")
    return cand[rng.choice(len(cand), n, replace=False)]


def spatial_cv(X, y, groups, model="random_forest", n_splits=5):
    check_supervised_inventory(int(np.sum(y)))
    gkf = GroupKFold(n_splits=min(n_splits, len(np.unique(groups))))
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(X, y, groups):
        if y[tr].sum() == 0 or y[te].sum() == 0:
            continue
        m = MODELS[model]()
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(oof)
    prev = float(np.mean(y[ok]))
    return {"model": model, "pr_auc": float(average_precision_score(y[ok], oof[ok])),
            "roc_auc": float(roc_auc_score(y[ok], oof[ok])), "brier": float(brier_score_loss(y[ok], oof[ok])),
            "class_prevalence": prev, "n_evaluated": int(ok.sum()), "oof": oof,
            "validation_status": "spatially_validated",
            "note": "PR-AUC must be read against prevalence; negatives are sampled, so Brier is not population-calibrated"}


def event_holdout(X, y, event_ids, model, test_events):
    """Train on other events, test on whole held-out events (§6.1 event_holdout)."""
    te = np.isin(event_ids, test_events)
    m = MODELS[model]()
    m.fit(X[~te], y[~te])
    p = m.predict_proba(X[te])[:, 1]
    return {"pr_auc": float(average_precision_score(y[te], p)), "roc_auc": float(roc_auc_score(y[te], p))}


def fit_final(X, y, model="random_forest"):
    check_supervised_inventory(int(np.sum(y)))
    m = MODELS[model]()
    m.fit(X, y)
    lo, hi = np.nanquantile(X, 0.005, axis=0), np.nanquantile(X, 0.995, axis=0)
    return m, {"lo": lo, "hi": hi}


def ood_mask(X, domain):
    """True where ANY feature lies outside the training envelope -> suppress confident output."""
    with np.errstate(invalid="ignore"):
        return np.any((X < domain["lo"]) | (X > domain["hi"]), axis=1)


def predict(model, X, domain):
    p = model.predict_proba(X)[:, 1]
    ood = ood_mask(X, domain)
    return {"score_relative": np.where(ood, np.nan, p), "out_of_domain": ood, "calibrated": False}


def reliability(y, p, bins=10):
    from sklearn.calibration import calibration_curve
    frac, mean = calibration_curve(y, p, n_bins=bins, strategy="quantile")
    return {"mean_predicted": mean, "fraction_positive": frac}
