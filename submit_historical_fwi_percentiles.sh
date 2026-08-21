#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --partition=debug   # debug caps walltime at 1h; run should be ~6-10 min
#SBATCH --time=0-01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=32000         # MB. Peak is ~1.1 GB/block; 32 GB is generous.
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=END,FAIL
#SBATCH --job-name=fwi_hist_pct
#SBATCH --output=logs/slurm-%j.out

# Historical (2000-2014) FWI percentile values per cell -- the field the risk
# classes are built on. Replaces reading `pct_maps` out of the upstream
# fwi_tc_AminusB_*.npz, which also computed the retired A/B trend metric and so
# had to read the future run as well.
#
# Reads ~97 GB across 15 files, streaming over spatial blocks. Writes ONLY to
# this project (outputs/risk_historical/); nothing goes to /projects/rev/.
#
# Submit with:  sbatch submit_historical_fwi_percentiles.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate sup3r
python historical_fwi_percentiles.py
