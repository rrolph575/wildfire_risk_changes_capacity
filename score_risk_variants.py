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
Score every candidate risk formulation against observed fires (MTBS).

Compares, on identical footing, the products built from the FWI *level* (what
is shipped) against those built from the FWI *change* (the prototype in
delta_fwi_risk.py), each alone and each combined with fuel through the existing
+/-1 matrix.

METRIC -- "lift" = mean class of burned cells / mean class of unburned cells.
    >1  the layer marks burned ground as riskier than average  (useful)
    =1  no discrimination
    <1  the layer marks burned ground as SAFER than average    (inverted)

Lift is a ratio of means, so it is only comparable BETWEEN ROWS ON THE SAME
SCALE. Every row here is on the same 0-3 class scale for that reason; the
continuous indices are deliberately not mixed in.

Caveats that belong with any number this prints: MTBS covers fires >=500 acres
(>=1000 in the West), so this is significant fires, not all ignitions; fire
occurrence is not the same as risk to a transmission line, which also depends
on consequence; and Sup3rCC is GCM-driven, so this tests climatology, never an
individual fire.

Run in the `rev` conda env (~30 s):
    conda activate rev
    python score_risk_variants.py
"""

import os

import numpy as np
import pandas as pd
import geopandas as gpd

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
CLASS_ORDER = ["none", "low", "medium", "high"]
LV = {c: i for i, c in enumerate(CLASS_ORDER)}
FUEL_SHIFT = {"low": -1, "medium": 0, "high": +1}


def burned_mask(d, fires):
    """Cells overlapping any wildfire. bbox prefilter then exact intersect --
    the `rev` env has no spatial index."""
    lon, lat = d.lon.to_numpy(), d.lat.to_numpy()
    m = np.zeros(len(d), bool)
    for g, (x0, y0, x1, y1) in zip(fires.geometry,
                                   fires.geometry.bounds.to_numpy()):
        for i in np.where((lon > x0-.03) & (lon < x1+.03) &
                          (lat > y0-.03) & (lat < y1+.03))[0]:
            if not m[i] and d.geometry.iloc[i].intersects(g):
                m[i] = True
    return m


def combine(base_level, fuel_class, gate):
    """The shipped 12-entry matrix: fuel shifts the base class +/-1, clipped,
    then the non-burnable gate forces `none`."""
    shift = np.array([FUEL_SHIFT[c] for c in fuel_class])
    out = np.clip(base_level + shift, 0, 3)
    out[gate] = 0
    return out


def main():
    rows = []
    for region in ("tva", "socal"):
        cur = gpd.read_file(os.path.join(
            PROJ, "outputs", "risk_future_with_fuel",
            f"abs_risk_future_fuel_{region}_risk_classes.gpkg"))
        dl = gpd.read_file(os.path.join(
            PROJ, "outputs", "risk_future_delta",
            "abs_risk_delta_p98_risk_classes.gpkg"))
        dl = dl[dl.region == region]
        d = cur.merge(dl[["lon", "lat", "delta_abs_level", "delta_rel_level",
                          "delta_abs", "delta_rel"]],
                      on=["lon", "lat"], how="inner", validate="one_to_one")
        if len(d) != len(cur):
            raise SystemExit(f"{region}: join lost cells {len(cur)} -> {len(d)}")

        fires = gpd.read_file(os.path.join(
            PROJ, "data", "fire_perimeters",
            f"{region}_mtbs_wildfires.gpkg")).to_crs(4326)
        b = burned_mask(d, fires)
        gate = (d.nonburnable_gated.to_numpy() == 1)
        fuel_cls = d.fuel_class.to_numpy()

        lvl = np.array([LV[c] for c in d.risk_class])
        variants = {
            "FWI level (shipped)": lvl,
            "FWI level + fuel (shipped)": np.array([LV[c] for c in d.combined_class]),
            "FWI delta_abs": d.delta_abs_level.to_numpy(),
            "FWI delta_abs + fuel": combine(d.delta_abs_level.to_numpy(), fuel_cls, gate),
            "FWI delta_rel": d.delta_rel_level.to_numpy(),
            "FWI delta_rel + fuel": combine(d.delta_rel_level.to_numpy(), fuel_cls, gate),
        }
        for name, v in variants.items():
            v = np.asarray(v, dtype="float64")
            rows.append({"region": region, "variant": name,
                         "burned": v[b].mean(), "unburned": v[~b].mean(),
                         "lift": v[b].mean() / max(v[~b].mean(), 1e-9),
                         "pct_burned_med_high": 100*(v[b] >= 2).mean()})
        print(f"  {region}: {b.sum():,}/{len(d):,} cells burned "
              f"({len(fires):,} wildfires)")

    t = pd.DataFrame(rows)
    print()
    piv = t.pivot(index="variant", columns="region", values="lift")
    piv = piv.reindex([v for v in t.variant.unique()])
    print("LIFT  (>1 = marks burned ground riskier; <1 = marks it safer)")
    print(piv.to_string(float_format="%.2fx"))
    print()
    piv2 = t.pivot(index="variant", columns="region",
                   values="pct_burned_med_high").reindex(piv.index)
    print("% of BURNED cells classed medium or high")
    print(piv2.to_string(float_format="%.0f%%"))


if __name__ == "__main__":
    main()
