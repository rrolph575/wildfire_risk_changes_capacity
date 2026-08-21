"""
Fuel composition per risk cell, from LANDFIRE 2024 FBFM40.

Step 1 of bringing fuel into the wildfire risk zones. Produces WHAT IS THERE,
not a risk class -- the classing decision comes afterwards, once these numbers
can be looked at.

WHY FUEL
    FWI is a fire WEATHER index with no fuel term. Across TVA the two run in
    opposite directions: fire weather worsens westward, fuel increases eastward.
    Measured on the WHP hazard layer, rank correlation with longitude was -0.52
    for fire weather and +0.21 for fuel, and the two were near-independent of
    each other (-0.04). So the fire-weather-only map understates the forested
    eastern plateau. LANDFIRE gives fuel directly, rather than WHP's composite
    of fuel + weather + ignition (which would partly double-count weather).

WHAT IT COMPUTES
    Each ~2.8 km risk cell contains roughly 8,700 LANDFIRE pixels at 30 m, so a
    single "the fuel model here" would throw most of that away. Instead this
    tallies the full composition: the fraction of each risk cell in each Scott &
    Burgan fuel family.

        NB  non-burnable   91 urban, 92 snow/ice, 93 agriculture,
                           98 water, 99 barren
        GR  grass                101-109
        GS  grass-shrub          121-124
        SH  shrub                141-149
        TU  timber-understory    161-165
        TL  timber litter        181-189
        SB  slash-blowdown       201-204

    Families are the published Scott & Burgan (2005) groupings -- no invented
    ordering of individual models. Turning composition into a low/medium/high
    fuel axis is a separate, deliberate step.

    NB also replaces WHP entirely: it identifies non-burnable ground with a
    REASON attached (water vs urban vs agriculture), where WHP gave only 0.

NOTE ON EXTENT
    LANDFIRE covers CONUS land; the raster's nodata defines the coastline, the
    same role WHP's nodata plays in the existing land mask. Cells with no valid
    LANDFIRE pixels are written as NaN and should be treated as not-land.

Run as a batch job (reads ~940 MB over a 468 M-cell window):
    sbatch submit_landfire_fuel_composition.sh

Outputs (to outputs/risk_future_with_fuel/):
  * tva_fuel_composition.gpkg -- layer "fuel_composition", one polygon per risk
        cell with: region, n_lf_pixels, frac_nonburnable, frac_GR, frac_GS,
        frac_SH, frac_TU, frac_TL, frac_SB, frac_burnable, dominant_family,
        and the non-burnable split frac_nb_urban / _water / _agriculture.
"""

import os

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.windows import Window
from rasterio.features import rasterize

PROJ = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
RISK_GPKG = os.path.join(PROJ, "outputs", "risk_future",
                         "abs_risk_future_p98_risk_classes.gpkg")
RISK_LAYER = "risk_classes"
LANDFIRE = os.path.expandvars(
    "/scratch/$USER/landfire/LF2024_FBFM40_CONUS.tif")
PRODUCT_DIR = os.path.join(PROJ, "outputs", "risk_future_with_fuel")
REGION = "tva"
BLOCK_ROWS = 2048

# Scott & Burgan 40 families, by code range.
FAMILIES = {
    "GR": range(101, 110), "GS": range(121, 125), "SH": range(141, 150),
    "TU": range(161, 166), "TL": range(181, 190), "SB": range(201, 205),
}
NONBURN = {91: "urban", 92: "snow_ice", 93: "agriculture",
           98: "water", 99: "barren"}
NODATA_CODES = {-9999, 32767}


def family_lookup():
    """Flat LUT array: code -> family index (-1 = not a fuel code).

    An array indexed by the raw code, not a dict: the alternative is 45
    full-array comparisons per block (`fam[gf == code] = fi`), which over
    ~47 M pixels x 10 blocks is billions of needless comparisons. Codes top out
    at 204, so a 256-slot table covers them and `LUT[gf]` resolves the whole
    block in one fancy-index."""
    names = list(FAMILIES) + ["NB"]
    lut = np.full(256, -1, dtype=np.int16)
    for i, fam in enumerate(FAMILIES):
        for c in FAMILIES[fam]:
            lut[c] = i
    for c in NONBURN:
        lut[c] = len(FAMILIES)          # all non-burnable share one slot
    # second table for the non-burnable reason split, same trick
    nb_lut = np.full(256, -1, dtype=np.int16)
    for j, c in enumerate(NONBURN):
        nb_lut[c] = j
    return lut, nb_lut, names


def main():
    os.makedirs(PRODUCT_DIR, exist_ok=True)
    lut, nb_lut, fam_names = family_lookup()
    n_fam = len(fam_names)

    cells = gpd.read_file(RISK_GPKG, layer=RISK_LAYER)
    cells = cells[cells["region"] == REGION].reset_index(drop=True)
    n = len(cells)
    print(f"{n:,} {REGION} risk cells")

    with rasterio.open(LANDFIRE) as src:
        cells_p = cells.to_crs(src.crs)
        minx, miny, maxx, maxy = cells_p.total_bounds
        r0, c0 = src.index(minx, maxy, op=np.floor)
        r1, c1 = src.index(maxx, miny, op=np.ceil)
        r0, c0 = max(int(r0), 0), max(int(c0), 0)
        r1, c1 = min(int(r1), src.height), min(int(c1), src.width)
        W, H = c1 - c0, r1 - r0
        print(f"LANDFIRE window {W:,} x {H:,} at 30 m ({W*H/1e6:.0f} M pixels)")

        shapes = list(zip(cells_p.geometry, np.arange(n, dtype="int32")))
        # counts[cell, family] and a separate tally of the non-burnable reasons
        counts = np.zeros((n, n_fam), dtype="int64")
        nb_counts = np.zeros((n, len(NONBURN)), dtype="int64")
        nb_codes = list(NONBURN)

        for br in range(0, H, BLOCK_ROWS):
            nr = min(BLOCK_ROWS, H - br)
            blk = Window(c0, r0 + br, W, nr)
            tr = src.window_transform(blk)
            idx = rasterize(shapes, out_shape=(nr, W), transform=tr,
                            fill=-1, dtype="int32", all_touched=True)
            fuel = src.read(1, window=blk)

            m = idx >= 0
            for c in NODATA_CODES:                    # drop fill / nodata
                m &= fuel != c
            m &= (fuel >= 0) & (fuel < 256)           # keep the LUT in range
            gi, gf = idx[m], fuel[m]

            # np.bincount on a flattened (cell, family) index rather than
            # np.add.at, which is unbuffered and an order of magnitude slower.
            fam = lut[gf]
            ok = fam >= 0
            counts += np.bincount(gi[ok] * n_fam + fam[ok],
                                  minlength=n * n_fam).reshape(n, n_fam)

            nbf = nb_lut[gf]
            ok = nbf >= 0
            nb_counts += np.bincount(gi[ok] * len(NONBURN) + nbf[ok],
                                     minlength=n * len(NONBURN)
                                     ).reshape(n, len(NONBURN))

            print(f"  rows {br:,}-{br+nr:,} of {H:,}", flush=True)

    tot = counts.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = counts / np.maximum(tot, 1)[:, None]
    frac[tot == 0] = np.nan

    # Deliberately NOT carrying risk_class/risk_level: fuel composition is a
    # property of the ground, independent of fire weather, so the output stays
    # valid across an FWI rebuild. lon/lat are the join key back to whichever
    # risk classes are current at combine time.
    out = cells[["region", "lon", "lat"]].copy()
    out["n_lf_pixels"] = tot
    for i, fam in enumerate(fam_names):
        out[f"frac_{'nonburnable' if fam == 'NB' else fam}"] = frac[:, i]
    out["frac_burnable"] = 1.0 - out["frac_nonburnable"]
    for j, code in enumerate(nb_codes):
        out[f"frac_nb_{NONBURN[code]}"] = np.where(
            tot > 0, nb_counts[:, j] / np.maximum(tot, 1), np.nan)
    burn_only = np.where(np.isnan(frac[:, :-1]), -1, frac[:, :-1])
    out["dominant_family"] = [fam_names[i] if t > 0 else None
                              for i, t in zip(burn_only.argmax(axis=1), tot)]

    gdf = gpd.GeoDataFrame(out, geometry=cells.geometry.values, crs=cells.crs)
    dst = os.path.join(PRODUCT_DIR, "tva_fuel_composition.gpkg")
    gdf.to_file(dst, layer="fuel_composition", driver="GPKG")
    print(f"\n  saved -> {dst}")

    print(f"\nmean composition over {REGION} risk cells:")
    for fam in fam_names:
        col = f"frac_{'nonburnable' if fam == 'NB' else fam}"
        print(f"  {col:22s} {100*out[col].mean():5.1f}%")
    print("\nnon-burnable breakdown:")
    for code in nb_codes:
        print(f"  {NONBURN[code]:14s} {100*out[f'frac_nb_{NONBURN[code]}'].mean():5.1f}%")
    print("\ndominant family, cell counts:")
    print(out["dominant_family"].value_counts().to_string())
    print(f"\ncells with no LANDFIRE pixels (not land): "
          f"{int((tot == 0).sum()):,}")


if __name__ == "__main__":
    main()
