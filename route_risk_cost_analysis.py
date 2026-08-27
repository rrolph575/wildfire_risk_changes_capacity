"""
Per-route wildfire cost penalty for the existing TVA least-cost paths.

Samples the original and penalised 90 m cost surfaces along each of the routed
lines already on disk, and reports what wildfire risk adds to each one.

WHAT THIS ANSWERS (and what it does not)
    The routes in tva_lcp_route_points.gpkg were optimised against the
    ORIGINAL cost surface. Re-costing those same paths on the penalised surface
    answers "what does wildfire risk cost if nothing reroutes" -- an UPPER
    BOUND on the penalty's impact, because a re-run router would detour around
    penalised ground and pay less.

    Getting the genuinely re-optimised routes means re-running the sienna
    transmission LCP pipeline with tva_cost_risk_penalty_90m.tif as its cost
    input. That is that pipeline's job, not this script's.

METHOD
    Each route is densified to a point every 45 m (half a cell) so no traversed
    cell is skipped, converted to raster row/col, and consecutive duplicates
    dropped -- giving the exact sequence of 90 m cells the line passes through.
    Original and adjusted cost are summed over that sequence.

    The per-cell multiplier is recovered as adjusted/original, which also gives
    the share of each route sitting in each risk class. Cells outside the risk
    region (nodata in the adjusted raster) are counted and charged at x1.0.

    NOTE this sums raw cell values; it does NOT weight each step by the distance
    travelled through the cell. The routing pipeline does. Confirmed:

        pipeline `cost` / my plain cell sum      median 1.1694
        implied step factor from route geometry  median 1.1726
        (1.000 = every step straight, 1.414 = every step diagonal)

    Those agree to 0.3%, and the per-layer component costs in the route gpkg sum
    to its `cost` column exactly (ratio 1.0000), ruling out a scope difference.
    So the gap is purely diagonal/distance weighting: a diagonal step crosses
    127.3 m of ground, not 90 m.

    CONSEQUENCE: `orig_cost_sum` / `adj_cost_sum` here are ~14.5% below the
    pipeline's basis and must NOT be quoted as absolute costs. `pct_increase` is
    unaffected -- it is a ratio over the same cells, and step length is
    uncorrelated with risk class. For absolute figures use the pipeline's own
    cost scaled by that percentage, which is what the *_pipeline_basis columns
    below do.

Outputs (to OUT_DIR):
  * tva_route_endpoint_costs.csv -- the slim one: each route's two endpoints in
        lat/lon with its total cost before and after the wildfire penalty, on
        the routing pipeline's own cost basis. Start here.
  * tva_route_risk_cost.csv   -- one row per route: length, original cost,
        adjusted cost, % increase, and the share of the route in each class.
  * tva_route_risk_cost.gpkg  -- the same, with the route geometries.
  * tva_route_risk_cost.png   -- routes coloured by % cost increase, plus the
        distribution across all routes.

Run in the `rev` conda env:
    conda activate rev
    python route_risk_cost_analysis.py
"""

import os

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.windows import Window
from matplotlib.lines import Line2D
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from region_inputs import region_input

OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
# Region to analyse. Env-driven; SoCal stops with a clear message until its
# routing inputs are supplied -- see region_inputs.py.
REGION = os.environ.get("REGION", "tva")
ROUTES_GPKG = region_input(REGION, "routes_gpkg")
ORIG_TIF = region_input(REGION, "cost_tif")
# Which penalty raster to re-cost the existing routes against:
#   historical | future | future_with_fuel
# Env-overridable so one batch job can cover several without editing this file.
RISK_SOURCE = os.environ.get("RISK_SOURCE", "future_with_fuel")
if RISK_SOURCE not in ("historical", "future", "future_with_fuel"):
    raise SystemExit(f"bad RISK_SOURCE {RISK_SOURCE!r}")
PRODUCT_DIR = os.path.join(OUT_DIR, "outputs", f"cost_penalty_{RISK_SOURCE}")
ADJ_TIF = os.path.join(PRODUCT_DIR, f"{REGION}_cost_risk_penalty_90m.tif")
STATES_PATH = "/projects/rev/projects/scapes/maps/conus_state_boundaries.gpkg"

STEP_M = 45.0                     # sampling interval along each route
CLASS_ORDER = ["none", "low", "medium", "high"]
MULTIPLIERS = [1.0, 1.1, 1.3, 1.5]
CLASS_COLORS = {"none": "#cfcfcf", "low": "#fc9272",
                "medium": "#ef3b2c", "high": "#99000d"}
TAG = f"{REGION}_route_risk_cost"


# ----------------------------------------------------------------------------
def route_cells(geom, tr, nrow, ncol):
    """Sequence of raster (row, col) a line passes through, in order."""
    n = max(int(geom.length / STEP_M) + 1, 2)
    d = np.linspace(0.0, geom.length, n)
    pts = [geom.interpolate(t) for t in d]
    x = np.fromiter((p.x for p in pts), float, n)
    y = np.fromiter((p.y for p in pts), float, n)

    col = np.floor((x - tr.c) / tr.a).astype(np.int64)
    row = np.floor((y - tr.f) / tr.e).astype(np.int64)   # tr.e is negative
    ok = (row >= 0) & (row < nrow) & (col >= 0) & (col < ncol)
    row, col = row[ok], col[ok]
    if row.size == 0:
        return row, col
    flat = row * ncol + col
    keep = np.ones(flat.size, bool)
    keep[1:] = flat[1:] != flat[:-1]                     # drop repeats
    return row[keep], col[keep]


def main():
    routes = gpd.read_file(ROUTES_GPKG)
    routes = routes[routes.geom_type == "LineString"].reset_index(drop=True)

    with rasterio.open(ADJ_TIF) as a, rasterio.open(ORIG_TIF) as s:
        tr, nrow, ncol, nodata = a.transform, a.height, a.width, a.nodata
        routes = routes.to_crs(a.crs)
        print(f"{len(routes):,} routes; loading {nrow:,} x {ncol:,} cost "
              f"windows into memory")
        adj = a.read(1)
        r0, c0 = s.index(tr.c, tr.f)
        orig = s.read(1, window=Window(int(c0), int(r0), ncol, nrow))

    rows = []
    for i, g in enumerate(routes.geometry):
        rr, cc = route_cells(g, tr, nrow, ncol)
        o = orig[rr, cc].astype("float64")
        d = adj[rr, cc].astype("float64")
        outside = d == nodata                 # outside the risk region
        d = np.where(outside, o, d)           # charged at x1.0 there

        mult = np.where(o > 0, d / np.where(o == 0, 1.0, o), 1.0)
        share = {c: float(np.isclose(mult, m, atol=0.02).mean())
                 for c, m in zip(CLASS_ORDER, MULTIPLIERS)}
        rows.append({
            "n_cells": int(rr.size),
            "cells_outside_region": int(outside.sum()),
            "orig_cost_sum": o.sum(),
            "adj_cost_sum": d.sum(),
            "pct_increase": 100.0 * (d.sum() / o.sum() - 1.0) if o.sum() else np.nan,
            **{f"frac_{c}": share[c] for c in CLASS_ORDER},
        })
        if (i + 1) % 250 == 0:
            print(f"  {i+1:,}/{len(routes):,}", end="\r")

    res = pd.concat([routes[["start_BusName", "end_BusName", "length_km",
                             "voltage", "cost", "rid"]].reset_index(drop=True),
                     pd.DataFrame(rows)], axis=1)
    res["added_cost"] = res["adj_cost_sum"] - res["orig_cost_sum"]
    # Absolute figures on the ROUTING PIPELINE's cost basis: take its own `cost`
    # for the route and scale by the percentage measured here. This is the pair
    # to quote -- see the note on distance weighting in the module docstring.
    res["added_cost_pipeline_basis"] = res["cost"] * res["pct_increase"] / 100.0
    res["adj_cost_pipeline_basis"] = res["cost"] + res["added_cost_pipeline_basis"]

    out_csv = os.path.join(PRODUCT_DIR, f"{TAG}.csv")
    res.to_csv(out_csv, index=False)
    print(f"\n  saved -> {out_csv}")

    # Slim companion: just the endpoints and the before/after totals. Costs are
    # on the ROUTING PIPELINE's basis (see the note on distance weighting
    # above) -- these are the figures to quote, not orig/adj_cost_sum.
    ends = pd.DataFrame({
        "start_BusName": res["start_BusName"],
        "end_BusName": res["end_BusName"],
        "start_lat": routes["start_lat"].values,
        "start_lon": routes["start_lon"].values,
        "end_lat": routes["end_lat"].values,
        "end_lon": routes["end_lon"].values,
        "length_km": res["length_km"].round(3),
        "voltage": res["voltage"],
        "cost_before_penalty": res["cost"],
        "cost_after_penalty": res["adj_cost_pipeline_basis"],
        "added_cost": res["added_cost_pipeline_basis"],
        "pct_increase": res["pct_increase"].round(3),
    })
    ends_csv = os.path.join(PRODUCT_DIR, f"{REGION}_route_endpoint_costs.csv")
    ends.to_csv(ends_csv, index=False)
    print(f"  saved -> {ends_csv}")
    gdf = gpd.GeoDataFrame(res.copy(), geometry=routes.geometry.values,
                           crs=routes.crs)
    out_gpkg = os.path.join(PRODUCT_DIR, f"{TAG}.gpkg")
    gdf.to_file(out_gpkg, layer="route_risk_cost", driver="GPKG")
    print(f"  saved -> {out_gpkg}")

    # ---------------------------------------------------------------- report
    p = res["pct_increase"]
    print(f"\nper-route cost increase from the wildfire penalty:")
    print(f"  min {p.min():.2f}%  p25 {p.quantile(.25):.2f}%  "
          f"median {p.median():.2f}%  p75 {p.quantile(.75):.2f}%  "
          f"max {p.max():.2f}%")
    tot_o, tot_a = res["orig_cost_sum"].sum(), res["adj_cost_sum"].sum()
    print(f"  all routes combined: {tot_o:.4g} -> {tot_a:.4g} "
          f"({100*(tot_a/tot_o-1):.2f}% higher)")
    print(f"  route-length in each class (mean share): "
          + ", ".join(f"{c} {100*res['frac_'+c].mean():.1f}%"
                      for c in CLASS_ORDER))
    print(f"  cells outside the risk region: "
          f"{int(res['cells_outside_region'].sum()):,} of "
          f"{int(res['n_cells'].sum()):,}")

    print("\nmost exposed routes:")
    print(res.nlargest(5, "pct_increase")[
        ["start_BusName", "end_BusName", "length_km", "pct_increase",
         "frac_high"]].to_string(index=False))

    # how does a plain cell-sum compare to the pipeline's own cost column?
    r = res["orig_cost_sum"] / res["cost"]
    print(f"\nsanity: my plain sum of original cells / gpkg 'cost' column: "
          f"median {r.median():.3f} (min {r.min():.3f}, max {r.max():.3f})")

    figure(gdf, res)


def figure(gdf, res):
    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(16.5, 7.4), constrained_layout=True,
        gridspec_kw={"width_ratios": [1.35, 1]})

    # Geographic context under the routes. State lines only -- deliberately no
    # region outline: the "TVA region" in this project is just the lat/lon box
    # derived from the bus span, NOT a TVA service-territory boundary, and
    # drawing it invites reading it as authoritative.
    try:
        states = gpd.read_file(STATES_PATH).to_crs(gdf.crs)
        states.boundary.plot(ax=ax, color="0.72", linewidth=0.7, zorder=0)
    except Exception as e:
        print(f"  (skipping state boundaries: {e})")

    vmax = float(np.nanpercentile(res["pct_increase"], 98))
    gdf.plot(ax=ax, column="pct_increase", cmap="YlOrRd", linewidth=1.0,
             vmin=0, vmax=vmax, legend=True,
             legend_kwds={"label": "cost increase along the route (%)",
                          "shrink": 0.8})
    ax.set_title(f"{len(gdf):,} existing TVA routes, re-costed on the "
                 f"wildfire-penalised surface\n(same paths, new price — "
                 f"an upper bound; a re-run router would detour)", fontsize=11)
    ax.legend(handles=[Line2D([0], [0], color="0.72", lw=0.7,
                              label="state boundaries")],
              loc="lower left", fontsize=9, framealpha=0.95)
    b = gdf.total_bounds
    pad = 0.04 * max(b[2] - b[0], b[3] - b[1])
    ax.set_xlim(b[0] - pad, b[2] + pad); ax.set_ylim(b[1] - pad, b[3] + pad)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")

    ax2.hist(res["pct_increase"], bins=40, color="#ef3b2c", edgecolor="white")
    med = res["pct_increase"].median()
    ax2.axvline(med, color="#111111", lw=2,
                label=f"median {med:.2f}%")
    ax2.axvline(11.70, color="#00a0a0", lw=2, ls="--",
                label="11.70% = area average\n(if a line crossed every cell)")
    ax2.set_xlabel("cost increase along the route (%)")
    ax2.set_ylabel("routes")
    ax2.set_title("Distribution across routes", fontsize=11)
    ax2.legend(fontsize=9.5)
    ax2.spines[["top", "right"]].set_visible(False)

    out = os.path.join(PRODUCT_DIR, f"{TAG}.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


def figure_only():
    """Redraw the figure from the saved outputs, skipping the ~7 min sampling.

    Usage: python route_risk_cost_analysis.py figure"""
    gdf = gpd.read_file(os.path.join(PRODUCT_DIR, f"{TAG}.gpkg"),
                        layer="route_risk_cost")
    figure(gdf, pd.DataFrame(gdf.drop(columns="geometry")))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "figure":
        figure_only()
    else:
        main()
