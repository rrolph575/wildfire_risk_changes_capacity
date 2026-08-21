# Summary of methods: projected (2025–2059) wildfire fire-weather risk

A plain-language walkthrough of the projected version of the risk classes. The
historical version, and the reasoning behind the whole absolute-severity
approach, is in `summary_of_methods_absolute_regional_thresholds.md` — read that
first; this document only covers what changes when the future period is used.

## Goal

Answer "how much more of each region will clear **today's** high-risk bar under
climate projections" — using the same absolute fire-weather severity measure,
but computed over 2025–2059 instead of 2000–2014.

## The two steps

**1. Build the future field** — `future_fwi_projected_hazard.py`, a SLURM batch
job (`submit_future_fwi_projected_hazard.sh`).

Streams the Sup3rCC **ssp245** daily FWI files for 2025–2059 (35 files, ~118 GB
of `fwi_tc`) and writes one `.npz` with two fields:

- `fut_pct_maps` — each cell's **future p90/p95/p98 FWI value**. The direct
  analogue of the historical `pct_maps`: same quantity, same units, later period.
- `days_per_year_maps` — days/yr above each **fixed absolute** FWI threshold.

**2. Re-classify** — `regional_absolute_risk_maps.py` with
`FIELD_SOURCE = "future"`. Identical machinery to the historical version: same
region boxes, same land mask, same 4 classes.

## The one methodological change that matters

**The cutoffs are held FIXED at the historical values.** They are read straight
from the `cut_low` / `cut_medium` / `cut_high` columns of
`abs_risk_hist_p98_risk_classes.gpkg`, so the two products cannot drift apart:

| region | low | medium | high |
|---|---|---|---|
| TVA | 35.1 | 38.8 | 40.8 |
| SoCal | 98.6 | 111.7 | 125.2 |

> **Why not re-derive them from the future field?** Because that would destroy
> the very signal the batch job was run to obtain. Re-deriving means taking the
> 50th/75th/90th spatial percentile of the *future* field, which forces the same
> 50/25/15/10 split by construction. Warming is roughly uniform in space, so the
> spatial *ranking* of cells barely moves — the map would look almost identical
> to the historical one and would say nothing about projection. Holding the
> cutoffs fixed lets the class shares move, and **that movement is the result**.

## What came out

Class shares, as % of in-region land cells:

| class | TVA hist → future | SoCal hist → future |
|---|---|---|
| none | 50.0 → **30.8** | 50.0 → **43.7** |
| low | 25.0 → 25.4 | 25.0 → 25.0 |
| medium | 15.0 → 17.8 | 15.0 → 16.6 |
| **high** | 10.0 → **26.0** | 10.0 → **14.7** |

**TVA's high-risk area roughly 2.6×; SoCal's roughly 1.5×.** Because the cutoffs
are frozen, this reads literally: 26.0% of TVA is projected to clear *today's*
high bar, against 10% today.

Mean p98 rises **+2.7 FWI in TVA** (34.4 → 37.1) and **+5.9 in SoCal**
(93.5 → 99.4). SoCal warms more in absolute FWI, but TVA's classes move further
because its cutoffs are packed into 5.7 FWI (35.1–40.8) while SoCal's span 26.6
(98.6–125.2) — the same shift pushes far more TVA cells across a boundary.

Outputs, all prefixed `abs_risk_future_p98_` so nothing overwrites the
historical set: four PNGs (2 regions × with/without burnable mask) and
`abs_risk_future_p98_risk_classes.gpkg`.

### The `days_per_year_*` fields

The GeoPackage carries `days_per_year_low` / `_medium` / `_high`: the average
number of days per year, over 2025–2059, that the cell's daily FWI exceeded that
region's low / medium / high cutoff. Total exceedance days ÷ 35 years.

Useful because **the class saturates and this doesn't** — two cells can both be
`high` while one exceeds the bar 5 days/yr and the other 19.

There is a natural reference point: a cell whose p98 sits exactly *at* a cutoff
would show **~7.3 days/yr** above it (2% of 365). Above 7.3 is worse than the
bar; below is under it.

| days/yr above the **high** cutoff | TVA (≥40.8) | SoCal (≥125.2) |
|---|---|---|
| median | 4.9 | 1.3 |
| max | 19.5 | 101.7 |

TVA's median cell sits at 4.9 — under the high bar, consistent with only 24.9%
of cells being class `high`. The worst SoCal cell (future p98 = 279) spends
**102 days/yr** above 125.2.

> **Rebuilt 2026-08-18** on the re-released Sup3rCC `fwi_tc` data (the
> 2026-08-05 update, same `v0.2.2` path). The historical field barely
> moved; the projected one did. Numbers above are post-rebuild.
>
> **Fuel is now applied on top of this** — see
> `summary_of_methods_fuel_combination.md`.

## Caveats

- **This is fire WEATHER, with no fuel term.** FWI cannot see that the eastern
  TVA plateau carries far more fuel than the agricultural west, so the projected
  map still puts the heaviest risk in western TVA. Bringing in a fuel-aware
  layer (USFS WHP, or LANDFIRE) is an open, separate step — and note WHP is a
  present-day product, so pairing it with a projected weather field assumes
  fuels stay as they are for 35 years.
- **Not every cell worsens.** In TVA 18,690 cells worsen a class, 23,634 hold
  and **1,401 improve**; 12.2% of TVA cells have a *lower* future p98 than
  historical. SoCal is nearly monotonic (7 cells improve, 0.8% lower). That TVA
  spread deserves a look before the numbers are leaned on — it may be genuine
  regional circulation/precipitation response, or noise from a single ensemble
  member.
- **One scenario, one realisation.** ssp245, `r1i1p1f1` — no ensemble spread, no
  alternative emissions pathway. And a 35-year future window is compared against
  a 15-year historical one, so the two are not sampled equally.
- **Classes remain region-relative**, exactly as in the historical version: TVA
  `high` (FWI ≥ 40.8) is far milder than SoCal `high` (≥ 125.2).

## How it was run

- **Step 1** (batch, `sup3r` env): **14 min 46 s**, peak RSS **3.6 GB**, on the
  `alcaps` allocation. Reads ~118 GB. Submit with
  `sbatch submit_future_fwi_projected_hazard.sh`.
- **Step 2** (`rev` env): ~20 s, as for the historical version.
- Switching `FIELD_SOURCE` back to `"historical"` in
  `regional_absolute_risk_maps.py` reproduces the historical product unchanged.
