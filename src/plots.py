"""Figures: forest plot, funnel plot, Kadir Has trend."""
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from meta import logit_effects, random_effects, wilson_ci, expit

INK, MUTED, GRID, AXIS = "#3a3a38", "#8a8a85", "#ecebe6", "#d0cfc9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated categorical order


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=INK, labelsize=8)
    ax.set_axisbelow(True)


def forest(df, group_col, path, title, pct_col="pct", n_col="n"):
    groups = list(dict.fromkeys(df[group_col]))
    rows = []  # (label, est, lo, hi, kind, color)
    for gi, g in enumerate(groups):
        sub = df[df[group_col] == g].sort_values("field_year")
        c = SERIES[gi % len(SERIES)]
        rows.append((g.capitalize(), None, None, None, "header", c))
        lo, hi = wilson_ci(sub[pct_col], sub[n_col])
        for (_, r), l, h in zip(sub.iterrows(), lo, hi):
            lab = f"   {r['institution']} {int(r['field_year'])}  (n={int(r[n_col]):,})".replace(",", ".")
            if r.get("n_assumed", 0) == 1:
                lab += " *"
            rows.append((lab, r[pct_col], l, h, "study", c))
        y, v = logit_effects(sub[pct_col], sub[n_col])
        res = random_effects(y, v)
        if len(sub) > 1:
            rows.append((f"   Alt grup havuzu (I²={res['I2']:.0f}%)", res["pooled_pct"],
                         res["ci_low"], res["ci_high"], "pooled", c))
    y, v = logit_effects(df[pct_col], df[n_col])
    tot = random_effects(y, v)
    rows.append(("Genel havuz (rastgele etkiler)", tot["pooled_pct"], tot["ci_low"], tot["ci_high"], "total", INK))

    fig, ax = plt.subplots(figsize=(9.5, 0.27 * len(rows) + 1.2), dpi=150)
    for i, (lab, est, lo, hi, kind, c) in enumerate(rows):
        yy = len(rows) - i
        ax.text(-0.02, yy, lab, transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=8, color=INK, weight="bold" if kind in ("header", "total") else "normal")
        if est is None:
            continue
        if kind in ("pooled", "total"):
            ax.fill([lo, est, hi, est], [yy, yy + 0.32, yy, yy - 0.32], color=c, lw=0)
        else:
            ax.plot([lo, hi], [yy, yy], color=c, lw=1.6)
            ax.plot(est, yy, "o", color=c, ms=5)
        ax.text(1.01, yy, f"{est:.1f} [{lo:.1f}–{hi:.1f}]", transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=7.5, color=INK)
    ax.axvline(tot["pooled_pct"], color=MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.set_yticks([])
    ax.set_xlabel("% (95% GA)", color=INK, fontsize=8)
    ax.set_xlim(0, max(r[3] for r in rows if r[3] is not None) + 2)
    ax.grid(axis="x", color=GRID, lw=0.8)
    _style(ax)
    ax.spines["left"].set_visible(False)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    fig.text(0.01, 0.01, "* n raporda yok; 2.500 varsayıldı (duyarlılık analizinde çıkarılıyor)", fontsize=7, color=MUTED)
    fig.subplots_adjust(left=0.42, right=0.84, top=0.93, bottom=0.08)
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return tot


def funnel(df, path, pct_col="pct", n_col="n"):
    y, v = logit_effects(df[pct_col], df[n_col])
    res = random_effects(y, v)
    se = np.sqrt(v)
    fig, ax = plt.subplots(figsize=(5.5, 4.2), dpi=150)
    s = np.linspace(0, se.max() * 1.1, 50)
    mu = res["mu_logit"]
    ax.plot(mu - Z_ * s, s, color=MUTED, lw=0.8)
    ax.plot(mu + Z_ * s, s, color=MUTED, lw=0.8)
    ax.axvline(mu, color=MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.scatter(y, se, s=26, color=SERIES[0], edgecolor="white", lw=1, zorder=3)
    ax.invert_yaxis()
    ax.set_xlabel("logit(oran)", color=INK, fontsize=8)
    ax.set_ylabel("Standart hata", color=INK, fontsize=8)
    ax.set_title("Huni grafiği (funnel plot)", fontsize=10, color=INK, loc="left")
    ax.grid(color=GRID, lw=0.8)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


Z_ = 1.959964


def khas_trend(kh, path):
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    for col, lab, c in [("pct", "Tüm katılımcılar içinde", SERIES[1]),
                        ("pct_declarers", "Etnik kimlik beyan edenler içinde", SERIES[0])]:
        n = kh["n"] if col == "pct" else kh["n"] * (kh["turk_pct"] + kh["pct"]) / 100
        lo, hi = wilson_ci(kh[col], n)
        ax.fill_between(kh["field_year"], lo, hi, color=c, alpha=0.15, lw=0)
        ax.plot(kh["field_year"], kh[col], color=c, lw=2, marker="o", ms=4, label=lab)
    ax.axvline(2015.5, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax.text(2015.6, 19.5, "2016: cevapsızlık\n%20-38'den %1-3'e iniyor", fontsize=7.5, color=INK, va="top")
    ax.set_ylim(0, 20)
    ax.set_xticks(kh["field_year"])
    ax.set_ylabel("Kürt + Zaza, %", color=INK, fontsize=8)
    ax.set_title("Kadir Has serisi: Kürt + Zaza kimlik beyanı, 2011–2022 (%95 GA)", fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.grid(axis="y", color=GRID, lw=0.8)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
