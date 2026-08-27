"""
Per-region routing inputs, in one place so the cost and route scripts agree.

Both transmission_cost_risk_penalty.py and route_risk_cost_analysis.py need the
same three upstream files, and both previously hardcoded the TVA paths. Holding
them here means adding a region is one edit, not two that can drift apart.

    cost_tif     the unpenalised least-cost-path cost surface (90 m, EPSG:5070)
    routes_csv   route endpoints, used to drop routes leaving the region
    routes_gpkg  the routed LineStrings, re-costed by route_risk_cost_analysis

SOCAL IS NOT WIRED UP YET -- deliberately left as None rather than guessed.
The TVA cost surface is a TVA routing product: it carries values over SoCal but
was never built or validated for that region, so pointing SoCal at it would
produce numbers that look plausible and mean nothing. When the SoCal products
arrive from the transmission team, fill the three paths in below and both
scripts work with no further changes.
"""

_REV = "/kfs2/projects/rev/projects/sienna_transmission"

REGION_INPUTS = {
    "tva": {
        "cost_tif":    f"{_REV}/tva_lcp/tva_lcp_default_agg_costs.tif",
        "routes_csv":  f"{_REV}/tva_lcp/tva_routes.csv",
        "routes_gpkg": f"{_REV}/tva_lcp/tva_lcp_route_points.gpkg",
    },
    "socal": {
        "cost_tif":    None,   # PENDING -- see module docstring
        "routes_csv":  None,   # PENDING
        "routes_gpkg": None,   # PENDING
    },
}


def region_input(region, key):
    """One input path, or a clear explanation of what is missing.

    Fails loudly and specifically rather than letting a None reach rasterio as
    an unreadable path -- the resulting error would name a file, not the reason
    the file is absent."""
    if region not in REGION_INPUTS:
        raise SystemExit(f"unknown REGION {region!r}; "
                         f"expected one of {sorted(REGION_INPUTS)}")
    path = REGION_INPUTS[region].get(key)
    if path is None:
        raise SystemExit(
            f"REGION={region} has no '{key}' yet.\n"
            f"  The {region} routing products have not been supplied. Add the "
            f"path to REGION_INPUTS in region_inputs.py once they arrive.\n"
            f"  Do NOT substitute the TVA cost surface: it covers the SoCal "
            f"extent but was not built for it, so the numbers would be "
            f"meaningless rather than absent.")
    return path
