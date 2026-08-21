#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --partition=debug     # debug caps walltime at 1h; run should be ~5-15 min
#SBATCH --time=0-01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=32000           # MB. Peak is one 2048-row block (~100 MB) plus
                              # the rasterised index; 32 GB is generous.
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=END,FAIL
#SBATCH --job-name=lf_fuel_comp
#SBATCH --output=logs/slurm-%j.out

# Fuel composition per risk cell from LANDFIRE 2024 FBFM40 (30 m, EPSG:5070).
#
# Streams a ~24,800 x 18,900 window (468 M pixels, ~940 MB) over the TVA risk
# cells and tallies, for each ~2.8 km cell, the fraction in each Scott & Burgan
# fuel family plus the non-burnable split (urban / water / agriculture).
#
# This produces COMPOSITION ONLY. Turning it into a low/medium/high fuel axis,
# and combining that with the fire-weather classes, is a separate step taken
# after these numbers can be inspected.
#
# INPUT the raster must already be extracted to /scratch/$USER/landfire/ from
#   /scratch/gbuster/transfer/LF2024_FBFM40_CONUS.zip
# (already done; nothing is ever written back to that transfer folder).
#
# Submit with:  sbatch submit_landfire_fuel_composition.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate rev
python landfire_fuel_composition.py
