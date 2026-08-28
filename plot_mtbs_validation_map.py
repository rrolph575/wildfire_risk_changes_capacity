"""
Risk classes vs where fires have actually burned (MTBS).

The map behind summary_of_validation_against_observed_fires.md. Three panels,
each the full region with MTBS wildfire perimeters drawn on top, so the
mismatch is visible rather than only quoted as a lift statistic:

    (a) fire weather class   -- the layer that fails
    (b) fuel_index           -- the layer that works
    (c) combined class       -- what the cost penalty actually consumes

MTBS is satellite-mapped burned area over ALL ownerships, filtered to
`incid_type == 'Wildfire'` (prescribed fire is a management decision and is
concentrated on federal land). Fires >=500 acres east / >=1000 west, so this
is significant fires, not all ignitions.

Read the panels together: in (a) the burned perimeters sit mostly on pale
`none` ground, in (b) they sit on dark high-fuel ground. That contrast IS the
finding -- fire weather marks burned ground as safer than average (lift 0.25x
TVA, 0.42x SoCal) while fuel marks it as riskier (1.87x / 1.83x).

Run in the `rev` conda env (~20 s, no batch job needed):
    conda activate rev
    REGION=tva   python plot_mtbs_validation_map.py
    REGION=socal python plot_mtbs_validation_map.py

Outputs (to outputs/risk_future_with_fuel/):
  * mtbs_validation_<region>.png
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
                                         CLASS_COLORS, OCEAN_COLOR,
                                         LAND_COLOR, STATES_PATH)
from plot_fuel_maps import rasterize_f, load as load_region

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_with_fuel")
REGION = os.environ.get("REGION", "tva")
MTBS = os.path.join(PROJ, "data", "fire_perimeters",
                    f"{REGION}_mtbs_wildfires.gpkg")


def burned_mask(d, fires):
    """Cells overlapping any wildfire perimeter.

    Bounding-box prefilter then exact intersect: the `rev` env has no spatial
    index, and a naive all-pairs test is ~18 M polygon intersections."""
    lon, lat = d.lon.to_numpy(), d.lat.to_numpy()
    m = np.zeros(len(d), bool)
    for g, (x0, y0, x1, y1) in zip(fires.geometry,
                                   fires.geometry.bounds.to_numpy()):
        for i in np.where((lon > x0-.03) & (lon < x1+.03) &
                          (lat > y0-.03) & (lat < y1+.03))[0]:
            if not m[i] and d.geometry.iloc[i].intersects(g):
                m[i] = True
    return m


def main():
    d = load_region(REGION)
    fires = gpd.read_file(MTBS).to_crs(4326)
    b = burned_mask(d, fires)
    lv = {c: i for i, c in enumerate(CLASS_ORDER)}

    cfg = REGIONS[REGION]
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]
    step = grid_step(d.lon.to_numpy(), d.lat.to_numpy())
    lon, lat = d.lon.to_numpy(), d.lat.to_numpy()
    lon0, lat0 = float(lon.min()), float(lat.min())
    grid = {"lon0": lon0, "lat0": lat0,
            "nx": int(np.rint((lon.max()-lon0)/step))+1,
            "ny": int(np.rint((lat.max()-lat0)/step))+1}
    states = gpd.read_file(STATES_PATH).to_crs(4326)

    def lift(v):
        return v[b].mean() / max(v[~b].mean(), 1e-9)

    fw = np.array([lv[c] for c in d.risk_class], dtype="float64")
    cb = np.array([lv[c] for c in d.combined_class], dtype="float64")
    fi = d.fuel_index.to_numpy()
    # Lift is a ratio of means, so it is NOT comparable across scales: the
    # continuous 0-1 index and a 0-3 class scale give different numbers for the
    # same signal. Report the quartile-classed value too, since that is what the
    # validation doc quotes and what the other two panels are measured on.
    fi_cls = np.digitize(fi, d.fuel_index.quantile([.25, .50, .75]).to_numpy())
    fi_cls = np.where(d.nonburnable_gated.to_numpy() == 1, 0, fi_cls)

    cls_cmap = ListedColormap([CLASS_COLORS[c] for c in CLASS_ORDER])
    panels = [
        ("(a) fire weather class\nthe layer that FAILS  —  lift %.2fx" % lift(fw),
         fw, cls_cmap, 0, len(CLASS_ORDER)-1, None),
        ("(b) fuel_index (shown continuous)\nthe layer that WORKS  —  "
         "lift %.2fx classed at quartiles" % lift(fi_cls),
         fi, "YlGn", 0, 1, "fuel_index"),
        ("(c) combined class (what the cost penalty uses)\nlift %.2fx" % lift(cb),
         cb, cls_cmap, 0, len(CLASS_ORDER)-1, None),
    ]

    pw = 6.4
    fig, axes = plt.subplots(1, 3,
                             figsize=(pw*3, pw*(y1-y0)/(x1-x0) + 2.4),
                             constrained_layout=True)
    for ax, (title, vals, cmap, vmin, vmax, cbar) in zip(axes, panels):
        ax.set_facecolor(OCEAN_COLOR)
        states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
        img, ext = rasterize_f(lon, lat, vals, grid, step)
        im = ax.imshow(img, extent=ext, origin="lower", cmap=cmap,
                       interpolation="nearest", vmin=vmin, vmax=vmax, zorder=2)
        states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)
        # perimeters: BLACK outlines, unfilled. Red was unreadable -- the class
        # palette is itself red, and panel (b) is green, so only a neutral dark
        # outline reads against all three backgrounds.
        fires.plot(ax=ax, facecolor="none", edgecolor="black",
                   linewidth=0.8, zorder=6)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10.5)
        if cbar:
            fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01, label=cbar)
        else:
            ax.legend(handles=[Line2D([0], [0], marker="s", linestyle="None",
                                      color=CLASS_COLORS[c], markersize=10,
                                      label=c) for c in CLASS_ORDER]
                      + [Line2D([0], [0], color="black", lw=1.6,
                                label="MTBS wildfire")],
                      loc="lower left", fontsize=8.5, framealpha=0.95)

    fig.suptitle(
        f"{cfg['label']}: risk classes vs {len(fires):,} MTBS wildfires "
        f"({int(fires.burnbndac.sum()):,} acres)\n"
        f"{b.sum():,} of {len(d):,} cells burned — lift >1 marks burned ground "
        f"riskier than average, <1 marks it SAFER", fontsize=13)
    out = os.path.join(PRODUCT_DIR, f"mtbs_validation_{REGION}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")
    print(f"  burned cells {b.sum():,}/{len(d):,} | lift  fw {lift(fw):.2f}x "
          f"fuel {lift(fi_cls):.2f}x (classed) / {lift(fi):.2f}x (continuous) "
          f"| combined {lift(cb):.2f}x")


if __name__ == "__main__":
    main()
