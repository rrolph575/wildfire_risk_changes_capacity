"""
Wildfire-risk cost penalty for TVA transmission routing.

Applies a multiplicative penalty to the least-cost-path (LCP) cost surface used
to route transmission between nodes, so that a candidate line pays more for
every metre it spends in higher wildfire-risk ground. Risk classes come from
`abs_risk_hist_p98_risk_classes.gpkg` (see
documentation_and_summaries/summary_of_methods_absolute_regional_thresholds.md).

    adjusted_cost(cell) = original_cost(cell) x multiplier(risk class of cell)

THE PENALTY
    none    x1.0    no added cost -- a line that only crosses no-risk ground
                    costs exactly what it costs today
    low     x1.1    +10%
    medium  x1.3    +30%
    high    x1.5    +50%

    Note "none" is 1.0, NOT 0. A 0 multiplier would make no-risk ground *free*
    rather than unpenalised, and the router would collapse every path onto it.
    Edit RISK_MULTIPLIER to retune.

    Because the penalty is applied per cell and the router sums cost along a
    path, the "percentage of the line in each class" weighting falls out
    automatically: a route that is 30% medium-risk and 70% none pays
    0.3*1.3 + 0.7*1.0 = 1.09x, without that fraction ever being computed.

RESOLUTION
    The cost raster is 90 m (EPSG:5070); the risk cells are ~0.0281 deg
    (~2.8 km), so ~900 cost cells sit inside each risk cell. Every 90 m cell
    takes the class of the risk cell containing it. The penalty is therefore
    blocky at 2.8 km -- it is as sharp as the fire-weather grid allows, which is
    much coarser than the routing grid.

SCOPE
    TVA only. The cost raster is a TVA routing product; it carries values over
    SoCal too, but ~37% of that area is zero (ocean / outside the AOI) and it
    was not built for that region. Set REGION to run elsewhere at your own risk.

    A lat/lon region box becomes a tilted quad in EPSG:5070, so ~17% of the
    output window falls outside the risk cells. With EXCLUDE_OUTSIDE_REGION
    (default) that area is written as nodata, making it impassable so no route
    can leave the region -- otherwise a path could bulge outside and pay no
    penalty at all. The raster's own nodata cells pass through untouched.

    Endpoints are checked separately: a route with a bus outside the region is
    dropped. For the current TVA route set nothing is dropped, and cannot be --
    the region box was derived from the bus span, so every bus is inside it.
    The check is a guard for future route sets or a changed box.

Outputs (all written to OUT_DIR):
  * tva_cost_risk_penalty_90m.tif  -- adjusted 90 m cost surface, EPSG:5070,
        float32, same grid alignment and nodata as the input raster, cropped to
        the TVA risk extent (the full CONUS input is 3.9 billion cells; this
        window is 52 M). This is the file to feed back into routing.
  * tva_cost_risk_penalty_cells.gpkg -- layer "risk_cost", one polygon per
        ~2.8 km risk cell, for inspection in QGIS. Fields: region, risk_class,
        risk_level, multiplier, n_cost_cells, cost_mean, cost_sum,
        adj_cost_mean, adj_cost_sum, added_cost (adj_cost_sum - cost_sum).
  * tva_cost_risk_penalty_routes_in_region.csv -- tva_routes.csv filtered to
        routes with both endpoints inside the region.

Run in the `rev` conda env (needs rasterio):
    conda activate rev
    python transmission_cost_risk_penalty.py
"""

import os

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.windows import Window
from rasterio.features import rasterize
from region_inputs import region_input

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"

# Which risk classes to price: "historical" (2000-2014 fire weather) or
# "future" (2025-2059, cutoffs held fixed at the historical values). Outputs go
# to outputs/cost_penalty_<source>/ so the two never overwrite each other.
#
# Overridable from the environment so one batch job can do both without editing
# this file:  RISK_SOURCE=future python transmission_cost_risk_penalty.py
#   historical        2000-2014 fire weather only
#   future            2025-2059 fire weather only, historical cutoffs held fixed
#   future_with_fuel  the above combined with LANDFIRE fuel (see
#                     combine_fwi_fuel_risk.py) -- fuel shifts the fire-weather
#                     class by one step, then a non-burnable gate is applied
RISK_SOURCE = os.environ.get("RISK_SOURCE", "future")

_SOURCES = {
    "historical": ("risk_historical", "abs_risk_hist_p98_risk_classes.gpkg",
                   "risk_class"),
    "future": ("risk_future", "abs_risk_future_p98_risk_classes.gpkg",
               "risk_class"),
    # NOTE the different column: the combined product keeps `risk_class` for
    # the fire-weather-only class so both inputs stay traceable, and puts the
    # combined answer in `combined_class`. Read the right one.
    "future_with_fuel": ("risk_future_with_fuel",
                         "abs_risk_future_fuel_{region}_risk_classes.gpkg",
                         "combined_class"),
}
if RISK_SOURCE not in _SOURCES:
    raise SystemExit(f"RISK_SOURCE must be one of {sorted(_SOURCES)}, "
                     f"got {RISK_SOURCE!r}")
# Region to cost. Env-driven, matching combine_fwi_fuel_risk.py and
# landfire_fuel_composition.py, so one script serves both:
#   REGION=socal RISK_SOURCE=future_with_fuel python transmission_cost_risk_penalty.py
# SoCal will stop with a clear message until its routing inputs are supplied --
# see region_inputs.py.
REGION = os.environ.get("REGION", "tva")

_sub, _fname, CLASS_COL = _SOURCES[RISK_SOURCE]
RISK_GPKG = os.path.join(OUT_DIR, "outputs", _sub, _fname.format(region=REGION))
PRODUCT_DIR = os.path.join(OUT_DIR, "outputs", f"cost_penalty_{RISK_SOURCE}")
RISK_LAYER = "risk_classes"
COST_TIF = region_input(REGION, "cost_tif")
RISK_MULTIPLIER = {"none": 1.0, "low": 1.1, "medium": 1.3, "high": 1.5}

# Keep routes inside the region. With True, cost cells outside the risk
# coverage are written as nodata, so the router cannot path through them and no
# line can leave the TVA region. With False they keep their original cost and a
# route may bulge outside, where no penalty applies at all.
EXCLUDE_OUTSIDE_REGION = True

# Routes whose endpoints are not both inside the region are dropped. Note this
# is a guard, not a filter that currently bites: the TVA box was derived from
# the bus span padded ~0.25 deg, so every bus is inside it by construction.
ROUTES_CSV = region_input(REGION, "routes_csv")

BLOCK_ROWS = 1024          # rows of 90 m raster processed at a time
TAG = f"{REGION}_cost_risk_penalty"


# ----------------------------------------------------------------------------
def risk_cells(src_crs):
    """TVA risk cells reprojected to the cost raster's CRS, with multipliers."""
    g = gpd.read_file(RISK_GPKG, layer=RISK_LAYER)
    g = g[g["region"] == REGION].reset_index(drop=True)
    if g.empty:
        raise SystemExit(f"no cells for region '{REGION}' in {RISK_GPKG}")
    missing = set(g[CLASS_COL]) - set(RISK_MULTIPLIER)
    if missing:
        raise SystemExit(f"risk_class values with no multiplier: {missing}")
    g["multiplier"] = g[CLASS_COL].map(RISK_MULTIPLIER).astype(float)
    # Normalise the naming for the output, and DERIVE the level rather than
    # copying it from the input: the combined product calls its columns
    # combined_class/combined_level, so depending on a `risk_level` column
    # being present breaks for that source.
    g["risk_class"] = g[CLASS_COL]
    g["risk_level"] = g[CLASS_COL].map(
        {c: i for i, c in enumerate(["none", "low", "medium", "high"])}
    ).astype("int8")
    g = g.to_crs(src_crs)
    print(f"{len(g):,} {REGION} risk cells; class counts "
          + str(g[CLASS_COL].value_counts().to_dict()))
    return g


def cost_window(src, bounds):
    """Integer raster window covering `bounds`, clipped to the raster."""
    minx, miny, maxx, maxy = bounds
    r0, c0 = src.index(minx, maxy, op=np.floor)      # upper-left
    r1, c1 = src.index(maxx, miny, op=np.ceil)       # lower-right
    r0, c0 = max(int(r0), 0), max(int(c0), 0)
    r1, c1 = min(int(r1), src.height), min(int(c1), src.width)
    return Window(c0, r0, c1 - c0, r1 - r0)


def filter_routes(bounds4326):
    """Drop routes with an endpoint outside the region box, write the rest.

    Both endpoints must be inside: a route anchored outside the region would be
    routed on a cost surface that is only penalised inside it."""
    import pandas as pd
    x0, y0, x1, y1 = bounds4326
    d = pd.read_csv(ROUTES_CSV)

    def inside(lon, lat):
        return (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)

    keep = (inside(d["start_lon"], d["start_lat"])
            & inside(d["end_lon"], d["end_lat"]))
    out = os.path.join(PRODUCT_DIR, f"{TAG}_routes_in_region.csv")
    d[keep].to_csv(out, index=False)
    print(f"routes: {len(d):,} in, {int(keep.sum()):,} kept, "
          f"{int((~keep).sum()):,} dropped for an endpoint outside {REGION}")
    if (~keep).any():
        for _, r in d[~keep].head(10).iterrows():
            print(f"    dropped {r['start_BusName']} -> {r['end_BusName']}")
    print(f"  saved -> {out}")


def main():
    os.makedirs(PRODUCT_DIR, exist_ok=True)

    filter_routes(tuple(gpd.read_file(RISK_GPKG, layer=RISK_LAYER)
                        .query(f"region == '{REGION}'").total_bounds))

    with rasterio.open(COST_TIF) as src:
        cells = risk_cells(src.crs)
        mult = cells["multiplier"].to_numpy(dtype="float64")
        n = len(cells)

        win = cost_window(src, tuple(cells.total_bounds))
        w, h = int(win.width), int(win.height)
        print(f"cost window: {w:,} x {h:,} cells at {src.res[0]:.0f} m "
              f"({w*h/1e6:.1f} M cells)")

        nodata = src.nodata
        profile = src.profile.copy()
        profile.update(height=h, width=w, count=1, dtype="float32",
                       transform=src.window_transform(win),
                       compress="deflate", predictor=2, tiled=True,
                       blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")

        # Rasterizing the cell *index* (not the multiplier) lets one pass serve
        # both the output raster and the per-cell zonal statistics.
        shapes = list(zip(cells.geometry, np.arange(n, dtype="int32")))

        cnt = np.zeros(n, dtype="int64")
        s_cost = np.zeros(n, dtype="float64")
        s_adj = np.zeros(n, dtype="float64")
        uncovered = 0

        out_path = os.path.join(PRODUCT_DIR, f"{TAG}_90m.tif")
        with rasterio.open(out_path, "w", **profile) as dst:
            for r0 in range(0, h, BLOCK_ROWS):
                nr = min(BLOCK_ROWS, h - r0)
                blk = Window(win.col_off, win.row_off + r0, w, nr)
                tr = src.window_transform(blk)

                # all_touched=True matters: the risk cells are squares in
                # EPSG:4326, so reprojecting them to 5070 leaves hairline slivers
                # between neighbours that a centre-in-polygon test drops. Those
                # dropped pixels would keep the x1.0 base cost and form cheap
                # corridors along cell boundaries -- precisely what a least-cost
                # router hunts for. Touching pixels are claimed instead; at a
                # boundary the later cell wins, which is arbitrary but harmless
                # when neighbours differ by one class step.
                idx = rasterize(shapes, out_shape=(nr, w), transform=tr,
                                fill=-1, dtype="int32", all_touched=True)
                cost = src.read(1, window=blk).astype("float32")

                m = np.ones((nr, w), dtype="float32")
                covered = idx >= 0
                m[covered] = mult[idx[covered]]
                adj = cost * m

                good = covered
                if nodata is not None:
                    nod = cost == nodata
                    adj[nod] = nodata          # nodata passes through untouched
                    good = covered & ~nod
                    if EXCLUDE_OUTSIDE_REGION:
                        # Outside the region there is no risk class, so a route
                        # there would pay no penalty. Make it impassable rather
                        # than free of penalty.
                        adj[~covered] = nodata
                uncovered += int((~covered).sum())

                dst.write(adj, 1, window=Window(0, r0, w, nr))

                gi = idx[good]
                cnt += np.bincount(gi, minlength=n)
                s_cost += np.bincount(gi, weights=cost[good].astype("float64"),
                                      minlength=n)
                s_adj += np.bincount(gi, weights=adj[good].astype("float64"),
                                     minlength=n)
                print(f"  rows {r0:,}-{r0+nr:,} of {h:,}", end="\r")

        print(f"\n  saved -> {out_path}")
        if uncovered:
            what = ("written as nodata, impassable" if EXCLUDE_OUTSIDE_REGION
                    else "left at x1.0, passable but unpenalised")
            print(f"  ({uncovered:,} cells outside the region -- {what})")

    # ------------------------------------------------------------------ gpkg
    with np.errstate(invalid="ignore", divide="ignore"):
        cells["n_cost_cells"] = cnt
        cells["cost_sum"] = s_cost
        cells["adj_cost_sum"] = s_adj
        cells["cost_mean"] = np.where(cnt > 0, s_cost / np.maximum(cnt, 1),
                                      np.nan)
        cells["adj_cost_mean"] = np.where(cnt > 0, s_adj / np.maximum(cnt, 1),
                                          np.nan)
    cells["added_cost"] = cells["adj_cost_sum"] - cells["cost_sum"]

    keep = ["region", "risk_class", "risk_level", "multiplier", "n_cost_cells",
            "cost_mean", "cost_sum", "adj_cost_mean", "adj_cost_sum",
            "added_cost", "geometry"]
    out_gpkg = os.path.join(PRODUCT_DIR, f"{TAG}_cells.gpkg")
    cells[keep].to_file(out_gpkg, layer="risk_cost", driver="GPKG")
    print(f"  saved -> {out_gpkg}")

    # ---------------------------------------------------------------- report
    tot, tot_adj = s_cost.sum(), s_adj.sum()
    print(f"\nregion-wide cost {tot:.4g} -> {tot_adj:.4g} "
          f"({100*(tot_adj/tot - 1):.2f}% higher if a line were drawn "
          f"through every cell equally)")
    print(f"{'class':8s} {'cells':>8s} {'mult':>5s} {'% of cost cells':>16s}")
    for cls in RISK_MULTIPLIER:
        m = cells["risk_class"] == cls
        if m.any():
            print(f"{cls:8s} {int(m.sum()):8,d} "
                  f"{RISK_MULTIPLIER[cls]:5.2f} "
                  f"{100*cnt[m.to_numpy()].sum()/max(cnt.sum(),1):15.1f}%")


if __name__ == "__main__":
    main()
