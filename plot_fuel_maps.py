"""
Fuel maps: what is on the ground, and what fuel changed.

Two figures neither region had. The risk maps show the RESULT of combining
fire weather with fuel; these show the fuel input itself and the effect it had,
which is what makes the two regions' opposite behaviour legible.

FIGURE 1 -- composition
    Six panels of raw Scott & Burgan family fractions -- every family that
    carries weight in fuel_index (SH, GS, GR, TU, TL), plus non-burnable.
    Continuous 0-1, not classed, so the terciles are not baked in. Reading the two regions side by side is
    the point: TVA is a timber-litter region with grass mixed through it and
    almost no shrub; SoCal is a shrub region with a hard desert/urban edge.

FIGURE 2 -- what fuel changed
    Every cell coloured by how its class moved when fuel was applied: demoted,
    unchanged, promoted, or forced to `none` by the non-burnable gate. This is
    the map behind the headline numbers -- in TVA promotions and demotions are
    geographically separated (west demoted, east promoted) so risk moves across
    the region; in SoCal promotion clusters on the coastal chaparral the mild
    marine fire weather had zeroed out, and demotion sits in the interior
    desert.

    NOTE the `demoted` count here is SMALLER than the one combine_fwi_fuel_risk
    prints, and both are correct -- they answer different questions. This map
    separates cells demoted by low fuel from cells the non-burnable gate forced
    to `none`; the combine run counts a gated cell as demoted if its class fell.
    For SoCal: 3,418 demoted total = 2,069 by low fuel + 1,349 by the gate, and
    the remaining 1,445 gated cells were already `none` on fire weather alone.

Run in the `rev` conda env (~15 s per region, no batch job needed):
    conda activate rev
    REGION=tva   python plot_fuel_maps.py
    REGION=socal python plot_fuel_maps.py

Outputs (to outputs/risk_future_with_fuel/):
  * fuel_composition_<region>.png
  * fuel_change_<region>.png
"""

import os

import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap

from regional_absolute_risk_maps import (grid_step, REGIONS, CLASS_ORDER,
                                         OCEAN_COLOR, LAND_COLOR, STATES_PATH)

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_with_fuel")
REGION = os.environ.get("REGION", "tva")

# Panels for figure 1: EVERY family that carries weight in fuel_index, plus
# non-burnable. Showing a subset would hide inputs that the index actually
# uses -- GS is only 0.9% of TVA but 19.1% of SoCal, and TU is the reverse, so
# any subset chosen to suit one region misrepresents the other. SB is the sole
# omission: it exceeds 1% in 85 TVA and 2 SoCal cells and is excluded from
# fuel_index for that reason.
COMP_PANELS = [
    ("frac_SH", "shrub / chaparral (SH)", "Greens"),
    ("frac_GS", "grass-shrub (GS)", "YlGn"),
    ("frac_GR", "grass (GR)", "YlOrBr"),
    ("frac_TU", "timber-understory (TU)", "PuBuGn"),
    ("frac_TL", "timber litter (TL)", "BuGn"),
    ("frac_nonburnable", "non-burnable (urban/water/ag/barren)", "Greys"),
]

CHANGE_ORDER = ["gated to none", "demoted", "unchanged", "promoted"]
CHANGE_COLORS = ["#4a6f8a", "#7fa8c9", "#e8e4dc", "#c0392b"]


def rasterize_f(lon, lat, values, grid, step):
    """Float version of the shared int16 rasterize().

    The shared helper masks on `< 0`, which is correct for class codes but
    would silently drop legitimate zero fractions here. This masks on NaN
    instead, so a cell that is genuinely 0% shrub still draws."""
    col = np.rint((lon - grid["lon0"]) / step).astype(int)
    row = np.rint((lat - grid["lat0"]) / step).astype(int)
    img = np.full((grid["ny"], grid["nx"]), np.nan, dtype="float64")
    img[row, col] = values
    extent = [grid["lon0"] - step / 2,
              grid["lon0"] + (grid["nx"] - 0.5) * step,
              grid["lat0"] - step / 2,
              grid["lat0"] + (grid["ny"] - 0.5) * step]
    return np.ma.masked_invalid(img), extent


def load(region=None):
    """Combined classes joined to fuel composition for one region.

    `region` is an explicit argument, not just the module-level REGION, because
    importers set REGION in their own environment AFTER this module is imported
    -- reading the module global then silently loads the wrong region."""
    region = region or REGION
    comb = gpd.read_file(
        os.path.join(PRODUCT_DIR,
                     f"abs_risk_future_fuel_{region}_risk_classes.gpkg"),
        layer="risk_classes")
    fuel = gpd.read_file(
        os.path.join(PRODUCT_DIR, f"{region}_fuel_composition.gpkg"),
        layer="fuel_composition")
    d = comb.merge(fuel.drop(columns="geometry"), on=["region", "lon", "lat"],
                   how="inner", validate="one_to_one")
    if len(d) != len(comb):
        raise SystemExit(f"join lost cells: {len(comb)} -> {len(d)}")
    return d


def basemap(ax, states, x0, x1, y0, y1):
    ax.set_facecolor(OCEAN_COLOR)
    states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])


def figures(d):
    cfg = REGIONS[REGION]
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]
    step = grid_step(d.lon.to_numpy(), d.lat.to_numpy())
    lon, lat = d.lon.to_numpy(), d.lat.to_numpy()
    lon0, lat0 = float(lon.min()), float(lat.min())
    grid = {"lon0": lon0, "lat0": lat0,
            "nx": int(np.rint((lon.max() - lon0) / step)) + 1,
            "ny": int(np.rint((lat.max() - lat0) / step)) + 1}
    states = gpd.read_file(STATES_PATH).to_crs(4326)
    aspect = (y1 - y0) / (x1 - x0)

    # ---- figure 1: composition -----------------------------------------
    pw = 6.0
    nrow, ncol = 3, 2
    fig, axes = plt.subplots(nrow, ncol,
                             figsize=(pw * ncol, pw * aspect * nrow + 1.8),
                             constrained_layout=True)
    for ax, (col, title, cmap) in zip(axes.ravel(), COMP_PANELS):
        basemap(ax, states, x0, x1, y0, y1)
        img, ext = rasterize_f(lon, lat, d[col].to_numpy(), grid, step)
        im = ax.imshow(img, extent=ext, origin="lower", cmap=cmap,
                       interpolation="nearest", vmin=0, vmax=1, zorder=2)
        states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)
        ax.set_title(f"{title}\nregion mean {100*d[col].mean():.1f}%",
                     fontsize=10.5)
        fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01,
                     label="fraction of cell")
    fig.suptitle(f"{cfg['label']}: LANDFIRE fuel composition\n"
                 f"fraction of each ~2.8 km cell in each Scott & Burgan family",
                 fontsize=13)
    out = os.path.join(PRODUCT_DIR, f"fuel_composition_{REGION}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight"); plt.close(fig)
    print(f"  saved -> {out}")

    # ---- figure 2: what fuel changed ------------------------------------
    lv = {c: i for i, c in enumerate(CLASS_ORDER)}
    before = np.array([lv[c] for c in d.risk_class])
    after = np.array([lv[c] for c in d.combined_class])
    code = np.where(after > before, 3, np.where(after < before, 1, 2))
    code[d.nonburnable_gated.to_numpy() == 1] = 0

    fig, ax = plt.subplots(figsize=(9.0, 9.0 * aspect + 1.8),
                           constrained_layout=True)
    basemap(ax, states, x0, x1, y0, y1)
    img, ext = rasterize_f(lon, lat, code.astype("float64"), grid, step)
    ax.imshow(img, extent=ext, origin="lower", interpolation="nearest",
              cmap=ListedColormap(CHANGE_COLORS), vmin=0,
              vmax=len(CHANGE_COLORS) - 1, zorder=2)
    states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)
    counts = [int((code == i).sum()) for i in range(len(CHANGE_ORDER))]
    ax.legend(handles=[Line2D([0], [0], marker="s", linestyle="None", color=c,
                              markersize=11, label=f"{l}  ({n:,})")
                       for l, c, n in zip(CHANGE_ORDER, CHANGE_COLORS, counts)],
              loc="lower left", fontsize=9.5, framealpha=0.95)
    ax.set_title(f"{cfg['label']}: what adding fuel changed\n"
                 f"{counts[3]:,} promoted, {counts[1]:,} demoted, "
                 f"{counts[2]:,} unchanged, {counts[0]:,} gated non-burnable",
                 fontsize=12.5)
    out = os.path.join(PRODUCT_DIR, f"fuel_change_{REGION}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight"); plt.close(fig)
    print(f"  saved -> {out}")


if __name__ == "__main__":
    figures(load())
