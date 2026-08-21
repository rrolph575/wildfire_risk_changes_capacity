"""
Projected fire-weather hazard from the future (2025-2059) Sup3rCC FWI run.

Produces the two future fields the absolute-risk method needs and that the
existing NPZ cannot supply. Both are computed in a single streaming pass over
the ssp245 daily data, because reading that data is the expensive part.

  1. FUTURE PERCENTILE VALUES -- `fut_pct_maps`
     Each cell's p90/p95/p98 FWI over 2025-2059, in FWI units. This is the
     direct future analogue of the historical `pct_maps` the current risk
     classes are built on, so the two can be compared like with like: same
     quantity, same units, different period.

  2. DAYS PER YEAR ABOVE FIXED ABSOLUTE THRESHOLDS -- `days_per_year_maps`
     For each cell, the mean number of days per year in 2025-2059 with FWI
     above each fixed value in ABS_THRESHOLDS.

WHY A FIXED THRESHOLD, NOT A PER-CELL ONE
    The retired `A` metric counted future days above *each cell's own*
    historical p98. That makes the historical count ~7.3 days/yr everywhere by
    construction (2% of 365), so the future count could only express how much a
    cell had CHANGED -- a trend metric. In these regions it carried no
    information about absolute severity (corr with historical p98 was +0.005 in
    SoCal and -0.487 in TVA, i.e. backwards).

    Counting against ONE fixed FWI value for every cell removes that. A mild
    cell rarely reaches the bar and scores low; a severe cell clears it often
    and scores high. The historical counts vary across space instead of being
    pinned at 7.3 -- which is exactly the information the per-cell version
    destroys. The result is an absolute severity measure that also carries the
    climate projection, in units that read well: "days per year of high-risk
    fire weather, 2025-2059".

WHAT THIS IS NOT
    Fire WEATHER only. FWI has no fuel term, so it cannot see that the eastern
    TVA plateau carries far more fuel than the agricultural west. Combining
    with a fuel-aware layer (USFS WHP, or LANDFIRE) is a separate step, and
    note WHP is a present-day product being paired with a future weather field.

EFFICIENCY
    ~118 GB of fwi_tc to read (35 files x ~3.4 GB), so it cannot be held in
    memory. The HDF5 datasets are chunked (full_time, 800 cells), so "all days
    for a block of columns" is a chunk-aligned read. We stream over spatial
    blocks of 48,000 cells, holding every future day for that block (~2.5 GB),
    and compute both outputs from it before moving on. Each byte is read once.
    Pattern follows /home/rrolph/wildfire/fwi_percentile_maps.py.

Run on a compute node in the `sup3r` conda env:
    sbatch submit_future_fwi_projected_hazard.sh

Outputs (to OUT_DIR):
  * fwi_tc_future2025_2059_projected_hazard.npz -- keys: lat, lon, percentiles,
        fut_pct_maps (n_pct, n_cells), abs_thresholds, abs_threshold_labels,
        days_per_year_maps (n_thr, n_cells), n_future_years, future_window,
        variable.
"""

import glob
import os
import warnings

import h5py
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
VARIABLE = "fwi_tc"                # trend-corrected FWI, matching the rest of
                                   # this project (humidity-trend corrected;
                                   # NOT temperature corrected)

FUTURE_GLOB = ("/datasets/sup3rcc/conus_ecearth3veg_ssp245_r1i1p1f1/"
               "v0.2.2/daily/*fwi*.h5")
YEAR_MIN = 2025                    # ssp245 spans 2015-2059; count from here

PERCENTILES = [90, 95, 98]         # future percentile VALUES to compute

# Fixed absolute FWI cutoffs to count future exceedance days against. These are
# the regional class boundaries from the current risk classes -- the 50th/75th/
# 90th-percentile land cell of each region -- taken at FULL PRECISION from the
# cut_low / cut_medium / cut_high columns of
# outputs/risk_historical/abs_risk_hist_p98_risk_classes.gpkg.
#
# Full precision matters: an earlier version rounded these to 1 dp, so days/yr
# were counted against 40.8 while cells were classed against 40.798705. The gap
# was immaterial (<0.04 FWI) but it made two products silently disagree.
#
# REGENERATE THOSE CLASSES => UPDATE THESE NUMBERS.
# Last synced 2026-08-18 against the 2026-08-05 fwi_tc re-release.
ABS_THRESHOLDS = {
    "tva_low": 35.134499, "tva_medium": 38.780228, "tva_high": 40.775414,
    "socal_low": 98.709900, "socal_medium": 111.765953, "socal_high": 125.249133,
}

# Multiple of the 800-cell HDF5 chunk width. 48,000 cells x ~12,810 days
# x float32 ~= 2.5 GB resident per block.
CELLS_PER_BLOCK = 800 * 60

OUT_DIR = ("/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
           "/outputs/risk_future")
TAG = f"{VARIABLE}_future{YEAR_MIN}_2059_projected_hazard"


def _file_year(f):
    return int(os.path.basename(f).split("_")[-1].split(".")[0])


# ----------------------------------------------------------------------------
def compute():
    files = sorted(glob.glob(FUTURE_GLOB))
    if not files:
        raise FileNotFoundError(f"No files match {FUTURE_GLOB}")
    files = [f for f in files if _file_year(f) >= YEAR_MIN]
    if not files:
        raise FileNotFoundError(f"No files at/after {YEAR_MIN}")

    labels = list(ABS_THRESHOLDS)
    thr = np.asarray([ABS_THRESHOLDS[k] for k in labels], dtype=np.float32)
    pctiles = np.asarray(PERCENTILES, dtype=float)
    n_p, n_t = len(pctiles), len(thr)

    handles = [h5py.File(f, "r") for f in files]
    try:
        dsets = [h[VARIABLE] for h in handles]
        ndays = [d.shape[0] for d in dsets]
        total_days = int(np.sum(ndays))
        n_cells = dsets[0].shape[1]
        n_years = len(files)
        years = [_file_year(f) for f in files]
        print(f"{n_cells:,} grid cells, variable '{VARIABLE}'")
        print(f"{n_years} future years ({years[0]}-{years[-1]}), "
              f"{total_days:,} days total")
        print(f"percentiles {PERCENTILES}; "
              f"{n_t} absolute thresholds {dict(ABS_THRESHOLDS)}")

        meta = pd.DataFrame(handles[0]["meta"][:])
        lat = meta["latitude"].to_numpy(dtype=np.float32)
        lon = meta["longitude"].to_numpy(dtype=np.float32)

        fut_pct_maps = np.full((n_p, n_cells), np.nan, dtype=np.float32)
        days_per_year_maps = np.full((n_t, n_cells), np.nan, dtype=np.float32)

        starts = list(range(0, n_cells, CELLS_PER_BLOCK))
        for bi, c0 in enumerate(starts):
            c1 = min(c0 + CELLS_PER_BLOCK, n_cells)
            nc = c1 - c0

            block = np.empty((total_days, nc), dtype=np.float32)
            off = 0
            for d, nd in zip(dsets, ndays):
                block[off:off + nd] = d[:, c0:c1]
                off += nd

            with warnings.catch_warnings():
                # all-NaN columns (ocean) -> NaN, expected
                warnings.simplefilter("ignore", category=RuntimeWarning)
                fut_pct_maps[:, c0:c1] = np.nanpercentile(
                    block, pctiles, axis=0).astype(np.float32)

            # NaN > t is False, so NaN days simply never count as exceedances;
            # cells that are entirely NaN are masked back out below.
            allnan = np.all(np.isnan(block), axis=0)
            for ti in range(n_t):
                cnt = np.sum(block > thr[ti], axis=0).astype(np.float32)
                cnt[allnan] = np.nan
                days_per_year_maps[ti, c0:c1] = cnt / n_years

            del block
            print(f"  block {bi + 1}/{len(starts)} "
                  f"(cells {c0:,}-{c1:,}) done", flush=True)
    finally:
        for h in handles:
            h.close()

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{TAG}.npz")
    np.savez_compressed(
        out,
        lat=lat, lon=lon,
        percentiles=np.asarray(PERCENTILES, dtype=np.float32),
        fut_pct_maps=fut_pct_maps,
        abs_thresholds=thr,
        abs_threshold_labels=np.asarray(labels),
        days_per_year_maps=days_per_year_maps,
        n_future_years=np.int32(n_years),
        future_window=np.asarray([years[0], years[-1]], dtype=np.int32),
        variable=np.asarray(VARIABLE),
    )
    print(f"\n  saved -> {out}")

    finite = np.isfinite(fut_pct_maps[PERCENTILES.index(98)])
    print(f"\nfuture p98 FWI: {finite.sum():,} finite cells, "
          f"range {np.nanmin(fut_pct_maps[PERCENTILES.index(98)]):.1f}-"
          f"{np.nanmax(fut_pct_maps[PERCENTILES.index(98)]):.1f}")
    for ti, k in enumerate(labels):
        v = days_per_year_maps[ti][finite]
        print(f"  days/yr above {k:14s} (FWI {thr[ti]:6.1f}): "
              f"median {np.nanmedian(v):6.1f}, max {np.nanmax(v):6.1f}")


if __name__ == "__main__":
    compute()
