"""
!!! PROTOTYPE -- NOT THE SHIPPED METHOD. Kept as the record of an
    alternative that was built, scored, and DECLINED on 2026-08-28.

    The change-based axis scored better against MTBS (2.38x TVA /
    2.37x SoCal with fuel, vs 0.86x / 0.99x shipped) but that gain
    could not be separated from a land-cover confound: "low
    historical FWI" alone scores 2.57x / 1.80x, because low FWI
    marks moist forested ground. Anything inversely correlated with
    FWI inherits skill for free, and delta_rel correlates -0.670
    with historical FWI in TVA.

    Decision: keep the LEVEL-based method; frame the product as
    fire-weather severity and its projected change. See
    documentation_and_summaries/summary_of_validation_against_observed_fires.md
"""

"""
PROTOTYPE: classify cells by how much fire weather WORSENS, not how severe it is.

The existing products class each cell by its p98 FWI *level*. Validation against
MTBS showed that level is ANTI-predictive of where fires actually burn (lift
0.25x TVA / 0.42x SoCal) -- see summary_of_validation_against_observed_fires.md.

But the *change* in that same field is PREDICTIVE (1.81x / 1.36x), and the
change is also literally the research question: how does climate change alter
fire risk. This script builds that third product so the two can be compared on
equal terms. It does not replace anything.

    delta_abs = future_p98_fwi - hist_p98_fwi          (FWI units)
    delta_rel = 100 * delta_abs / hist_p98_fwi         (percent)

Both are produced. `delta_rel` scored better in testing but has a denominator
artifact -- a cell with a low historical base shows a large percentage for a
small absolute change -- so `delta_abs` is the conservative choice and the
comparison is left explicit rather than decided here.

Classed with the SAME region-relative 50/75/90 machinery as the level products,
so the only thing that changes is WHICH field is being classed. Fuel then
modifies it through the same 12-entry matrix.

WHY NO BATCH JOB
    Both p98 fields already exist per-cell in the risk GeoPackages. The 97 GB +
    118 GB Sup3rCC reads that produced them are done. This is arithmetic on
    63,132 rows.

Run in the `rev` conda env (~20 s):
    conda activate rev
    python delta_fwi_risk.py

Outputs (to outputs/risk_future_delta/):
  * abs_risk_delta_p98_risk_classes.gpkg -- both regions, layer "risk_classes",
        with delta_abs, delta_rel, and a class column for each.
"""

import os

import numpy as np
import pandas as pd
import geopandas as gpd

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
HIST = os.path.join(PROJ, "outputs", "risk_historical",
                    "abs_risk_hist_p98_risk_classes.gpkg")
FUT = os.path.join(PROJ, "outputs", "risk_future",
                   "abs_risk_future_p98_risk_classes.gpkg")
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_delta")
CLASS_ORDER = ["none", "low", "medium", "high"]
CLASS_QUANTILES = {"low": 50, "medium": 75, "high": 90}


def classify(values, region_mask):
    """none/low/medium/high from within-region percentiles of `values`.

    Same construction as regional_absolute_risk_maps: cutoffs are the 50th,
    75th and 90th percentile CELL within the region, so each region is ranked
    against itself and the shares are 50/25/15/10 by design."""
    out = np.zeros(len(values), dtype="int8")
    cuts = {}
    for reg in np.unique(region_mask):
        m = region_mask == reg
        v = values[m]
        c = {k: float(np.percentile(v, q)) for k, q in CLASS_QUANTILES.items()}
        cuts[reg] = c
        lev = np.zeros(m.sum(), dtype="int8")
        for i, name in enumerate(CLASS_ORDER[1:], start=1):
            lev[v >= c[name]] = i
        out[m] = lev
    return out, cuts


def main():
    os.makedirs(PRODUCT_DIR, exist_ok=True)
    h = gpd.read_file(HIST, layer="risk_classes")
    f = gpd.read_file(FUT, layer="risk_classes")
    d = h[["region", "lon", "lat", "hist_p98_fwi", "whp_burnable",
           "geometry"]].merge(
        f[["region", "lon", "lat", "future_p98_fwi"]],
        on=["region", "lon", "lat"], how="inner", validate="one_to_one")
    if len(d) != len(h):
        raise SystemExit(f"join lost cells: {len(h)} -> {len(d)}")

    d["delta_abs"] = d.future_p98_fwi - d.hist_p98_fwi
    d["delta_rel"] = 100.0 * d.delta_abs / d.hist_p98_fwi

    reg = d.region.to_numpy()
    for field in ("delta_abs", "delta_rel"):
        lev, cuts = classify(d[field].to_numpy(), reg)
        d[f"{field}_level"] = lev
        d[f"{field}_class"] = [CLASS_ORDER[i] for i in lev]
        print(f"\n{field} cutoffs (50/75/90th percentile cell):")
        for r, c in cuts.items():
            print(f"  {r:6s} low>={c['low']:8.3f}  medium>={c['medium']:8.3f}"
                  f"  high>={c['high']:8.3f}")

    out = os.path.join(PRODUCT_DIR, "abs_risk_delta_p98_risk_classes.gpkg")
    gpd.GeoDataFrame(d, crs=h.crs).to_file(out, layer="risk_classes",
                                           driver="GPKG")
    print(f"\n  saved -> {out}")
    for r in d.region.unique():
        s = d[d.region == r]
        print(f"  {r}: {len(s):,} cells | mean delta_abs {s.delta_abs.mean():+.2f} FWI"
              f" | mean delta_rel {s.delta_rel.mean():+.1f}%")


if __name__ == "__main__":
    main()
