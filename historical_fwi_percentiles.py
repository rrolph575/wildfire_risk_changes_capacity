"""
Historical (2000-2014) FWI percentile values per cell, from the Sup3rCC run.

The historical twin of future_fwi_projected_hazard.py. Produces the field the
risk classes are actually built on -- each cell's p90/p95/p98 FWI value -- and
nothing else.

WHY THIS EXISTS RATHER THAN THE UPSTREAM JOB
    This project used to read `pct_maps` out of
        .../data/fwi/fwi_tc_AminusB_pcthist2000_2014_cnt2025_2059_maps.npz
    which is produced by /home/rrolph/wildfire/fwi_exceedance_change_maps.py.
    That file's headline product is `A - B`, the retired trend metric; we only
    ever read one of its seven arrays, and the name no longer describes what we
    use it for.

    Computing A and B means reading BOTH runs -- 15 historical + 35 future
    files -- for a field that needs only the 15 historical ones. This script
    reads just those, so it is roughly 6-7 min instead of 20-40, writes into
    this project instead of the shared /projects/rev/ directory, and leaves the
    undergrounding project's inputs untouched.

VINTAGE STAMPING
    On 2026-08-05 the Sup3rCC fwi_tc files were re-released under the SAME
    version string (v0.2.2), silently invalidating everything downstream. To
    make that detectable next time, the source filenames and their modification
    times are written into the output as `source_files` / `source_mtimes`.
    Compare them against the files on disk before trusting a derived product.

EFFICIENCY
    ~97 GB across 15 files. The HDF5 datasets are chunked (full_time, 800
    cells), so "all days for a block of columns" is a chunk-aligned read. We
    stream blocks of 48,000 cells, holding every historical day for that block
    (~1.1 GB), and compute the percentiles before moving on.

Run on a compute node in the `sup3r` conda env:
    sbatch submit_historical_fwi_percentiles.sh

Outputs (to OUT_DIR):
  * fwi_tc_hist2000_2014_percentiles.npz -- keys: lat, lon, percentiles,
        pct_maps (n_pct, n_cells), n_hist_years, hist_window, variable,
        source_files, source_mtimes.
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
VARIABLE = "fwi_tc"                # trend-corrected FWI (humidity-trend
                                   # corrected; NOT temperature corrected)

HIST_GLOB = ("/datasets/sup3rcc/conus_ecearth3veg_historical_r1i1p1f1/"
             "v0.2.2/daily/*fwi*.h5")

PERCENTILES = [90, 95, 98]         # percentile VALUES to compute

# Multiple of the 800-cell HDF5 chunk width. 48,000 cells x ~5,478 days
# x float32 ~= 1.1 GB resident per block.
CELLS_PER_BLOCK = 800 * 60

OUT_DIR = ("/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
           "/outputs/risk_historical")
TAG = f"{VARIABLE}_hist2000_2014_percentiles"


def _file_year(f):
    return int(os.path.basename(f).split("_")[-1].split(".")[0])


# ----------------------------------------------------------------------------
def compute():
    files = sorted(glob.glob(HIST_GLOB))
    if not files:
        raise FileNotFoundError(f"No files match {HIST_GLOB}")

    pctiles = np.asarray(PERCENTILES, dtype=float)
    n_p = len(pctiles)

    handles = [h5py.File(f, "r") for f in files]
    try:
        dsets = [h[VARIABLE] for h in handles]
        ndays = [d.shape[0] for d in dsets]
        total_days = int(np.sum(ndays))
        n_cells = dsets[0].shape[1]
        years = [_file_year(f) for f in files]
        print(f"{n_cells:,} grid cells, variable '{VARIABLE}'")
        print(f"{len(files)} historical years ({years[0]}-{years[-1]}), "
              f"{total_days:,} days total")
        print(f"percentiles {PERCENTILES}")

        meta = pd.DataFrame(handles[0]["meta"][:])
        lat = meta["latitude"].to_numpy(dtype=np.float32)
        lon = meta["longitude"].to_numpy(dtype=np.float32)

        pct_maps = np.full((n_p, n_cells), np.nan, dtype=np.float32)

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
                pct_maps[:, c0:c1] = np.nanpercentile(
                    block, pctiles, axis=0).astype(np.float32)

            del block
            print(f"  block {bi + 1}/{len(starts)} "
                  f"(cells {c0:,}-{c1:,}) done", flush=True)
    finally:
        for h in handles:
            h.close()

    # Vintage stamp -- see the docstring. mtimes are epoch seconds.
    src_names = np.asarray([os.path.basename(f) for f in files])
    src_mtimes = np.asarray([os.path.getmtime(f) for f in files], dtype="float64")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{TAG}.npz")
    np.savez_compressed(
        out,
        lat=lat, lon=lon,
        percentiles=np.asarray(PERCENTILES, dtype=np.float32),
        pct_maps=pct_maps,
        n_hist_years=np.int32(len(files)),
        hist_window=np.asarray([years[0], years[-1]], dtype=np.int32),
        variable=np.asarray(VARIABLE),
        source_files=src_names,
        source_mtimes=src_mtimes,
    )
    print(f"\n  saved -> {out}")

    import datetime as _dt
    newest = _dt.datetime.fromtimestamp(src_mtimes.max())
    print(f"  source vintage: newest input mtime {newest:%Y-%m-%d %H:%M}")
    for i, p in enumerate(PERCENTILES):
        v = pct_maps[i][np.isfinite(pct_maps[i])]
        print(f"  p{p}: {v.size:,} finite cells, range {v.min():.1f}-{v.max():.1f}")


if __name__ == "__main__":
    compute()
