"""
Explainer figures for the wildfire-risk cost penalty.

Visualises what each field in `tva_cost_risk_penalty_cells.gpkg` actually means,
and how the ~2.8 km risk classes act on the 90 m cost surface. Made because
"sum of adjusted cost" is impossible to picture from a field name.

Figure 1 -- the penalty in action over a small window:
    (a) risk class, on the ~2.8 km fire-weather grid
    (b) original cost, 90 m
    (c) adjusted cost, 90 m, same colour scale as (b)
    (d) the multiplier actually applied (adjusted / original), 90 m -- shows the
        penalty is blocky at 2.8 km even though the cost grid is 90 m

Figure 2 -- one risk cell, blown up to individual 90 m pixels, showing the
    difference between cost_mean (one pixel), cost_sum (every pixel in the
    square) and what a line actually pays to cross (one row of pixels). This is
    the figure that explains why the _sum fields are not route costs.

Run in the `rev` conda env:
    conda activate rev
    python plot_cost_penalty_explainer.py

Outputs (to OUT_DIR):
  * cost_penalty_explainer_zoom.png
  * cost_penalty_explainer_cell.png
"""

import os

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"

# Must match the RISK_SOURCE the penalty raster was built with -- panels (c)
# and (d) come from that raster, so mixing sources would show one period's
# classes beside another period's multiplier.
RISK_SOURCE = os.environ.get("RISK_SOURCE", "future_with_fuel")

_SOURCES = {
    "historical": ("risk_historical", "abs_risk_hist_p98_risk_classes.gpkg",
                   "risk_class"),
    "future": ("risk_future", "abs_risk_future_p98_risk_classes.gpkg",
               "risk_class"),
    # the combined product puts its answer in `combined_class`; `risk_class`
    # there is the fire-weather-only class, kept for traceability
    "future_with_fuel": ("risk_future_with_fuel",
                         "abs_risk_future_fuel_tva_risk_classes.gpkg",
                         "combined_class"),
}
if RISK_SOURCE not in _SOURCES:
    raise SystemExit(f"bad RISK_SOURCE {RISK_SOURCE!r}")
_sub, _fname, CLASS_COL = _SOURCES[RISK_SOURCE]
RISK_GPKG = os.path.join(OUT_DIR, "outputs", _sub, _fname)
PRODUCT_DIR = os.path.join(OUT_DIR, "outputs", f"cost_penalty_{RISK_SOURCE}")
COST_GPKG = os.path.join(PRODUCT_DIR, "tva_cost_risk_penalty_cells.gpkg")
ADJ_TIF = os.path.join(PRODUCT_DIR, "tva_cost_risk_penalty_90m.tif")

# Route geometry does not depend on the penalty, so the example route is picked
# from whichever per-route analysis exists; only which route is shown changes.
ROUTE_CSV = os.path.join(OUT_DIR, "outputs", "cost_penalty_historical",
                         "tva_route_risk_cost.csv")
ORIG_TIF = ("/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/"
            "tva_lcp_default_agg_costs.tif")
ROUTES_GPKG = ("/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/"
               "tva_lcp_route_points.gpkg")

# Window with all four risk classes present (found by scanning the TVA grid).
ZOOM = (-86.98, 36.32, -86.55, 36.62)          # lon0, lat0, lon1, lat1

CLASS_ORDER = ["none", "low", "medium", "high"]
CLASS_COLORS = {"none": "#cfcfcf", "low": "#fc9272",
                "medium": "#ef3b2c", "high": "#99000d"}
MULTIPLIERS = [1.0, 1.1, 1.3, 1.5]
COST_CMAP = "Blues"                  # single hue, light -> dark, for magnitude


def read_window(path, bounds4326, crs):
    """Read a raster over a lon/lat box; return array + extent in raster CRS."""
    with rasterio.open(path) as r:
        b = transform_bounds("EPSG:4326", crs, *bounds4326)
        win = from_bounds(*b, transform=r.transform)
        a = r.read(1, window=win, masked=True)
        t = r.window_transform(win)
        ext = [t.c, t.c + a.shape[1] * t.a, t.f + a.shape[0] * t.e, t.f]
    return a, ext


def figure_zoom(cells):
    x0, y0, x1, y1 = ZOOM
    with rasterio.open(ADJ_TIF) as r:
        crs = r.crs
    orig, ext = read_window(ORIG_TIF, ZOOM, crs)
    adj, _ = read_window(ADJ_TIF, ZOOM, crs)

    sub = cells.cx[x0:x1, y0:y1].to_crs(crs)
    lo, hi = np.percentile(orig.compressed(), [2, 98])

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 11.5),
                             constrained_layout=True)
    (ax_a, ax_b), (ax_c, ax_d) = axes

    # (a) risk class on the coarse grid
    for cls in CLASS_ORDER:
        s = sub[sub[CLASS_COL] == cls]
        if len(s):
            s.plot(ax=ax_a, color=CLASS_COLORS[cls], edgecolor="white",
                   linewidth=0.3)
    ax_a.set_title("(a) risk class — the ~2.8 km fire-weather grid\n"
                   "one square = one row in the .gpkg", fontsize=11)
    ax_a.legend(handles=[Line2D([0], [0], marker="s", linestyle="None",
                                color=CLASS_COLORS[c], markersize=11,
                                label=f"{c}  (x{m})")
                         for c, m in zip(CLASS_ORDER, MULTIPLIERS)],
                loc="lower left", fontsize=9, framealpha=0.95)

    # (b) and (c) share a colour scale so the change is honestly small
    for ax, a, ttl in [
            (ax_b, orig, "(b) original cost, 90 m\ntva_lcp_default_agg_costs.tif"),
            (ax_c, adj, "(c) adjusted cost, 90 m — same colour scale as (b)\n"
                        "tva_cost_risk_penalty_90m.tif")]:
        im = ax.imshow(a, extent=ext, origin="upper", cmap=COST_CMAP,
                       vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(ttl, fontsize=11)
        fig.colorbar(im, ax=ax, shrink=0.8, label="cost per 90 m cell")

    # (d) the multiplier that was actually applied
    ratio = np.where(orig > 0, adj / np.where(orig == 0, 1, orig), np.nan)
    cmap = ListedColormap([CLASS_COLORS[c] for c in CLASS_ORDER])
    norm = BoundaryNorm([0.95, 1.05, 1.2, 1.4, 1.6], cmap.N)
    im = ax_d.imshow(ratio, extent=ext, origin="upper", cmap=cmap, norm=norm,
                     interpolation="nearest")
    ax_d.set_title("(d) multiplier applied = (c) / (b)\n"
                   "blocky at 2.8 km because the risk grid is", fontsize=11)
    cb = fig.colorbar(im, ax=ax_d, shrink=0.8, ticks=[1.0, 1.15, 1.35, 1.55])
    cb.ax.set_yticklabels([f"x{m}" for m in MULTIPLIERS])

    for ax in axes.ravel():
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])

    fig.suptitle("How the wildfire-risk penalty acts on the transmission cost "
                 "surface\n(TVA, ~36.5N 86.8W — the risk class of each 2.8 km "
                 "square multiplies every 90 m cost cell inside it)",
                 fontsize=13)
    out = os.path.join(PRODUCT_DIR, "cost_penalty_explainer_zoom.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


def pick_cell_and_route(cells):
    """A real routed line and the risk cell it spends the longest inside.

    No synthetic straight crossing: the actual least-cost paths are on disk, and
    they wander -- the chord this finds is longer than the cell's diagonal.
    (geopandas here has no rtree/pygeos, so the candidate cells are filtered
    numerically on centroid coordinates rather than with a spatial index.)"""
    import pandas as pd
    res = pd.read_csv(ROUTE_CSV)
    r = gpd.read_file(ROUTES_GPKG)
    r = r[r.geom_type == "LineString"].to_crs(cells.crs).reset_index(drop=True)

    # a mid-exposure route, so the example is representative not extreme
    i = int(res.assign(k=(res["pct_increase"] - 20).abs())
               .nsmallest(1, "k").index[0])
    line = r.geometry.iloc[i]

    cx = cells.geometry.centroid.x.values
    cy = cells.geometry.centroid.y.values
    hot = cells["risk_class"].isin(["medium", "high"]).values  # cost gpkg: always risk_class
    x0, y0, x1, y1 = line.bounds
    near = np.flatnonzero(hot & (cx > x0) & (cx < x1) & (cy > y0) & (cy < y1))

    best, bi = None, None
    for k in near:
        seg = line.intersection(cells.geometry.iloc[k])
        if not seg.is_empty and seg.geom_type == "LineString":
            if best is None or seg.length > best.length:
                best, bi = seg, int(k)
    return cells.iloc[bi], best, res.iloc[i]


def figure_cell():
    """One risk cell at 90 m, with a REAL routed line crossing it.

    Shows what each .gpkg field counts: one pixel (cost_mean), the cells an
    actual least-cost path traverses (what a crossing really costs), and the
    whole square (cost_sum). Uses the cost gpkg so the labels are the
    authoritative values, and masks to the cell's true tilted footprint."""
    from rasterio.features import geometry_mask

    g = gpd.read_file(COST_GPKG, layer="risk_cost")
    c, seg, route = pick_cell_and_route(g)

    with rasterio.open(ORIG_TIF) as r:
        pad = 200.0                                  # metres of context
        minx, miny, maxx, maxy = c.geometry.bounds
        win = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad,
                          transform=r.transform)
        cost = r.read(1, window=win).astype(float)
        t = r.window_transform(win)
    ny, nx = cost.shape
    ext = [t.c, t.c + nx * t.a, t.f + ny * t.e, t.f]

    inside = geometry_mask([c.geometry], out_shape=(ny, nx), transform=t,
                           invert=True, all_touched=True)
    v = np.where(inside, cost, np.nan)
    lo, hi = np.nanpercentile(v, [2, 98])

    fig, ax = plt.subplots(figsize=(9.8, 9.6), constrained_layout=True)
    ax.imshow(np.where(inside, np.nan, cost), extent=ext, origin="upper",
              cmap="Greys", vmin=lo, vmax=hi, alpha=0.25,
              interpolation="nearest")                # context, greyed out
    im = ax.imshow(v, extent=ext, origin="upper", cmap=COST_CMAP,
                   vmin=lo, vmax=hi, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.8,
                 label="original cost of one 90 m cell")

    dx, dy = abs(t.a), abs(t.e)
    for i in range(nx + 1):                           # 90 m pixel grid
        ax.plot([ext[0] + i * dx] * 2, [ext[2], ext[3]], color="white",
                lw=0.3, alpha=0.5, zorder=3)
    for j in range(ny + 1):
        ax.plot([ext[0], ext[1]], [ext[3] - j * dy] * 2, color="white",
                lw=0.3, alpha=0.5, zorder=3)

    # --- the REAL routed line through this cell, sampled at 9 m -------------
    n = max(int(seg.length / 9.0) + 1, 2)
    pts = [seg.interpolate(s) for s in np.linspace(0.0, seg.length, n)]
    px = np.fromiter((p.x for p in pts), float, n)
    py = np.fromiter((p.y for p in pts), float, n)
    pc_ = np.floor((px - t.c) / t.a).astype(int)
    pr_ = np.floor((py - t.f) / t.e).astype(int)
    ok = (pr_ >= 0) & (pr_ < ny) & (pc_ >= 0) & (pc_ < nx)
    pr_, pc_ = pr_[ok], pc_[ok]
    ds = seg.length / (n - 1)
    # distance-weighted, matching the routing pipeline: a diagonal step covers
    # 127 m of ground, not 90 m, so cost is accrued per metre travelled.
    crossing = float(np.nansum(cost[pr_, pc_] * ds) / dx)
    n_traversed = int(np.unique(pr_ * nx + pc_).size)

    touched = np.full((ny, nx), np.nan)
    touched[pr_, pc_] = 1.0
    ax.imshow(touched, extent=ext, origin="upper",
              cmap=ListedColormap(["#00a0a0"]), alpha=0.55,
              interpolation="nearest", zorder=4)
    gpd.GeoSeries([seg], crs=g.crs).plot(ax=ax, color="#00484d", linewidth=2.0,
                                         zorder=5)
    # one 90 m cell -- the free pixel nearest the cell centre, so the marker is
    # always inside the footprint and never hidden under the route
    cent = c.geometry.centroid
    crow = int((cent.y - t.f) / t.e)
    ccol = int((cent.x - t.c) / t.a)
    free_r, free_c = np.nonzero(inside & ~np.isfinite(touched))
    k = int(np.argmin((free_r - crow) ** 2 + (free_c - ccol) ** 2))
    pr0, pc0 = int(free_r[k]), int(free_c[k])
    ax.add_patch(Rectangle((ext[0] + pc0 * dx, ext[3] - (pr0 + 1) * dy), dx, dy,
                           fill=False, edgecolor="#111111", linewidth=2.4,
                           zorder=6))
    # the whole risk cell
    gpd.GeoSeries([c.geometry], crs=g.crs).boundary.plot(
        ax=ax, color="#99000d", linewidth=3.0, zorder=7)

    ax.set_title(f"One risk cell — {c['risk_class']}, ×{c['multiplier']:.1f}, "
                 f"containing {int(c['n_cost_cells']):,} cost cells of 90 m\n"
                 f"crossed by a real least-cost path: "
                 f"{route['start_BusName']} → {route['end_BusName']}",
                 fontsize=11.5)
    ax.legend(handles=[
        Line2D([0], [0], color="#111111", lw=2.4,
               label=f"one 90 m cell  →  cost_mean = {c['cost_mean']:,.0f}"),
        Line2D([0], [0], color="#00a0a0", lw=7, alpha=0.7,
               label=f"the real route through this cell — {n_traversed} cells "
                     f"over {seg.length:,.0f} m\n     →  the crossing costs "
                     f"{crossing:,.0f}  (distance-weighted)"),
        Line2D([0], [0], color="#99000d", lw=3.0,
               label=f"every cell in the square  →  cost_sum = "
                     f"{c['cost_sum']:,.0f}  ({c['cost_sum']/crossing:.0f}x "
                     f"the crossing)")],
        loc="upper center", bbox_to_anchor=(0.5, -0.015), fontsize=10.5,
        frameon=True)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])

    fig.suptitle("Why the _sum fields are area totals, not route costs",
                 fontsize=13.5)
    out = os.path.join(PRODUCT_DIR, "cost_penalty_explainer_cell.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")
    print(f"    real crossing: {n_traversed} cells, {seg.length:,.0f} m, cost {crossing:,.0f}")


def main():
    cells = gpd.read_file(RISK_GPKG, layer="risk_classes")
    cells = cells[cells["region"] == "tva"]
    cells["multiplier"] = cells["risk_class"].map(
        dict(zip(CLASS_ORDER, MULTIPLIERS)))
    figure_zoom(cells)
    figure_cell()


if __name__ == "__main__":
    main()
