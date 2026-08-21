# Summary of methods: combining fire weather with fuel

How LANDFIRE fuel is brought into the wildfire risk zones, and how it is
combined with the projected fire-weather classes into a single class on the
same none/low/medium/high scale.

Read `summary_of_methods_absolute_regional_thresholds.md` and
`summary_of_methods_future_projected_risk.md` first — this document only covers
what fuel adds on top of them.

## Why fuel was added

FWI is a fire **weather** index with no fuel term. Across TVA the two signals
run in opposite directions and are near-independent of each other:

| across TVA | rank correlation with longitude |
|---|---|
| fire weather (p98 FWI) | **−0.52** → worse in the **west** |
| fuel (`woody`, LANDFIRE) | **+0.40** → more in the **east** |
| fire weather vs fuel | **−0.04** → essentially independent |

So the fire-weather-only map concentrates risk on the agricultural west and
understates the forested eastern plateau. Fuel is not a proxy for anything
already in the map — it carries genuinely new information.

## Step 1 — measure the fuel

`landfire_fuel_composition.py` (batch, ~5 min) reads **LANDFIRE 2024 FBFM40**
(30 m, EPSG:5070) over a 468 M-pixel TVA window. Each ~2.8 km risk cell holds
roughly 8,700 LANDFIRE pixels, so rather than taking one dominant fuel model it
tallies the **composition** — the fraction of each cell in each Scott & Burgan
family. The fractions sum to exactly 1.0 per cell.

    GR  grass  101-109        TL  timber litter      181-189
    GS  grass-shrub 121-124   SB  slash-blowdown     201-204
    SH  shrub  141-149        NB  non-burnable  91 urban, 92 snow/ice,
    TU  timber-understory                       93 agriculture, 98 water,
        161-165                                 99 barren

Mean composition over TVA: **TL 53.1%, GR 17.8%, non-burnable 21.4%**
(agriculture 10.8, urban 8.1, water 2.5), TU 4.2%, SH 2.6%, GS 0.9%, SB ~0%.

**LANDFIRE also replaces WHP** for identifying non-burnable ground, with a
reason attached rather than an undifferentiated 0. Its coastline agrees with
WHP's for TVA — the job reported *0 cells with no LANDFIRE pixels*.

## Step 2 — the fuel axis

    woody = frac_TL + frac_TU + frac_SH + frac_GS

The fraction of the cell in timber and shrub families. Two deliberate choices:

- **Grass excluded.** It burns fast but carries little load, and `frac_GR` is
  flat across TVA (rank correlation with longitude −0.04), so it would add
  noise rather than signal.
- **Non-burnable needs no special handling.** `woody` is a fraction of the
  WHOLE cell, so agriculture, water and urban dilute it automatically — a cell
  that is 60% agriculture and 40% timber scores 0.40.

Classed at **terciles within the region** — the 33rd and 67th percentile cell:

| fuel class | TVA `woody` | share |
|---|---|---|
| low | < 0.488 | 33% |
| medium | 0.488 – 0.785 | 34% |
| high | ≥ 0.785 | 33% |

> **Terciles, not the 50/75/90 used for fire weather.** Fire weather is the
> primary axis and `high` should be selective. Fuel is a MODIFIER: with
> FWI-style cutoffs it would demote 17,557 cells and promote only 4,114,
> collapsing `high` from 26% to 9% — shrinking the map rather than informing
> it. Terciles keep it near-symmetric (12,613 promoted / 11,938 demoted).

## Step 3 — combining the two

The two quantities are not commensurable — FWI runs 0–300+, `woody` is a
fraction 0–1 — so there is **no arithmetic** that combines them honestly.
Instead each is converted to an ordinal class against its own region's spread,
and the pair is resolved through a 12-entry table. Fuel shifts the fire-weather
class by one step, clipped at the ends:

| FWI ↓ / fuel → | low | medium | high |
|---|---|---|---|
| **none** | none | none | **low** |
| **low** | none | low | medium |
| **medium** | low | medium | **high** |
| **high** | medium | high | high |

The two corners that matter: **severe fire weather over bare ground is marked
down**; **moderate weather over heavy timber is marked up**. That is the whole
purpose of adding fuel.

The `none` + high-fuel cell resolves to `low` (not `none`) deliberately: `none`
in this scale means "below the region's median cell", not "safe", and 7,080
TVA cells — 16% of the region — sit in that combination.

**Non-burnable gate**, applied last and overriding: `frac_burnable < 0.10`
forces `none`. This catches **1,164 cells** (reservoirs, dense urban) and is
what stops the cost penalty charging a wildfire multiplier on open water.

Built by `combine_fwi_fuel_risk.py` (~45 s).

## What came out

Class shares over TVA land cells:

| class | fire weather only | + fuel |
|---|---|---|
| none | 30.8% | 25.5% |
| low | 25.4% | **31.8%** |
| medium | 17.8% | 24.4% |
| **high** | **26.0%** | **18.3%** |

**12,613 promoted, 11,938 demoted, 19,174 unchanged** — 56% of cells move.

Downstream, on the transmission cost penalty:

| product | region-wide | median route | p75 | max route |
|---|---|---|---|---|
| historical fire weather | +11.71% | +8.06% | 15.48% | 50.00% |
| projected fire weather | +20.82% | +16.76% | 28.67% | 50.00% |
| **projected + fuel** | **+19.59%** | **+17.27%** | **25.80%** | **48.87%** |

**Fuel redistributes risk rather than raising or lowering it.** The regional
total barely moves (20.82% → 19.59%) despite 56% of cells changing class. What
changes is *where* the cost sits — off the agricultural west, onto the forested
east. At route level it compresses the distribution: the p75 falls, the maximum
drops below 50% for the first time (no route is now entirely in high-risk
ground), while the p25 and median edge up. For routing that is what matters,
since the router responds to where expensive ground is, not to the average.

## Assumptions worth knowing

| assumption | what it costs |
|---|---|
| 40 fuel models collapsed to **6 published families** | none — these are the Scott & Burgan groupings, not an invention |
| **within-family models treated identically** (TL1 = TL9) | real loss: TL1 is low-load compact litter, TL9 very high-load. TVA timber is a genuine mix (TL6 ~30%, TL2 ~16%, TL9 ~3%) |
| **area fraction, not load-weighted** | follows from the above — `woody` measures how much of the cell is woody fuel, not how much fuel there is |
| **SB excluded from `woody`** | slash/blowdown is heavy fuel but covers 365 cells at most 14%; left out deliberately as immaterial for TVA |
| cutoffs are **within-region terciles** | will not transfer to SoCal — chaparral country needs its own index and cutoffs |
| fuel is **present-day**, fire weather is **projected** | fuels are held static across 2025–2059: no vegetation shift, fuel accumulation, land-use change or fire history |

The load-weighting refinement — weighting each model by its published fuel load
rather than counting area — is the obvious next improvement, and is a modelling
choice rather than a bug fix.

## How it was run

- `landfire_fuel_composition.py` — batch, `rev` env, ~5 min, 468 M pixels
- `combine_fwi_fuel_risk.py` — `rev` env, ~45 s
- LANDFIRE raster: `/scratch/$USER/landfire/LF2024_FBFM40_CONUS.tif`
  (extracted from `/scratch/gbuster/transfer/LF2024_FBFM40_CONUS.zip`, which is
  never written to)
