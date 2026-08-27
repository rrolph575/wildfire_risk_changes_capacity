#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --partition=debug   # debug caps walltime at 1h; run is ~2 min total
#SBATCH --time=0-01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=16000         # MB. Measured peak 738 MB per run; 16 GB is ample.
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=END,FAIL
#SBATCH --job-name=cost_penalty
#SBATCH --output=logs/slurm-%j.out

# Wildfire-risk cost penalty on the TVA transmission cost surface, built for
# ALL THREE risk products in one job (~49 s each, 52 M cells per pass):
#   historical | future | future_with_fuel
# Running them together keeps the three comparable -- same code, same run.
#
# RISK_SOURCE is read from the environment, so no file editing between runs.
# Each pass writes to outputs/cost_penalty_<source>/ :
#     tva_cost_risk_penalty_90m.tif           the routing input
#     tva_cost_risk_penalty_cells.gpkg        per-risk-cell summary
#     tva_cost_risk_penalty_routes_in_region.csv
#
# Depends on the risk classes in outputs/risk_<source>/ already being current.
#
# Submit with:  sbatch submit_transmission_cost_risk_penalty.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate rev

# Sources to rebuild, space separated. Override at submit time with e.g.
#   sbatch --export=ALL,SOURCES="future_with_fuel" submit_transmission_cost_risk_penalty.sh
# Useful when only the fuel product changed -- the historical and future
# products do not use fuel, so re-running them just rewrites identical output.
for src in ${SOURCES:-historical future future_with_fuel}; do
    echo "===================== RISK_SOURCE = $src ====================="
    RISK_SOURCE=$src python transmission_cost_risk_penalty.py
    echo
done
