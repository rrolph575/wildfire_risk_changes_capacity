# README — `tva_cost_risk_penalty_*` output files

Data dictionary for the three files produced by
`transmission_cost_risk_penalty.py`. For *why* the method works this way, see
`summary_of_methods_transmission_cost_penalty.md`; this file describes the
outputs themselves, so it can travel with the data.

**Produced:** 2026-08-03 · **Script:** `transmission_cost_risk_penalty.py`
**Regenerate:** `conda activate rev && python transmission_cost_risk_penalty.py`
(~49 s, ~738 MB peak RAM)

## What the penalty is

Every 90 m cost cell is multiplied by the multiplier of the wildfire-risk class
it falls in:

| risk class | multiplier |
|---|---|
| none | ×1.0 (no added cost) |
| low | ×1.1 |
| medium | ×1.3 |
| high | ×1.5 |

Risk classes come from `abs_risk_hist_p98_risk_classes.gpkg` (TVA rows) — each
cell's historical 2000–2014 p98 Canadian FWI, classed against TVA's own
50th/75th/90th-percentile cells. **The classes are TVA-relative:** TVA "high"
means FWI ≥ 40.8, the worst 10% of TVA, which is "very high" but not "extreme"
on the published EFFIS scale. This is deliberate.

## Inputs used

| Role | Path |
|---|---|
| Risk classes | `abs_risk_hist_p98_risk_classes.gpkg`, layer `risk_classes`, `region = 'tva'` |
| Original cost surface | `/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/tva_lcp_default_agg_costs.tif` |
| Routes | `/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/tva_routes.csv` |

---

## 1. `tva_cost_risk_penalty_90m.tif` — the routing input

The adjusted cost surface. **This is the file to feed back into least-cost-path
routing** in place of the original `tva_lcp_default_agg_costs.tif`.

| property | value |
|---|---|
| size | 8,268 × 6,296 (52.1 M cells) |
| resolution | 90 m |
| CRS | EPSG:5070 (CONUS Albers) |
| bands / dtype | 1 / `float32` |
| nodata | `-1.0` |
| bounds (EPSG:5070) | 499231.5, 1123417.0, 1243351.5, 1690057.0 |
| bounds (EPSG:4326) | −90.6178, 32.3973, −81.7657, 38.1081 |
| compression | DEFLATE, predictor 2, tiled 512×512 |
| file size | 29 MB |

**Cell value** = original cost × risk multiplier. Units are *not recorded* in
either raster — the source file carries no units metadata, so these are simply
whatever the LCP pipeline's "aggregated cost" is, unchanged in kind. Typical
values are ~2.1×10⁵ per 90 m cell. The adjusted raster is grid-aligned with the
original (same 90 m grid, same nodata value), so the two are directly
comparable cell for cell.

**`-1.0` means one of two things**, and both are intentional:

1. The cell was nodata in the original cost raster (passed through untouched).
2. The cell lies **outside the TVA risk region** and is therefore impassable.
   A lat/lon box becomes a tilted quad in EPSG:5070, so **17.35% of this
   window** is outside the region. Those cells were made nodata so no route can
   leave the region — left passable they would carry full cost with *no*
   penalty, which is exactly the cheap corridor a least-cost router seeks out.
   Set `EXCLUDE_OUTSIDE_REGION = False` in the script to allow routing there.

The raster is cropped to the TVA risk extent, not the full CONUS extent of the
input (which is 3.9 billion cells). It is correctly georeferenced, so it drops
into the same workflow as long as the routing AOI is inside these bounds.

---

## 2. `tva_cost_risk_penalty_cells.gpkg` — per-risk-cell summary

For inspection and mapping in QGIS. **Not a routing input** — it is aggregated
to the ~2.8 km risk grid, far coarser than routing needs.

- **Layer:** `risk_cost` · **Rows:** 43,725 · **CRS:** EPSG:5070
- **Geometry:** polygon, one per risk cell (~2.8 km square, reprojected from the
  0.0281° lat/lon grid — so they are slightly non-square here)
- **File size:** 12 MB

| field | type | meaning |
|---|---|---|
| `region` | str | always `tva` |
| `risk_class` | str | `none` / `low` / `medium` / `high` |
| `risk_level` | int | 0–3, same order as above (for styling) |
| `multiplier` | float | penalty applied: 1.0 / 1.1 / 1.3 / 1.5 |
| `n_cost_cells` | int | how many 90 m cost cells fall inside this ~2.8 km risk cell (observed 952–1,084) |
| `cost_mean` | float | original cost of **one** 90 m cell here, averaged over the cells above |
| `cost_sum` | float | original cost of **all** those 90 m cells added together = `cost_mean × n_cost_cells` |
| `adj_cost_mean` | float | cost of one 90 m cell **after** the penalty = `cost_mean × multiplier` |
| `adj_cost_sum` | float | all of them after the penalty = `cost_sum × multiplier` |
| `added_cost` | float | what the penalty added = `adj_cost_sum − cost_sum` (0 for `none` cells) |

Observed ranges: `cost_mean` 2.08×10⁵ – 3.81×10⁶; `added_cost` 0 – 4.63×10⁸.

A worked row (a `medium` cell): 956 cost cells, each averaging 220,488 →
`cost_sum` 2.108×10⁸; at ×1.3 that becomes `adj_cost_mean` 286,634 and
`adj_cost_sum` 2.740×10⁸, so `added_cost` is 6.324×10⁷.

**See `cost_penalty_explainer_cell.png`** (made by `plot_cost_penalty_explainer.py`)
for this drawn out: one real risk cell at 90 m, with one pixel, one row across,
and the whole square outlined against the actual field values.
`cost_penalty_explainer_zoom.png` shows the same idea across a wider window —
risk class, original cost, adjusted cost, and the multiplier that resulted.

> ⚠️ **The `_sum` fields are area totals, not route costs.** They add up every
> 90 m cell in the risk cell. A line *crossing* a 2.8 km risk cell passes
> through only ~31 cells (one row across), not all ~958 — so `adj_cost_sum` is
> roughly 30× what a crossing would actually pay. Use the `_sum` fields for
> regional aggregation and for seeing which cells carry the most cost burden;
> use **`adj_cost_mean`** for "what does it cost to cross here", since that one
> is comparable between cells regardless of how many 90 m cells each contains.

By construction `adj_cost_sum / cost_sum == multiplier` for every row (verified
to 1×10⁻⁷, float32 rounding) — a useful integrity check if the file is ever
edited or re-derived.

---

## 3. `tva_cost_risk_penalty_routes_in_region.csv` — routes kept

`tva_routes.csv` filtered to routes with **both** endpoints inside the TVA
region. Same columns as the source, unchanged:

`fid`, `start_BusName`, `end_BusName`, `start_lat`, `start_lon`, `end_lat`,
`end_lon`, `voltage`, `polarity`, `start_option`, `end_option`, `rid`

**1,512 rows in, 1,512 kept, 0 dropped** — so this file is currently identical
to the source. That is structural, not luck: the TVA region box was derived from
the bus lat/lon span padded ~0.25°, so all 57 buses are inside it by
construction and the filter cannot drop anything. It exists as a guard for a
future route set or a changed region box.

---

## Known limitations

- **The penalty is blocky at ~2.8 km.** The cost grid is 90 m but the
  fire-weather grid is ~0.0281°, so ~950–1,080 cost cells share one risk class.
  The penalty steers routes at the scale of a few km, not metre by metre.
- **Classes are TVA-relative,** as noted above — ×1.5 prices "worst tenth of
  TVA", not "extreme fire weather" in absolute terms.
- **The region boundary is a hard wall.** Nodes sit inside the unpadded bus span
  with ~25 km of pad beyond them, but a route between two edge nodes that would
  naturally bulge outside is forced to stay in. Worth checking for after routing.
- **Cost units are undocumented** in the source raster; this output preserves
  whatever they are.
