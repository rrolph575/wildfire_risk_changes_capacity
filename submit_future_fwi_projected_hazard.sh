#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --time=0-04:00:00   # run should be ~15-35 min; 4h is headroom
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=64000         # MB. Peak is ~2.5 GB/block + h5py cache; 64 GB is
                            # generous. Raise CELLS_PER_BLOCK to trade RAM for
                            # fewer, larger reads.
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=END,FAIL
#SBATCH --job-name=fwi_future_hazard
#SBATCH --output=logs/slurm-%j.out

# Projected fire-weather hazard from the future (2025-2059) Sup3rCC ssp245 FWI.
#
# Reads ~118 GB of fwi_tc (35 yearly files x ~3.4 GB) streaming over spatial
# blocks, and writes ONE npz with both future fields:
#   * fut_pct_maps        -- future p90/p95/p98 FWI values per cell
#   * days_per_year_maps  -- days/yr above each fixed absolute FWI threshold
#
# Needs the `sup3r` env (h5py + access to /datasets/sup3rcc), NOT `rev`.
# The follow-on mapping step runs in `rev` and is fast.
#
# NOTE: the absolute thresholds are hardcoded in the script from the current
# risk classes (abs_risk_hist_p98_risk_classes.gpkg cut_* columns). If those
# classes are regenerated, update ABS_THRESHOLDS before submitting.
#
# Submit with:  sbatch submit_future_fwi_projected_hazard.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate sup3r
python future_fwi_projected_hazard.py
