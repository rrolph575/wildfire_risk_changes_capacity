# Summary of methods: regional wildfire high-risk maps

A plain-language walkthrough of what we did and why. For full detail see
`PROJECT_PLAN_regional_high_risk_maps.md`.

> **Companion approach.** This document covers the maps built from `A`, the
> *change* in fire weather. A second approach maps **absolute** fire-weather
> severity instead, with per-region thresholds and no trend information — see
> `summary_of_methods_absolute_regional_thresholds.md`. The two answer different
> questions and are not interchangeable.

## Goal
Take the existing national map of where fire weather is worsening
(from the upstream wildfire/ project) and make **zoomed-in versions for two
regions** — Southern California and the TVA area — that flag **high-risk** cells,
plus versions that also show which land is actually **burnable**. This is a
follow-on project: same method and thresholds, but framed around wildfire risk
(not undergrounding).

## The key quantity: `A`
`A` = the **future** (2025–2059) number of days per year with extreme fire
weather (FWI above the local historical 2000–2014 98th-percentile level), per
grid cell. Bigger `A` = more extreme fire-weather days in the future. This field
was already computed (by `fwi_exceedance_change_maps.py` in wildfire/) and saved,
so we just loaded it.

## The three thresholds
A cell is flagged **high risk** when `A` is at or above a threshold. Three levels
(more area flagged at lower thresholds):

| Scenario | Threshold |
|---|---|
| low | 16 days/yr |
| medium | 18 days/yr |
| high | 20 days/yr |

*(These are carried over from the upstream project. Because this is now a
separate project, they can be changed here without affecting wildfire/.)*

## Steps we took
1. **Loaded the `A` field** (98th-percentile version) and each grid cell's
   lat/lon from the saved results file.
2. **Defined the two regions:**
   - *TVA* — the lat/lon box covering all buses in `tva_bus_geographic_data.csv`
     (lat 33.3–37.3, lon −90.0 to −82.8).
   - *Southern California* — a standard SoCal box (lat 32.5–35.5, lon −121.0 to
     −114.0). *(The originally supplied coordinates were unusable — both corners
     were identical — so this standard extent was confirmed as a replacement.)*
3. **Made the first two maps** (one per region): each cell colored **crimson**
   where `A ≥ threshold` (high risk) or **grey** otherwise, with state borders
   overlaid. Three stacked panels = the low/medium/high thresholds. Each panel
   title reports the % of in-region cells that are high risk.
4. **Added a burnable/non-burnable layer** for the next two maps. Using the USFS
   Wildfire Hazard Potential raster, each cell is labeled **non-burnable** if its
   value is 0 (water, urban, agriculture, barren) or **burnable** if greater than
   0. Non-burnable cells are drawn in **steel blue** underneath, so it's clear
   which high-risk cells sit on land that can actually burn.
5. **Added color legends** to every panel and saved all four maps.

## What came out
Four figures (each = 3 panels for the three thresholds):

| File | Region | Burnable layer |
|---|---|---|
| `risk_A_p98_socal.png` | Southern California | no |
| `risk_A_p98_tva.png` | TVA | no |
| `risk_A_p98_socal_burnable.png` | Southern California | yes |
| `risk_A_p98_tva_burnable.png` | TVA | yes |

Plus `risk_A_p98_risk_classes.gpkg` — every in-region cell as a square polygon
(EPSG:4326), layer `risk_classes`, classified `zero` / `low` / `medium` / `high`
by the highest threshold its `A` value meets (`zero` = below the low threshold).
Fields: `region`, `lon`, `lat`, `A_days_yr`, `risk_class`, `risk_level` (0–3),
`whp_burnable`. Note these classes are **bands**, not cumulative: the map panels
show cumulative extents, so the low panel's crimson area is `low`+`medium`+`high`
combined.

Headline numbers (share of cells flagged high risk, low → high threshold):
- **TVA:** 9.9% → 6.0% → 3.9% (78% of the area is burnable).
- **Southern California:** 14.5% → 9.4% → 6.9% of *burnable* cells (46% of the
  region is burnable; much of the rest is ocean/urban).

## How it was run
- The map-making runs in the **`reeds2`** conda env.
- The one-time step that reads the burnable raster needs **`rasterio`**, so it
  runs in the **`rev`** env and caches its result to `.npz`; after that,
  everything runs in `reeds2`.
- Batch script: `submit_regional_high_risk_maps.sh` (SLURM allocation
  **`alcaps`**).
