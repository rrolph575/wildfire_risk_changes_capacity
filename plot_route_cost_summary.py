"""
Summary plot of tva_route_endpoint_costs.csv -- did route costs go up, and how
much, once the wildfire-risk penalty is applied?

Three panels:
    (a) before vs after, one point per route, against the 1:1 line. Every point
        must sit on or above the line -- the penalty is multiplicative with all
        multipliers >= 1.0, so no route can get cheaper. This is the check.
    (b) distribution of the per-route % increase, with the median and the
        system-wide total marked.
    (c) the aggregate before/after totals.

Costs are on the routing pipeline's own basis (see route_risk_cost_analysis.py
for why the raw cell sums are not the right thing to quote).

Run in the `rev` conda env:
    conda activate rev
    python plot_route_cost_summary.py

Outputs (to OUT_DIR):
  * tva_route_cost_summary.png
"""

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
RISK_SOURCE = os.environ.get("RISK_SOURCE", "future_with_fuel")
PRODUCT_DIR = os.path.join(OUT_DIR, "outputs", f"cost_penalty_{RISK_SOURCE}")
CSV = os.path.join(PRODUCT_DIR, "tva_route_endpoint_costs.csv")

BEFORE_C = "#b8b8b8"
AFTER_C = "#99000d"
ACCENT = "#00a0a0"


def main():
    d = pd.read_csv(CSV)
    up = int((d.cost_after_penalty > d.cost_before_penalty * 1.000001).sum())
    same = int(np.isclose(d.cost_after_penalty, d.cost_before_penalty).sum())
    down = int((d.cost_after_penalty < d.cost_before_penalty * 0.999999).sum())
    tot_b, tot_a = d.cost_before_penalty.sum(), d.cost_after_penalty.sum()
    overall = 100 * (tot_a / tot_b - 1)
    print(f"{len(d):,} routes: {up:,} increased, {same:,} unchanged, "
          f"{down:,} decreased")
    print(f"total {tot_b:.4g} -> {tot_a:.4g}  (+{overall:.2f}%)")

    fig, (ax1, ax2, ax3) = plt.subplots(
        1, 3, figsize=(17.5, 5.8), constrained_layout=True,
        gridspec_kw={"width_ratios": [1.15, 1.15, 0.72]})

    # ---- (a) before vs after, against 1:1 -------------------------------
    lim = [d.cost_before_penalty.min() * 0.8, d.cost_before_penalty.max() * 1.3]
    ax1.plot(lim, lim, color="0.35", lw=1.4, ls="--", zorder=1,
             label="1:1 — no change")
    s = ax1.scatter(d.cost_before_penalty, d.cost_after_penalty, s=14,
                    c=d.pct_increase, cmap="Reds", vmin=0, vmax=50,
                    linewidths=0, alpha=0.85, zorder=2)
    fig.colorbar(s, ax=ax1, shrink=0.85, label="increase (%)")
    ax1.set_xscale("log"); ax1.set_yscale("log")
    ax1.set_xlim(lim); ax1.set_ylim(lim)
    ax1.set_xlabel("cost before penalty"); ax1.set_ylabel("cost after penalty")
    ax1.set_title(f"(a) every route sits on or above 1:1\n"
                  f"{up:,} increased · {same:,} unchanged · {down:,} decreased",
                  fontsize=11)
    ax1.legend(loc="upper left", fontsize=9.5)
    ax1.set_aspect("equal")

    # ---- (b) distribution of the increase --------------------------------
    ax2.hist(d.pct_increase, bins=40, color=AFTER_C, edgecolor="white",
             linewidth=0.6)
    med = d.pct_increase.median()
    ax2.axvline(med, color="#111111", lw=2, label=f"median route  {med:.2f}%")
    ax2.axvline(overall, color=ACCENT, lw=2, ls="--",
                label=f"system total  {overall:.2f}%")
    ax2.set_xlabel("cost increase for that route (%)")
    ax2.set_ylabel("number of routes")
    ax2.set_title("(b) how much each route goes up\n"
                  f"{int((d.pct_increase < 0.005).sum()):,} routes unaffected; "
                  f"max {d.pct_increase.max():.0f}% (the ×1.5 ceiling)",
                  fontsize=11)
    ax2.legend(fontsize=9.5)
    ax2.spines[["top", "right"]].set_visible(False)

    # ---- (c) the totals ---------------------------------------------------
    sc = 1e12
    bars = ax3.bar(["before", "after"], [tot_b / sc, tot_a / sc],
                   color=[BEFORE_C, AFTER_C], width=0.62)
    for b, v in zip(bars, [tot_b / sc, tot_a / sc]):
        ax3.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f}", ha="center",
                 va="bottom", fontsize=11)
    ax3.annotate(f"+{overall:.2f}%\n(+{(tot_a-tot_b)/sc:.3f})",
                 xy=(1, tot_a / sc), xytext=(0.5, tot_a / sc * 1.06),
                 ha="center", fontsize=12, color=AFTER_C, weight="bold")
    ax3.set_ylim(0, tot_a / sc * 1.22)
    ax3.set_ylabel("total cost of all routes  (×10¹²)")
    ax3.set_title("(c) all 1,509 routes combined", fontsize=11)
    ax3.spines[["top", "right"]].set_visible(False)

    fig.suptitle("TVA transmission routes: cost before and after the "
                 "wildfire-risk penalty\n"
                 "same paths re-costed on the penalised surface — an upper "
                 "bound, since a re-run router would detour", fontsize=13)
    out = os.path.join(PRODUCT_DIR, "tva_route_cost_summary.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


if __name__ == "__main__":
    main()
