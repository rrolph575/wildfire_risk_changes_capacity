# Validation against observed fires (MTBS)

What happened when the risk products were checked against where fires have
actually burned. **The method was deliberately left unchanged in response to
this — see "Decision" at the end.** This document exists so the limitation is
on the record and travels with the product.

## Data

**MTBS** (Monitored Trends in Burn Severity), satellite-mapped burned-area
perimeters, **all land ownerships**, fires >=500 acres in the East and >=1000
in the West. Filtered to `incid_type == 'Wildfire'` — prescribed fire is a
management decision, not risk, and is concentrated on federal land.

| region | wildfires | years | acres | cells overlapping |
|---|---|---|---|---|
| TVA | 419 | 1985-2025 | 780,719 | 1,657 of 43,725 (3.8%) |
| SoCal | 631 | 1984-2025 | 6,687,022 | 4,466 of 19,407 (23.0%) |

Committed as `data/fire_perimeters/{tva,socal}_mtbs_wildfires.gpkg`.

> An earlier attempt used the NIFC Interagency Fire Perimeter History (2,245
> records in the TVA box). **That dataset cannot answer this question** — it is
> 99.9% USFS/NPS/FWS, so it is confounded with federal land ownership, which in
> TVA *is* the eastern mountains. It is not used here.

## Result

"Lift" = mean class of burned cells / mean class of unburned cells. Above 1
means the layer marks burned ground as riskier than average; below 1 means it
marks it as *safer* than average.

| scheme | TVA | SoCal |
|---|---|---|
| fire weather only | **0.25x** | **0.42x** |
| current (FWI base, fuel shifts +/-1) | 0.86x | 0.99x |
| inverted (fuel base, FWI shifts +/-1) | 1.27x | 1.44x |
| **fuel_index alone** | **1.87x** | **1.83x** |

In both regions the FWI layer is **anti-predictive** of where fires burn, the
current combination has close to no skill, and `fuel_index` alone is the best
available predictor. In TVA, 87% of cells that burned are classed `none` by
historical fire weather, against 50% of all cells.

Geographically: 84% of TVA wildfires and 91% of burned acres are in the eastern
half, while the risk map concentrates on the west.

## Why this is expected, not a bug

FWI measures atmospheric dryness. In TVA that peaks in the Mississippi valley
west — row-crop farmland with nothing to burn — while the forested eastern
plateau is cooler and wetter but carries the fuel, terrain and human ignitions.
**In the Southeast, fuel rather than weather is the limiting factor for fire.**
In SoCal the region-relative cutoffs bury the coastal wildland-urban interface,
where California's destructive fires occur, because the same box contains the
Mojave and Colorado deserts with FWI up to 292 (see the Eaton Fire check,
`fire_validation_eaton.png`).

## What this does and does not invalidate

**Does NOT invalidate the climate-change signal.** The projected-vs-historical
comparison is *within-cell* — each location measured against itself — so a
spatial ranking bias cancels. "TVA high-risk 10% -> 24.9% under fixed cutoffs"
remains a valid statement about worsening fire weather, and FWI is the right
instrument for it. Fuel cannot do this at all: LANDFIRE 2024 is a static
snapshot with no time dimension.

**DOES qualify the absolute classes.** The cost penalty consumes the absolute
class, charging x1.0-x1.5 on a spatial ranking that MTBS shows is unreliable.
Route-level cost differences should be read as reflecting *fire-weather
severity*, not *fire likelihood*.

## A confound that limits ALL of these numbers

Before reading the lift table as a ranking, note what the most skilful single
predictor turned out to be:

| predictor | TVA | SoCal |
|---|---|---|
| **"low historical FWI" alone** | **2.57x** | **1.80x** |
| FWI change, relative | 2.19x | 1.61x |
| FWI change, absolute | 1.82x | 1.27x |
| fuel_index alone | 1.87x | 1.83x |

Low fire-weather index obviously does not *cause* fire. It is a **land-cover
proxy**: high FWI marks dry farmland and desert with nothing to burn, low FWI
marks moist forested ground carrying fuel. Anything inversely correlated with
FWI inherits skill for free.

**This matters for interpreting the change signal.** `delta_rel` correlates
-0.670 with historical FWI in TVA, so a large part of its apparent skill is the
same proxy one step removed, not a genuine climate-fire link. A change-based
product was prototyped (`delta_fwi_risk.py`, scored by `score_risk_variants.py`)
and reached 2.38x TVA / 2.37x SoCal combined with fuel — but that number cannot
be separated from land cover and **should not be quoted as "predicts fire
better"**.

`fuel_index` is the exception: it measures vegetation directly rather than
inheriting it through a correlation, so its 1.87x/1.83x is the one figure here
that means what it appears to mean.

## Decision

**The method was kept unchanged**, reaffirmed 2026-08-28 after the
change-based alternative was built and scored.

The project's purpose is to show how climate change alters wildfire risk, and
FWI is what carries that signal. The validation failure is in *spatial
ranking*; the climate result is a *within-cell* comparison (each location
against itself over time), so a spatial bias cancels and
"TVA high-risk 10% -> 24.9% under fixed cutoffs" remains valid.

A change-based fire-weather axis was considered seriously, since the research
question is literally about change. It was NOT adopted: its better lift scores
could not be separated from the land-cover confound above, so it offered no
demonstrable improvement while reopening a settled method.

The product is framed as **fire-weather severity and its projected change** —
never as a forecast of where fires will burn. The absolute classes, which the
cost penalty consumes, price fire-weather severity rather than fire
likelihood.

Reproduce with `plot_fire_validation.py` and the committed MTBS GeoPackages.
The source shapefile (390 MB zip, 616 MB extracted) is at
`/scratch/$USER/mtbs/` and is not in the repo; read it with
`gpd.read_file(SHP, bbox=(...))` to avoid loading all of CONUS.
