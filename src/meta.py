"""Random-effects meta-analysis of proportions (logit scale, DerSimonian-Laird).

Small, dependency-light implementation so every step is visible:
effect sizes, pooling, heterogeneity, subgroups, meta-regression,
leave-one-out sensitivity and Egger's test.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

Z = stats.norm.ppf(0.975)  # 95% confidence, as in the source surveys


def expit(x):
    return 1 / (1 + np.exp(-x))


def logit_effects(pct, n):
    """Logit-transformed proportions and their sampling variances.
    A 0.5 continuity correction keeps small cells finite."""
    pct = np.asarray(pct, float)
    n = np.asarray(n, float)
    x = pct / 100 * n
    y = np.log((x + 0.5) / (n - x + 0.5))
    v = 1 / (x + 0.5) + 1 / (n - x + 0.5)
    return y, v


def wilson_ci(pct, n):
    """Per-study 95% Wilson interval, in percent."""
    p = np.asarray(pct, float) / 100
    n = np.asarray(n, float)
    den = 1 + Z**2 / n
    centre = (p + Z**2 / (2 * n)) / den
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / den
    return (centre - half) * 100, (centre + half) * 100


def random_effects(y, v):
    """DerSimonian-Laird random-effects pooling on the logit scale."""
    y, v = np.asarray(y, float), np.asarray(v, float)
    k = len(y)
    w = 1 / v
    y_fe = np.sum(w * y) / np.sum(w)
    Q = np.sum(w * (y - y_fe) ** 2)
    C = np.sum(w) - np.sum(w**2) / np.sum(w)
    tau2 = max(0.0, (Q - (k - 1)) / C) if k > 1 else 0.0
    ws = 1 / (v + tau2)
    mu = np.sum(ws * y) / np.sum(ws)
    se = np.sqrt(1 / np.sum(ws))
    I2 = max(0.0, (Q - (k - 1)) / Q) * 100 if Q > 0 else 0.0
    p_Q = 1 - stats.chi2.cdf(Q, k - 1) if k > 1 else np.nan
    if k > 2:
        t = stats.t.ppf(0.975, k - 2)
        half = t * np.sqrt(tau2 + se**2)
        pi = (expit(mu - half) * 100, expit(mu + half) * 100)
    else:
        pi = (np.nan, np.nan)
    return {
        "k": k,
        "pooled_pct": expit(mu) * 100,
        "ci_low": expit(mu - Z * se) * 100,
        "ci_high": expit(mu + Z * se) * 100,
        "pi_low": pi[0],
        "pi_high": pi[1],
        "Q": Q,
        "p_Q": p_Q,
        "I2": I2,
        "tau2": tau2,
        "mu_logit": mu,
        "se_logit": se,
        "weights_pct": ws / ws.sum() * 100,
    }


def pool(df, pct_col="pct", n_col="n", label="All studies"):
    y, v = logit_effects(df[pct_col], df[n_col])
    res = random_effects(y, v)
    res = {"analysis": label, **{k: v for k, v in res.items() if k != "weights_pct"}}
    return res


def subgroup_test(df, group_col, pct_col="pct", n_col="n"):
    """Pool within each subgroup and test for between-subgroup differences
    (Q_between on random-effects estimates)."""
    rows, mus, ses = [], [], []
    for g, sub in df.groupby(group_col, sort=False):
        r = pool(sub, pct_col, n_col, label=f"{group_col} = {g}")
        rows.append(r)
        mus.append(r["mu_logit"])
        ses.append(r["se_logit"])
    mus, ses = np.array(mus), np.array(ses)
    w = 1 / ses**2
    mbar = np.sum(w * mus) / np.sum(w)
    Qb = np.sum(w * (mus - mbar) ** 2)
    df_b = len(mus) - 1
    p = 1 - stats.chi2.cdf(Qb, df_b) if df_b > 0 else np.nan
    return pd.DataFrame(rows), {"Q_between": Qb, "df": df_b, "p": p}


def meta_regression(df, covariates, pct_col="pct", n_col="n"):
    """Weighted least squares with random-effects weights (tau2 from the
    intercept-only model). Returns coefficients on the logit scale."""
    y, v = logit_effects(df[pct_col], df[n_col])
    tau2 = random_effects(y, v)["tau2"]
    X = np.column_stack([np.ones(len(df))] + [np.asarray(df[c], float) for c in covariates])
    W = np.diag(1 / (v + tau2))
    cov = np.linalg.inv(X.T @ W @ X)
    b = cov @ X.T @ W @ y
    se = np.sqrt(np.diag(cov))
    zval = b / se
    p = 2 * (1 - stats.norm.cdf(np.abs(zval)))
    return pd.DataFrame(
        {"term": ["intercept"] + list(covariates), "coef_logit": b, "se": se,
         "z": zval, "p": p, "odds_ratio": np.exp(b)}
    )


def leave_one_out(df, id_col="study_id", pct_col="pct", n_col="n"):
    rows = []
    for sid in df[id_col]:
        r = pool(df[df[id_col] != sid], pct_col, n_col, label=f"without {sid}")
        rows.append({"omitted": sid, "pooled_pct": r["pooled_pct"],
                     "ci_low": r["ci_low"], "ci_high": r["ci_high"], "I2": r["I2"]})
    return pd.DataFrame(rows)


def egger_test(df, pct_col="pct", n_col="n"):
    """Egger's regression for small-study effects (standard normal deviate
    on precision). With census-style surveys this is a diagnostic, not a
    test of publication bias."""
    y, v = logit_effects(df[pct_col], df[n_col])
    se = np.sqrt(v)
    snd, prec = y / se, 1 / se
    X = np.column_stack([np.ones(len(y)), prec])
    beta, res, *_ = np.linalg.lstsq(X, snd, rcond=None)
    dof = len(y) - 2
    sigma2 = np.sum((snd - X @ beta) ** 2) / dof
    cov = sigma2 * np.linalg.inv(X.T @ X)
    t = beta[0] / np.sqrt(cov[0, 0])
    p = 2 * (1 - stats.t.cdf(abs(t), dof))
    return {"intercept": beta[0], "se": np.sqrt(cov[0, 0]), "t": t, "df": dof, "p": p}
