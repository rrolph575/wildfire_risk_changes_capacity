# Summary of methods: wildfire-risk cost penalty for TVA transmission routing

A plain-language walkthrough of `transmission_cost_risk_penalty.py`, which turns
the wildfire risk classes into a cost penalty on the transmission least-cost-path
(LCP) routing surface. The risk classes it consumes are built by
`regional_absolute_risk_maps.py` — see
`summary_of_methods_absolute_regional_thresholds.md`.

## Goal

Make a routed transmission line pay more for every metre it spends in
higher-wildfire-risk ground, so the router prefers a longer, safer path when the
detour is cheap and accepts risky ground only when avoiding it is expensive.

## The penalty

Each 90 m cost cell is multiplied by the multiplier of the risk class it sits in:

| risk class | multiplier | effect |
|---|---|---|
| none | ×1.0 | no added cost |
| low | ×1.1 | +10% |
| medium | ×1.3 | +30% |
| high | ×1.5 | +50% |

**"none" is ×1.0, not ×0.** A zero multiplier would make no-risk ground *free*
rather than merely unpenalised, and the router would collapse every path onto it.
×1.0 is what "no added cost for lines that only go through no risk zones" means.

**The "percentage of the line in each class" falls out automatically.** Because
the penalty is applied per cell and the router sums cost along a path, a route
that is 30% medium-risk and 70% no-risk pays

    0.3 × 1.3  +  0.7 × 1.0  =  1.09 ×

without that fraction ever being computed anywhere. There is no separate
line-level calculation, and nothing needs to know a route in advance.

## Inputs

| Purpose | Path |
|---|---|
| Risk classes | `abs_risk_hist_p98_risk_classes.gpkg`, layer `risk_classes`, TVA rows |
| Cost surface | `/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/tva_lcp_default_agg_costs.tif` |
| Routes / nodes | `/kfs2/projects/rev/projects/sienna_transmission/tva_lcp/tva_routes.csv` |

The cost raster is 90 m, EPSG:5070, CONUS extent (1.4 GB). Inside TVA it is fully
populated — 100% positive values, median ≈ 223,000 per cell. Outside the TVA area
of interest it is mostly zero, which is why this runs on TVA only.

## Resolution mismatch (the main limitation)

The cost grid is 90 m; the risk cells are ~0.0281° (~2.8 km). About **950 cost
cells sit inside each risk cell** (measured range 952–1014, median 983). Every
90 m cell takes the class of the risk cell containing it, so **the penalty is
blocky at 2.8 km**. It is as sharp as the fire-weather grid allows, which is far
coarser than the routing grid — the penalty steers routes at the scale of a few
km, not metre by metre.

## Keeping routes inside the region

Two separate controls, because "endpoint inside" and "path stays inside" are
different things:

1. **Endpoints** — a route with a bus outside the TVA box is dropped. For the
   current route set this drops nothing and *cannot*: the TVA box was derived
   from the bus lat/lon span padded ~0.25°, so all 57 buses and all 1,512 routes
   are inside it by construction. The check is a guard for future route sets or
   a changed box.
2. **The path itself** — this is the one that bites. A lat/lon box becomes a
   tilted quad in EPSG:5070, so **17.35% of the output raster window lies outside
   the risk cells**. Those cells are written as nodata, making them impassable,
   so no route can bulge outside the region. Left passable they would carry their
   original cost with *no penalty at all*, which is exactly the corridor a
   least-cost router would exploit. Set `EXCLUDE_OUTSIDE_REGION = False` to allow
   it.

## Steps we took

1. **Loaded the TVA risk cells** and mapped each `risk_class` to its multiplier.
2. **Filtered the routes** to those with both endpoints inside the region.
3. **Reprojected the risk cells** to the cost raster's CRS (EPSG:5070) and took
   the raster window covering them.
4. **Rasterized the risk cells** onto the 90 m grid, in row blocks so memory
   stays modest, recording which risk cell each cost cell belongs to.
5. **Multiplied** each cost cell by its class multiplier, wrote nodata outside
   the region, and passed the raster's own nodata through untouched.
6. **Accumulated per-risk-cell statistics** during the same pass, and wrote them
   out as a GeoPackage.

> **One subtlety worth knowing.** Risk cells are squares in EPSG:4326, so
> reprojecting them to EPSG:5070 leaves hairline slivers between neighbours. A
> centre-in-polygon test drops the pixels that fall in those slivers, and they
> keep the ×1.0 base cost — scattered unpenalised pixels strung along cell
> boundaries, precisely the cheap corridor a least-cost router hunts for. Using
> `all_touched=True` claims every touched pixel and closes them. Verified: with
> the fix, every interior raster row is a single unbroken run of classified
> pixels.

## What came out

| File | Size | What it is |
|---|---|---|
| `tva_cost_risk_penalty_90m.tif` | 29 MB | adjusted 90 m cost surface — **the routing input** |
| `tva_cost_risk_penalty_cells.gpkg` | 12 MB | 43,725 risk cells with before/after cost, for QGIS |
| `tva_cost_risk_penalty_routes_in_region.csv` | 225 KB | routes with both endpoints in region |

The raster is 8,268 × 6,296 at 90 m (52.1 M cells), EPSG:5070, float32, aligned
to the same grid as the input with the same nodata (−1), cropped to the TVA risk
extent. The gpkg layer `risk_cost` carries `risk_class`, `multiplier`,
`n_cost_cells`, `cost_mean`, `cost_sum`, `adj_cost_mean`, `adj_cost_sum`, and
`added_cost`.

Headline numbers:

- Region-wide cost **1.065 × 10¹³ → 1.190 × 10¹³, i.e. +11.70%** — the increase a
  line would see if it crossed every cell in the region equally. A real route
  will differ, depending on how much risky ground it crosses.
- Share of 90 m cost cells by class: **none 50.0%, low 25.1%, medium 15.0%,
  high 9.9%** — matching the 50/25/15/10 design of the risk classes.
- Routes: 1,512 in, **1,512 kept, 0 dropped**.

Checks that were run: adjusted/original ratios on the raster are exactly
{1.0, 1.1, 1.3, 1.5}; per-risk-cell `adj_cost_sum / cost_sum` equals the
multiplier to 1×10⁻⁷ (float32 rounding); every risk cell contains at least 952
cost cells and none is empty; output nodata fraction is 0.1735, matching the
outside-region area exactly.

## Three products, not one

The same method is now run against three sets of risk classes, each
writing to `outputs/cost_penalty_<source>/`:

| source | risk classes used | region-wide | median route |
|---|---|---|---|
| `historical` | 2000–2014 fire weather | +11.71% | +8.06% |
| `future` | 2025–2059 fire weather | +20.82% | +16.76% |
| `future_with_fuel` | the above combined with LANDFIRE fuel | +19.59% | +17.27% |

`RISK_SOURCE` selects which, in both `transmission_cost_risk_penalty.py`
and `route_risk_cost_analysis.py`, and routes inputs and outputs together.
Fuel redistributes cost rather than changing the total — see
`summary_of_methods_fuel_combination.md`.

## Caveats

- **The classes are region-relative.** TVA "high" means FWI ≥ 40.8 — the worst
  10% *of TVA* — which is mild nationally (SoCal's "high" is ≥ 125). So ×1.5 is
  penalising "worst tenth of TVA", not "extreme fire weather in absolute terms".
  If the penalty is meant to stand for real wildfire exposure cost, that argues
  for a gentler high multiplier here, or for rebuilding the risk classes on an
  absolute scale (`FIXED_CUTOFFS`) first — on a national yardstick TVA would have
  few or no high cells at all.
- **The region boundary is now a hard wall.** Nodes sit inside the unpadded bus
  span with ~25 km of pad beyond them, so there is margin, but a route between
  two edge nodes that would naturally bulge outside is forced to stay in. Worth
  checking for after routing.
- **The penalty is blocky at 2.8 km**, per the resolution section above.

## How it was run

- Runs in the **`rev`** conda env (needs rasterio + geopandas).
- **49 seconds**, **738 MB** peak RAM, ~220 MB read from the shared filesystem —
  small enough to run directly without a SLURM allocation. Use a batch job if
  sweeping multiplier values or extending beyond TVA, since both scale this up.
