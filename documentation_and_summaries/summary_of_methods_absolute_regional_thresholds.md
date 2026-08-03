# Summary of methods: regional risk maps from absolute fire-weather severity

A plain-language walkthrough of the **second** mapping approach, produced by
`regional_absolute_risk_maps.py` — the method this project now uses. The earlier
`A`-based approach it replaced is described in `summary_of_methods.md`; its code
and outputs have since been removed from the repo (see the last section).

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

## The two regions

Both regions use the same lat/lon boxes as the first approach. Recorded here
because the boxes are load-bearing for this method too — the cutoffs are derived
from whatever cells fall inside them, so changing a box changes the thresholds.

**TVA coverage area** — the box comes from the bus lat/lon span in
`tva_bus_geographic_data.csv` (latitude 33.298 → 37.260, longitude −90.049 →
−82.808), padded by ~0.25° so edge buses aren't clipped:

- `xlim = (-90.30, -82.55)`, `ylim = (33.05, 37.51)`

**Southern California** — a standard SoCal extent covering San Diego / LA /
Inland Empire / southern Central Valley:

- `xlim = (-121.0, -114.0)`, `ylim = (32.5, 35.5)`

*This standard box was adopted because the originally supplied coordinates were
unusable: the upper-left and lower-right corners were identical —
`(36.091326, -122.19206)` — giving a zero-area box, and that point sits on the
**central** California coast near Monterey, not in Southern California. The
standard extent was confirmed as the replacement.*

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

| class | spatial percentile threshold | SoCal 98th percentile historical FWI | TVA 98th percentile historical FWI | share of land cells |
|---|---|---|---|---|
| none | below 50th | < 98.6 | < 35.1 | 50% |
| low | 50th–75th | 98.6 – 111.7 | 35.1 – 38.8 | 25% |
| medium | 75th–90th | 111.7 – 125.2 | 38.8 – 40.8 | 15% |
| high | ≥ 90th | ≥ 125.2 | ≥ 40.8 | 10% |

A cell's class is the **highest** cutoff it clears, so a high cell also clears
the low and medium ones. The bands narrow going up (50 → 25 → 15 → 10% of
cells) so that "high" stays selective enough to act on. The three percentiles
are one line in the script — `CLASS_QUANTILES` in
`regional_absolute_risk_maps.py` — and both regions' cutoffs and shares follow
automatically if they are changed.

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
- **Self-contained:** `sample_burnable()` writes and reads the
  `_burnable_cache_<region>.npz` files itself, so no other script is needed.
  Deleting the caches is safe — they rebuild from the WHP raster on the next run
  in `rev` (~71 KB, a few seconds).
- **No SLURM allocation needed:** the whole script takes **20 seconds** and peaks
  at **235 MB** of RAM — fine to run directly.

## Note on the retired approach

The earlier `A`-based method (`regional_high_risk_maps.py`, its submit script,
and the `risk_A_p98_*` outputs) was **removed from the repo on 2026-08-03** in
favour of this one, for the reasons in the first section — `A` cannot express
absolute severity, and in TVA it runs backwards to it. `summary_of_methods.md`
and `PROJECT_PLAN_regional_high_risk_maps.md` are kept as the record of that
method, and describe files that no longer exist. The old results deck was
renamed `old_using_trend_method_wildfire_high_risk_results.pptx`.

Nothing was lost from the input side: neither method ever computed the p98
itself. Both only read arrays from the same upstream file — the retired one used
`A_maps`, this one uses `pct_maps` — and both are still there. Everything
deleted is recoverable from git history at commit `c94f6be`.
