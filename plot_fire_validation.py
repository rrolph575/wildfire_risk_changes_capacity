"""
Sanity-check the fuel index against a real fire perimeter.

Overlays a burned-area perimeter on the fuel index and the combined risk class,
to ask a simple question: did the ground that actually burned score as high
fuel? This is a QUALITATIVE check, not a validation -- see the caveats below.

WHY THIS IS A WEAK TEST, AND WHAT IT CAN STILL TELL YOU
    A ~14,000-acre fire covers only ~13 of the ~2.8 km risk cells out of
    19,407 in SoCal, so nothing here is statistically meaningful. Fires also
    need ignition and weather, not just fuel, so a single burn cannot confirm
    a fuel index and its absence cannot refute one. What it CAN do is catch a
    gross error -- if severe chaparral scored as low fuel, that would show.

    The fire-weather axis cannot be checked this way AT ALL. Sup3rCC is a
    GCM-driven downscaling, not a reanalysis: no day in it corresponds to a
    real date, so no specific fire's weather is in the record even in
    principle. Only the climatological distribution is meaningful.

    LANDFIRE 2024 predates a January 2025 fire, so the fuel it reports is the
    PRE-fire fuel that actually burned. That timing is right, and would not be
    for a fire before the LANDFIRE vintage.

Run in the `rev` conda env (~10 s, no batch job needed):
    conda activate rev
    python plot_fire_validation.py

Outputs (to outputs/risk_future_with_fuel/):
  * fire_validation_<fire>.png -- regional context, fuel index, combined class
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

from regional_absolute_risk_maps import (grid_step, REGIONS, CLASS_ORDER,
                                         CLASS_COLORS, OCEAN_COLOR,
                                         LAND_COLOR, STATES_PATH)
from plot_fuel_maps import rasterize_f, load as load_region

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_with_fuel")
PERIM = os.path.join(PROJ, "data", "fire_perimeters",
                     "eaton_fire_2025_perimeter.geojson")
FIRE = os.environ.get("FIRE", "eaton")
REGION = os.environ.get("REGION", "socal")
PAD = 0.16          # degrees of context around the perimeter in the zoom panels


def main():
    perim = gpd.read_file(PERIM).to_crs(4326)
    fire = perim.geometry.unary_union
    d = load_region(REGION)

    x0, y0, x1, y1 = perim.total_bounds
    zx = (x0 - PAD, x1 + PAD)
    zy = (y0 - PAD, y1 + PAD)

    step = grid_step(d.lon.to_numpy(), d.lat.to_numpy())
    lon, lat = d.lon.to_numpy(), d.lat.to_numpy()
    lon0, lat0 = float(lon.min()), float(lat.min())
    grid = {"lon0": lon0, "lat0": lat0,
            "nx": int(np.rint((lon.max() - lon0) / step)) + 1,
            "ny": int(np.rint((lat.max() - lat0) / step)) + 1}
    states = gpd.read_file(STATES_PATH).to_crs(4326)

    # cells overlapping the burn, for the caption
    sub = d[(d.lon > x0 - 0.05) & (d.lon < x1 + 0.05) &
            (d.lat > y0 - 0.05) & (d.lat < y1 + 0.05)].copy()
    sub["ovl"] = [c.intersection(fire).area / c.area for c in sub.geometry]
    hit = sub[sub.ovl > 0.10]

    fig, axes = plt.subplots(1, 3, figsize=(17.5, 6.4),
                             constrained_layout=True)
    cfg = REGIONS[REGION]

    # (a) regional context
    ax = axes[0]
    ax.set_facecolor(OCEAN_COLOR)
    states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
    img, ext = rasterize_f(lon, lat, d.fuel_index.to_numpy(), grid, step)
    ax.imshow(img, extent=ext, origin="lower", cmap="YlGn",
              interpolation="nearest", vmin=0, vmax=1, zorder=2)
    states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)
    ax.add_patch(plt.Rectangle((zx[0], zy[0]), zx[1]-zx[0], zy[1]-zy[0],
                               fill=False, ec="red", lw=1.8, zorder=6))
    ax.set_xlim(*cfg["xlim"]); ax.set_ylim(*cfg["ylim"])
    ax.set_title("(a) where the fire sits in the region\nfuel_index, "
                 "red box = zoom extent", fontsize=10.5)

    # (b) fuel index, zoomed
    ax = axes[1]
    ax.set_facecolor(OCEAN_COLOR)
    states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
    im = ax.imshow(img, extent=ext, origin="lower", cmap="YlGn",
                   interpolation="nearest", vmin=0, vmax=1, zorder=2)
    perim.boundary.plot(ax=ax, color="red", linewidth=2.2, zorder=6)
    ax.set_xlim(*zx); ax.set_ylim(*zy)
    ax.set_title("(b) fuel_index vs the burn perimeter\n"
                 f"median inside {hit.fuel_index.median():.2f} "
                 f"vs {d.fuel_index.median():.2f} region-wide", fontsize=10.5)
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.01, label="fuel_index")

    # (c) combined class, zoomed
    ax = axes[2]
    ax.set_facecolor(OCEAN_COLOR)
    states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
    code = np.array([CLASS_ORDER.index(c) for c in d.combined_class],
                    dtype="float64")
    img2, ext2 = rasterize_f(lon, lat, code, grid, step)
    ax.imshow(img2, extent=ext2, origin="lower", interpolation="nearest",
              cmap=ListedColormap([CLASS_COLORS[c] for c in CLASS_ORDER]),
              vmin=0, vmax=len(CLASS_ORDER)-1, zorder=2)
    perim.boundary.plot(ax=ax, color="red", linewidth=2.2, zorder=6)
    ax.set_xlim(*zx); ax.set_ylim(*zy)
    ax.legend(handles=[Line2D([0], [0], marker="s", linestyle="None", color=c,
                              markersize=10, label=l)
                       for l, c in zip(CLASS_ORDER,
                                       [CLASS_COLORS[c] for c in CLASS_ORDER])]
                      + [Line2D([0], [0], color="red", lw=2.2,
                                label="burn perimeter")],
              loc="lower left", fontsize=8.5, framealpha=0.95)
    ax.set_title("(c) combined class (fire weather + fuel)\n"
                 "fire weather scores this ground `none` throughout",
                 fontsize=10.5)

    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")

    fig.suptitle(
        f"{FIRE.title()} Fire (Jan 2025, {int(perim.poly_GISAcres.sum()):,} "
        f"acres) against the fuel index\n"
        f"{len(hit)} risk cells overlap the burn — a qualitative check, "
        f"not a statistical validation", fontsize=13)
    out = os.path.join(PRODUCT_DIR, f"fire_validation_{FIRE}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")
    print(f"  cells overlapping burn: {len(hit)}")
    print(f"  fuel_class: {dict(hit.fuel_class.value_counts())}")
    print(f"  risk_class (fire weather): {dict(hit.risk_class.value_counts())}")
    print(f"  combined_class: {dict(hit.combined_class.value_counts())}")


if __name__ == "__main__":
    main()
