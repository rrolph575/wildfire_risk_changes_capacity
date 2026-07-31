# Summary of methods: regional risk maps from absolute fire-weather severity

A plain-language walkthrough of the **second** mapping approach, produced by
`regional_absolute_risk_maps.py`. The first approach (`regional_high_risk_maps.py`)
is described in `summary_of_methods.md`; this is a companion to it, not a
replacement — the two answer different questions.

## Why we made a second version

The first approach classifies a cell by `A` = future (2025–2059) days per year
above **that cell's own** historical 98th-percentile fire weather. Because every
cell is measured against its own bar, the historical count `B` is ~7.3 days/yr
(2% of 365) **everywhere by construction** — we confirmed this in the data
(`B` ranges only 7.27–7.33 across all 2.3 M cells). So `A` can only express how
much a cell is *changing*; it cannot express how severe its fire weather *is*.

That shows up clearly in these two regions. Correlation between `A` and absolute
historical severity:

| Region | corr(`A`, historical p98 FWI) |
|---|---|
| Southern California | **+0.005** (no relationship at all) |
| TVA | **−0.487** (backwards) |

The TVA sign is the real issue: mild, damp cells have a low bar to clear, so they
gain exceedance days fastest and appear as "high risk" precisely *because* they
are mild. This second approach removes the trend signal entirely.

## The key quantity: historical p98 FWI

Each cell's **historical (2000–2014) 98th-percentile FWI value** — the fire-weather
level its worst 2% of days (~7 days/yr) actually reached. Units are FWI_tc. Higher
= genuinely more severe fire weather. **No future data is used anywhere in this
script.** This field was already in the same saved results file (`pct_maps`) — it
is the very threshold the first approach counted exceedances against.

> **Two different percentiles, two different axes.** The *p98* is over **time** at
> one cell (which days) and produces one FWI number per cell. The *50th/75th/90th*
> below are over **space** across cells (which cells) and are only used to pick the
> cutoff numbers. They do not interact.

## Land mask (this matters — it moved the numbers)

The FWI grid is a full lat/lon rectangle, so it carries real values **over the
ocean and over Mexico**, not just over CONUS land. In the SoCal box, **27% of
cells are water**, with a median FWI of 46. Those cells cannot burn, but they were
low enough to drag the region's cutoffs down and were being classified on the map.

We therefore drop every cell not covered by the USFS WHP raster before computing
anything. Effect:

| | SoCal median cell | SoCal cells |
|---|---|---|
| including ocean | FWI 83.5 | 26,643 |
| **land only (used)** | **FWI 98.6** | **19,407** |

TVA is entirely inland, so its numbers are unchanged (43,725 cells).

## The thresholds

Each region gets **its own** cutoff set, because the two are different
fire-weather regimes: SoCal's land cells span FWI 21–261 while TVA's span 14–47.
TVA's *maximum* falls below SoCal's 25th-percentile cell, so a single shared
national cutoff would leave TVA with zero medium and zero high cells.

Cutoffs are read off the **50th / 75th / 90th percentile of hist-p98 among that
region's own land cells**, then applied as plain absolute FWI cutoffs:

| Region | low (≥) | medium (≥) | high (≥) |
|---|---|---|---|
| Southern California | 98.6 | 111.7 | 125.2 |
| TVA | 35.1 | 38.8 | 40.8 |

A cell is **none** below the low cutoff, otherwise the highest class it reaches.
By construction this is a 50 / 25 / 15 / 10 % split of each region's land cells.

> ⚠️ **The classes are region-relative.** A SoCal "high" cell (FWI ≥ 125) is far
> more severe fire weather than a TVA "high" cell (FWI ≥ 41). They are *not*
> comparable across regions. Setting `FIXED_CUTOFFS` in the script switches both
> regions onto one shared yardstick if that comparison is ever needed — note that
> on a CONUS-wide yardstick TVA has no medium or high cells at all.

## Steps we took

1. **Loaded the historical p98 FWI field** and each cell's lat/lon from the saved
   results file (same file as the first approach, different array).
2. **Used the same two region boxes** as the first approach — TVA from the bus
   span, SoCal the standard box.
3. **Masked to land** (cells covered by the WHP raster), as described above.
4. **Derived each region's three cutoffs** from its own land-cell distribution.
5. **Classified every land cell** none / low / medium / high.
6. **Drew one map per region** on an ocean/land basemap, so "no risk" land is
   never confused with water. Cells are drawn as an image rather than as markers
   so they tile exactly with no seams.
7. **Added the burnable layer** for the second pair of maps, exactly as before —
   non-burnable cells (WHP = 0: water, urban, agriculture, barren) in steel blue.
   Cutoffs stay the ones computed over *all* land cells, so both versions of a
   region's map share identical class boundaries.
8. **Exported a GeoPackage** of every classified cell.

## What came out

Four figures (one panel each — all four classes appear at once, unlike the
three-panel threshold figures of the first approach):

| File | Region | Burnable layer |
|---|---|---|
| `abs_risk_hist_p98_socal.png` | Southern California | no |
| `abs_risk_hist_p98_tva.png` | TVA | no |
| `abs_risk_hist_p98_socal_burnable.png` | Southern California | yes |
| `abs_risk_hist_p98_tva_burnable.png` | TVA | yes |

Plus `abs_risk_hist_p98_risk_classes.gpkg` — 63,132 cells as square polygons
(EPSG:4326), layer `risk_classes`, fields: `region`, `lon`, `lat`,
`hist_p98_fwi`, `risk_class`, `risk_level` (0–3, for styling), `whp_burnable`
(1 burnable / 0 non-burnable), and `cut_low` / `cut_medium` / `cut_high` so the
cutoffs that produced each class travel with the data.

Headline numbers — share of cells in each class, **of burnable cells**:

| Region | none | low | medium | high | burnable |
|---|---|---|---|---|---|
| Southern California | 49.1% | 23.8% | 15.7% | **11.5%** | 63.5% of land |
| TVA | 55.3% | 26.1% | 13.5% | **5.0%** | 78.1% of land |

*(Over all land cells the split is exactly 50/25/15/10 in both regions by
construction; the table above differs because non-burnable cells are excluded
from the denominator. SoCal's burnable land skews slightly worse than its land
average, TVA's slightly better.)*

Geographically the result reads as expected: in SoCal the marine-influenced
coastal strip and LA basin fall in **none**, while the interior deserts and
foothill ranges carry the high classes. In TVA the severity gradient runs
west-to-east, with the western (Mississippi/west-Tennessee) end most severe.

## How it was run

- Runs in the **`rev`** conda env (needs geopandas + matplotlib; rasterio only if
  the burnable cache has to be rebuilt).
- Reuses `sample_burnable()` and `grid_step()` from `regional_high_risk_maps.py`,
  so the burnable flags and cell geometry are **identical** between the two
  approaches and the `_burnable_cache_<region>.npz` files are shared.
- **No SLURM allocation needed:** the whole script takes **20 seconds** and peaks
  at **235 MB** of RAM — fine to run directly.

## Which approach to use

| Question | Use |
|---|---|
| Where is fire weather *getting worse* fastest? | `regional_high_risk_maps.py` (`A`) |
| Where is fire weather *actually severe*? | this script (historical p98 FWI) |

They are not interchangeable, and in TVA they disagree by construction — see the
correlation table at the top.
