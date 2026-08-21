#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --partition=debug          # debug caps walltime at 1h; run is ~7 min
#SBATCH --time=0-01:00:00   # ~7 min per source; 3 sources ~21 min
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=8000                 # measured peak 1.03 GB; 8 GB is ample
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=FAIL
#SBATCH --job-name=route_risk_cost
#SBATCH --output=logs/slurm-%j.out

# Per-route wildfire cost penalty for the existing TVA least-cost paths.
# Measured on a login node before this script existed: 6 min 48 s, 1.03 GB peak.
# It loads two 6,296 x 8,268 float32 cost windows (~208 MB each) into memory and
# walks 1,509 routes over them, so it is the one step in this project that
# genuinely wants a compute node.
#
# Reads whichever penalty raster RISK_SOURCE selects inside
# route_risk_cost_analysis.py, and writes its outputs alongside it in
# outputs/cost_penalty_<source>/. Currently set to "future".
#
# Depends on that raster existing, so run transmission_cost_risk_penalty.py
# (with the matching RISK_SOURCE) first if it is missing or the risk classes /
# multipliers have changed.
#
# Submit with:  sbatch submit_route_risk_cost_analysis.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate rev

# Sources to re-cost, space separated. Override at submit time with e.g.
#   sbatch --export=ALL,SOURCES="future_with_fuel" submit_route_risk_cost_analysis.sh
for src in ${SOURCES:-historical future future_with_fuel}; do
    echo "===================== RISK_SOURCE = $src ====================="
    RISK_SOURCE=$src python route_risk_cost_analysis.py
    echo
done
