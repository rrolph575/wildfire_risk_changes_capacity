#!/bin/bash

#SBATCH --account=alcaps
#SBATCH --partition=debug
#SBATCH --time=0-01:00:00   # ~1 min per source per script; ~6 min total
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=16000
#SBATCH --mail-user=rebecca.fuchs@nlr.gov
#SBATCH --mail-type=END,FAIL
#SBATCH --job-name=regen_figs
#SBATCH --output=logs/slurm-%j.out

# Regenerate every cost-penalty figure for all three risk products, so the
# figures match the rebuilt data (5 Aug fwi_tc) and the fuel-informed classes.
#
#   cost_penalty_explainer_zoom.png / _cell.png   how the penalty acts
#   tva_route_cost_summary.png                    before/after per route
#
# Writes only into outputs/cost_penalty_<source>/.
# Submit with:  sbatch submit_regenerate_figures.sh

. $HOME/.bashrc

cd /projects/alcaps/bfuchs/wildfire_risk_changes_capacity
mkdir -p logs

conda activate rev

for src in ${SOURCES:-historical future future_with_fuel}; do
    echo "===================== RISK_SOURCE = $src ====================="
    RISK_SOURCE=$src python plot_cost_penalty_explainer.py
    RISK_SOURCE=$src python plot_route_cost_summary.py
    echo
done
