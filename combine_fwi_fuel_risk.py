"""
Combine fire weather (FWI) and fuel (LANDFIRE) into one wildfire risk class.

Takes the two independent measurements each grid cell already has and resolves
them to a single class on the SAME none/low/medium/high scale, so the cost
multipliers and every downstream script keep working unchanged.

WHY A LOOKUP TABLE, NOT A FORMULA
    FWI is an index running 0-300+; fuel is a fraction 0-1. There is no
    arithmetic that combines them honestly -- multiplying would be dominated by
    FWI's scale and would mean nothing. So each is first converted to an
    ordinal class against ITS OWN region's spread, and the pair of classes is
    resolved through a 12-entry table.

THE TWO AXES
    fire weather   p98 FWI vs the region's 50th/75th/90th-percentile cell
                   -> none / low / medium / high        (already computed)
    fuel           `woody` vs the region's 33rd/67th-percentile cell
                   -> low / medium / high

    woody = frac_TL + frac_TU + frac_SH + frac_GS, i.e. the fraction of the
    cell in timber and shrub families. Grass is excluded: it burns fast but
    carries little load, and frac_GR is flat across TVA (rank correlation with
    longitude -0.04), so it would add noise rather than signal. Non-burnable
    needs no special handling in this axis -- woody is a fraction of the WHOLE
    cell, so agriculture/water/urban dilute it automatically.

    Fuel uses TERCILES rather than mirroring the FWI 50/75/90. Fuel is a
    MODIFIER, not the primary axis: with FWI-style cutoffs it demotes 17,557
    cells and promotes only 4,114, collapsing `high` from 26% to 9%. Terciles
    keep it near-symmetric (12,613 promoted / 11,938 demoted).

THE MATRIX -- fuel shifts the fire-weather class by one step, clipped

    FWI \\ fuel     low       medium    high
    none           none      none      low
    low            none      low       medium
    medium         low       medium    high
    high           medium    high      high

    Read the two corners that matter: severe fire weather over bare ground is
    marked DOWN; moderate weather over heavy timber is marked UP. That is the
    whole reason for adding fuel -- the fire-weather-only map concentrates risk
    in agricultural western TVA and understates the forested eastern plateau
    (fuel rank-correlates +0.40 with longitude, fire weather -0.52).

NON-BURNABLE GATE
    Applied last and overriding: frac_burnable < NONBURN_GATE forces `none`.
    Catches reservoirs and dense urban, and is what stops the cost penalty
    charging a wildfire multiplier on open water.

Run in the `rev` conda env (fast, ~20 s -- no batch job needed):
    conda activate rev
    python combine_fwi_fuel_risk.py

Outputs (to outputs/risk_future_with_fuel/):
  * abs_risk_future_fuel_<region>_risk_classes.gpkg -- layer "risk_classes",
        one polygon per cell with both input classes, the fuel index, and the
        combined class, so any cell's result can be traced back to its inputs.
  * fuel_combination_<region>.png -- three panels: fire weather only, fuel,
        and the combined result, for judging whether the combination behaves.
"""

import os

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap

from regional_absolute_risk_maps import (rasterize, grid_step, REGIONS,
                                         CLASS_ORDER, CLASS_COLORS,
                                         OCEAN_COLOR, LAND_COLOR, STATES_PATH)

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_with_fuel")
FWI_GPKG = os.path.join(PROJ, "outputs", "risk_future",
                        "abs_risk_future_p98_risk_classes.gpkg")
FUEL_GPKG = os.path.join(PRODUCT_DIR, "tva_fuel_composition.gpkg")
REGION = "tva"

FUEL_QUANTILES = (0.33, 0.67)      # terciles -> low / medium / high
NONBURN_GATE = 0.10                # frac_burnable below this -> forced none
FUEL_ORDER = ["low", "medium", "high"]
FUEL_SHIFT = {"low": -1, "medium": 0, "high": +1}
FUEL_COLORS = {"low": "#e8e0d0", "medium": "#a8b88a", "high": "#3f6b3f"}


def combine(fwi_class, fuel_class):
    """The 12-entry table, expressed as a clipped +/-1 shift."""
    lv = CLASS_ORDER.index(fwi_class) + FUEL_SHIFT[fuel_class]
    return CLASS_ORDER[int(np.clip(lv, 0, len(CLASS_ORDER) - 1))]


def build():
    fwi = gpd.read_file(FWI_GPKG, layer="risk_classes")
    fwi = fwi[fwi["region"] == REGION]
    fuel = gpd.read_file(FUEL_GPKG, layer="fuel_composition")

    d = fwi.merge(fuel.drop(columns="geometry"), on=["region", "lon", "lat"],
                  how="inner", validate="one_to_one")
    if len(d) != len(fwi):
        raise SystemExit(f"join lost cells: {len(fwi)} fwi -> {len(d)} joined")

    d["woody"] = d.frac_TL + d.frac_TU + d.frac_SH + d.frac_GS
    q1, q2 = d["woody"].quantile(list(FUEL_QUANTILES))
    d["fuel_class"] = np.where(d.woody >= q2, "high",
                        np.where(d.woody >= q1, "medium", "low"))
    d["fuel_cut_low"], d["fuel_cut_high"] = float(q1), float(q2)

    d["combined_class"] = [combine(a, b)
                           for a, b in zip(d.risk_class, d.fuel_class)]
    gated = d["frac_burnable"] < NONBURN_GATE
    d.loc[gated, "combined_class"] = "none"
    d["nonburnable_gated"] = gated.astype(int)
    d["combined_level"] = [CLASS_ORDER.index(c) for c in d.combined_class]

    print(f"{len(d):,} {REGION} cells")
    print(f"fuel cutoffs (woody): low <{q1:.3f} | medium {q1:.3f}-{q2:.3f} "
          f"| high >={q2:.3f}")
    print(f"non-burnable gate: frac_burnable < {NONBURN_GATE} -> "
          f"{int(gated.sum()):,} cells forced to none")
    print("\n%-9s %12s %12s" % ("class", "FWI only", "FWI + fuel"))
    for c in CLASS_ORDER:
        print("%-9s %11.1f%% %11.1f%%" % (
            c, 100 * (d.risk_class == c).mean(),
            100 * (d.combined_class == c).mean()))
    lv = {c: i for i, c in enumerate(CLASS_ORDER)}
    up = sum(lv[a] > lv[b] for a, b in zip(d.combined_class, d.risk_class))
    dn = sum(lv[a] < lv[b] for a, b in zip(d.combined_class, d.risk_class))
    print(f"\npromoted {up:,} | demoted {dn:,} | unchanged "
          f"{len(d)-up-dn:,}")
    return d, (q1, q2)


def figure(d, cuts):
    cfg = REGIONS[REGION]
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]
    step = grid_step(d.lon.to_numpy(), d.lat.to_numpy())
    lon0, lat0 = float(d.lon.min()), float(d.lat.min())
    grid = {"lon0": lon0, "lat0": lat0,
            "nx": int(np.rint((d.lon.max() - lon0) / step)) + 1,
            "ny": int(np.rint((d.lat.max() - lat0) / step)) + 1}
    r = {"lon": d.lon.to_numpy(), "lat": d.lat.to_numpy(), "grid": grid}

    states = gpd.read_file(STATES_PATH).to_crs(4326)
    panels = [
        ("(a) fire weather only\np98 FWI vs regional cutoffs",
         [CLASS_ORDER.index(c) for c in d.risk_class],
         [CLASS_COLORS[c] for c in CLASS_ORDER], CLASS_ORDER),
        (f"(b) fuel\nwoody fraction, terciles {cuts[0]:.2f} / {cuts[1]:.2f}",
         [FUEL_ORDER.index(c) for c in d.fuel_class],
         [FUEL_COLORS[c] for c in FUEL_ORDER], FUEL_ORDER),
        ("(c) combined\nfuel shifts the class by one step",
         [CLASS_ORDER.index(c) for c in d.combined_class],
         [CLASS_COLORS[c] for c in CLASS_ORDER], CLASS_ORDER),
    ]
    pw = 6.2
    fig, axes = plt.subplots(1, 3, figsize=(pw * 3, pw * (y1-y0)/(x1-x0) + 2.0),
                             constrained_layout=True)
    for ax, (title, codes, colors, labels) in zip(axes, panels):
        ax.set_facecolor(OCEAN_COLOR)
        states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
        img, ext = rasterize(r, np.asarray(codes, dtype=np.int16), step)
        ax.imshow(img, extent=ext, origin="lower", interpolation="nearest",
                  cmap=ListedColormap(colors), vmin=0, vmax=len(colors)-1,
                  zorder=2)
        states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10.5)
        ax.legend(handles=[Line2D([0], [0], marker="s", linestyle="None",
                                  color=c, markersize=10, label=l)
                           for l, c in zip(labels, colors)],
                  loc="lower left", fontsize=8.5, framealpha=0.95)
    fig.suptitle(f"{cfg['label']}: combining projected fire weather with "
                 f"LANDFIRE fuel\n(b) shifts (a) by one class to give (c)",
                 fontsize=13)
    out = os.path.join(PRODUCT_DIR, f"fuel_combination_{REGION}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


def main():
    os.makedirs(PRODUCT_DIR, exist_ok=True)
    d, cuts = build()
    keep = ["region", "lon", "lat", "future_p98_fwi", "risk_class",
            "woody", "frac_burnable", "fuel_class", "fuel_cut_low",
            "fuel_cut_high", "combined_class", "combined_level",
            "nonburnable_gated", "geometry"]
    out = os.path.join(PRODUCT_DIR,
                       f"abs_risk_future_fuel_{REGION}_risk_classes.gpkg")
    gpd.GeoDataFrame(d[keep], crs=d.crs).to_file(
        out, layer="risk_classes", driver="GPKG")
    print(f"  saved -> {out}")
    figure(d, cuts)


if __name__ == "__main__":
    main()
