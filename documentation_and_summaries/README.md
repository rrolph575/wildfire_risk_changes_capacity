# Documentation index

Which document describes what, and which script and outputs it corresponds to.
Start here if you are not sure which method a number came from.

## Current pipeline

Each step feeds the next. The first one produces the cutoffs everything
downstream is measured against, so it is the one to read first.

| doc | method in brief | script | outputs |
|---|---|---|---|
| [summary_of_methods_absolute_regional_thresholds.md](summary_of_methods_absolute_regional_thresholds.md) | Classify each cell by its **historical (2000–2014) p98 FWI** — the fire-weather severity its worst 2% of days reach. Drop non-land cells, then give each region its own cutoffs from the 50th/75th/90th-percentile cell *within that region* → none / low / medium / high. **Produces the cutoffs everything downstream uses** (TVA 35.1 / 38.8 / 40.8). | `regional_absolute_risk_maps.py` (`FIELD_SOURCE="historical"`) | `outputs/risk_historical/` |
| [summary_of_methods_future_projected_risk.md](summary_of_methods_future_projected_risk.md) | Recompute the same p98 over **2025–2059 (ssp245)**, then classify it with the **historical cutoffs held fixed** — re-deriving them would force the same 50/25/15/10 split and erase the projection signal. Letting the shares move *is* the result: TVA high-risk 10% → 24.9%. | `future_fwi_projected_hazard.py` (batch) → same script (`FIELD_SOURCE="future"`) | `outputs/risk_future/` |
| [summary_of_methods_fuel_combination.md](summary_of_methods_fuel_combination.md) | Bring **fuel** in from LANDFIRE FBFM40. Tally each cell's fuel composition, reduce it to `fuel_index` = SH + GS + TU + TL + **0.5·GR** (grass counts, at half weight — fastest spread but lightest load), class that at within-region **terciles**, then combine with the fire-weather class through a 12-entry table — fuel shifts the class one step up or down. In TVA it redistributes risk off the agricultural west onto the forested east; in SoCal it reinforces fire weather instead, promoting coastal chaparral and demoting desert. | `landfire_fuel_composition.py` (batch), `combine_fwi_fuel_risk.py` | `outputs/risk_future_with_fuel/` |
| [summary_of_methods_transmission_cost_penalty.md](summary_of_methods_transmission_cost_penalty.md) | Multiply every 90 m transmission cost cell by the multiplier of the risk class it sits in (**×1.0 / 1.1 / 1.3 / 1.5**), then re-cost the 1,509 existing TVA routes on the penalised surface. (The route GeoPackage holds 1,512 features; 3 are zero-length Points between co-located buses and are correctly skipped.) | `transmission_cost_risk_penalty.py`, `route_risk_cost_analysis.py` | `outputs/cost_penalty_historical/`, `_future/`, `_future_with_fuel/` |
| [README_tva_cost_risk_penalty_outputs.md](README_tva_cost_risk_penalty_outputs.md) | Not a method — **data dictionary**: field-by-field description of the penalty raster, the cells GeoPackage and the route CSVs. | — | describes the above |

Both risk scripts share one `FIELD_SOURCE` switch, and the cost scripts share a
`RISK_SOURCE` switch; each routes its own inputs *and* outputs to the matching
`outputs/` subfolder, so historical and future products never overwrite.

## Running the pipeline

Order matters — each step reads the previous step's output. Most steps are
seconds and run directly in the `rev` conda env; only the two marked **batch**
need SLURM. `REGION` defaults to `tva`; `RISK_SOURCE`/`SOURCES` selects which
risk product to cost.

| # | command | time | produces |
|---|---|---|---|
| 1 | `python historical_fwi_percentiles.py` **(batch)** | ~30 min | historical p98 FWI + the cutoffs everything uses |
| 2 | `FIELD_SOURCE=historical python regional_absolute_risk_maps.py` | ~20 s | `outputs/risk_historical/` |
| 3 | `sbatch submit_future_fwi_projected_hazard.sh` **(batch)** | ~40 min | projected p98 FWI |
| 4 | `FIELD_SOURCE=future python regional_absolute_risk_maps.py` | ~20 s | `outputs/risk_future/` |
| 5 | `REGIONS="tva socal" sbatch submit_landfire_fuel_composition.sh` **(batch)** | ~10 min | `<region>_fuel_composition.gpkg` |
| 6 | `REGION=<region> python combine_fwi_fuel_risk.py` | ~20 s | combined classes + 3-panel figure |
| 7 | `REGION=<region> python plot_fuel_maps.py` | ~15 s | composition + change maps |
| 8 | `sbatch --export=ALL,SOURCES="future_with_fuel" submit_transmission_cost_risk_penalty.sh` | ~1 min | penalised 90 m cost raster |
| 9 | `sbatch --export=ALL,SOURCES="future_with_fuel" submit_route_risk_cost_analysis.sh` | ~7 min | per-route cost increase |

**Steps 8 and 9 are ordered and must not be swapped** — step 8 *writes* the
penalised raster `<region>_cost_risk_penalty_90m.tif`, and step 9 *reads* it to
re-cost the routes. Running 9 first would silently price routes against the
previous raster.

Omit `SOURCES` in steps 8–9 to rebuild all three risk products instead of just
the fuel one (~21 min rather than ~7). Only do that if the fire-weather-only
products actually changed — they do not use fuel.

## In progress

**Southern California is complete through step 7** — risk classes, fuel
composition, combined classes and all figures exist. Steps 8–9 are blocked:
SoCal has no least-cost-path cost surface and no routes, both pending from the
transmission team. The scripts are already `REGION`-parameterised, so when
those arrive the only edit is filling the three paths in `region_inputs.py`;
until then `REGION=socal` stops with an explicit message rather than silently
borrowing TVA's cost raster, which covers the extent but was never built for it.

## Archived — the retired `A` / trend method

Kept only as a record. **These describe files that no longer exist**; the code
was deleted in commit `6f76914`.

| doc | what it described | why retired |
|---|---|---|
| [archive/summary_of_methods.md](archive/summary_of_methods.md) | The `A` metric: future days/yr above **each cell's own** historical p98, flagged high risk at 16 / 18 / 20 days/yr. | A per-cell bar makes the historical count ~7.3 days/yr *everywhere* by construction, so `A` measures only **change**, not severity — and in TVA it ran backwards (correlation −0.49 with actual severity). |
| [archive/PROJECT_PLAN_regional_high_risk_maps.md](archive/PROJECT_PLAN_regional_high_risk_maps.md) | Plan and spec for that same method — region boxes, thresholds, inputs. | Same. Its region-box rationale was **already migrated** into the absolute-thresholds doc, so nothing is lost by archiving it. |
