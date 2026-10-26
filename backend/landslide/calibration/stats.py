"""Statistics for calibration/validation: ROC AUC with cluster bootstrap, group cross-validation, calibration, threshold fitting."""
from __future__ import annotations
import numpy as np


def auc(y, s):
    y = np.asarray(y).astype(int); s = np.asarray(s, float)
    ok = np.isfinite(s); y, s = y[ok], s[ok]
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    from scipy.stats import rankdata
    r = rankdata(s)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_ci(y, s, n_boot=500, group=None, seed=0, alpha=0.05):
    """AUC with a percentile bootstrap CI. `group` resamples whole clusters (an event with its controls) so the interval is not too narrow."""
    y = np.asarray(y); s = np.asarray(s, float)
    a = auc(y, s)
    rng = np.random.default_rng(seed)
    if group is None:
        group = np.arange(len(y))
    group = np.asarray(group)
    ug = np.unique(group)
    idx = {g: np.where(group == g)[0] for g in ug}
    bs = []
    for _ in range(n_boot):
        pick = rng.choice(ug, len(ug), replace=True)
        ii = np.concatenate([idx[g] for g in pick])
        v = auc(y[ii], s[ii])
        if np.isfinite(v):
            bs.append(v)
    lo, hi = (np.percentile(bs, [100 * alpha / 2, 100 * (1 - alpha / 2)]) if bs else (np.nan, np.nan))
    return a, float(lo), float(hi)


def cv_logistic(Z, y, groups, C=1.0):
    """Leave-one-group-out predicted probabilities (standardised inputs, L2 logistic regression, balanced class weights)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    Z = np.asarray(Z, float); y = np.asarray(y).astype(int); groups = np.asarray(groups)
    p = np.full(len(y), np.nan)
    for g in np.unique(groups[~np.isnan(groups.astype(float))] if groups.dtype.kind == "f" else groups):
        te = groups == g; tr = ~te
        if y[tr].sum() < 3:
            continue
        sc = StandardScaler().fit(Z[tr])
        m = LogisticRegression(C=C, class_weight="balanced", max_iter=1000).fit(sc.transform(Z[tr]), y[tr])
        p[te] = m.predict_proba(sc.transform(Z[te]))[:, 1]
    return p


def isotonic_cv(p, y, groups):
    """Out-of-fold isotonic calibration of out-of-fold scores (leave-one-group-out)."""
    from sklearn.isotonic import IsotonicRegression
    p = np.asarray(p, float); y = np.asarray(y).astype(int); groups = np.asarray(groups)
    out = np.full(len(y), np.nan)
    for g in np.unique(groups):
        te = groups == g; tr = ~te & np.isfinite(p)
        if tr.sum() < 10:
            continue
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p[tr], y[tr])
        out[te] = iso.predict(p[te])
    return out


def brier(y, p):
    ok = np.isfinite(p)
    return float(np.mean((np.asarray(p)[ok] - np.asarray(y)[ok]) ** 2))


def reliability(y, p, bins=8):
    ok = np.isfinite(p); y = np.asarray(y)[ok]; p = np.asarray(p)[ok]
    q = np.quantile(p, np.linspace(0, 1, bins + 1)); q[-1] += 1e-9
    out = []
    for i in range(bins):
        m = (p >= q[i]) & (p < q[i + 1])
        if m.sum():
            out.append({"p_mean": float(p[m].mean()), "freq": float(y[m].mean()), "n": int(m.sum())})
    return out


def tss(y, pred):
    y = np.asarray(y).astype(bool); pred = np.asarray(pred).astype(bool)
    return float(pred[y].mean() - pred[~y].mean())


def fit_id_threshold(X, feats_dur=(1, 3, 6, 12, 24, 48, 72), year_col="group_year"):
    """Fit I = a D^b (mm/h, h): event if ANY duration reaches the curve. Maximise TSS on training years; evaluate on the held-out year
    (leave-one-year-out), then refit on everything. Returns the full-data curve and its out-of-sample TSS."""
    import numpy as np
    Iall = np.stack([X[f"I{d}"].values for d in feats_dur], 1); Dv = np.array(feats_dur, float); y = X.y.values.astype(bool)
    bgrid = np.linspace(-1.0, -0.05, 39)

    def best(idx):
        top = (-9, None)
        for b in bgrid:
            curve = Dv ** b
            ratio = (Iall[idx] / curve).max(1)                               # exceedance ratio against a=1
            order = np.sort(np.unique(ratio))
            for a in np.quantile(ratio, np.linspace(0.02, 0.98, 97)):
                pred = ratio >= a
                t = pred[y[idx]].mean() - pred[~y[idx]].mean()
                if t > top[0]:
                    top = (t, (float(a), float(b)))
        return top
    years = X[year_col].values
    preds = np.zeros(len(X), bool)
    for yv in np.unique(years):
        te = years == yv; tr = ~te
        t, (a, b) = best(np.where(tr)[0])
        preds[te] = ((Iall[te] / (Dv ** b)).max(1)) >= a
    oos = float(preds[y].mean() - preds[~y].mean())
    t, (a, b) = best(np.arange(len(X)))
    return {"a_mm_h": a, "b": b, "tss_in_sample": float(t), "tss_leave_one_year_out": oos,
            "pod_loyo": float(preds[y].mean()), "false_alarm_rate_loyo": float(preds[~y].mean()), "form": "I = a * D^b (mm/h, D in h), exceeded at ANY duration 1-72 h"}
