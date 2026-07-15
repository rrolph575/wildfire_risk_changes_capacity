# Project plan: regional wildfire high-risk maps

**Goal.** Reproduce the national fire-weather map (from the upstream wildfire/
project, `undergrounding_A_p98_national.png`) as **four zoomed regional maps**
that flag **high-risk** cells:

1. Southern California — high-risk extent at the three thresholds.
2. TVA coverage area — same.
3. Southern California — same, **plus** a burnable / non-burnable mask overlay.
4. TVA coverage area — same, **plus** the burnable / non-burnable mask overlay.

This is a **follow-on project**, independent of wildfire/: same method and
thresholds, but framed around high wildfire risk (not undergrounding). All code
and outputs live in
`/projects/alcaps/bfuchs/wildfire_risk_changes_capacity/`.

---

## 1. What the reference map is

The national reference is produced by `_plot_national()` in
`/home/rrolph/wildfire/undergrounding_thresholds.py` (upstream project). It is a
single figure with **3 stacked panels** (rows = the low / medium / high
thresholds). In each panel:

- Every Sup3rCC grid cell (`lon`, `lat` points) is drawn as a small square
  marker.
- **Crimson** where the future exceedance rate `A >= threshold` (high risk);
  **light grey** (`0.85`) otherwise.
- Canada/Mexico borders, CONUS state boundaries, and the transmission lines are
  overlaid on top.
- Panel title reports the `% of CONUS cells` that are high risk.
- Extent is cropped to CONUS: `xlim = (-125.5, -66.5)`, `ylim = (23.5, 51.0)`.

**`A`** = future (2025–2059, ssp245) days/year with FWI above the historical
(2000–2014) p-th-percentile threshold, per cell. It comes from
`/home/rrolph/wildfire/fwi_exceedance_change_maps.py` and is cached in the NPZ
(see Inputs). We use **p98** (`PCTILE = 98`), matching the reference figure.

> **Note on the thresholds.** The three thresholds `{low: 16, medium: 18,
> high: 20}` days/yr originate in the upstream `undergrounding_thresholds.py`
> `THRESHOLDS` dict. They are **copied into this project** (`regional_high_risk_
> maps.py`) so they can be changed here without affecting wildfire/.

The four regional maps are the **same rendering with the extent (`xlim`/`ylim`)
swapped** for each region, plus (for maps 3 & 4) an added burnable mask layer.

---

## 2. Inputs

| Purpose | Path | Notes |
|---|---|---|
| Exceedance field `A` (p95, p98) | `/projects/rev/projects/ntps/fy26/underground_transmission/data/fwi/fwi_tc_AminusB_pcthist2000_2014_cnt2025_2059_maps.npz` | keys: `lat`, `lon`, `percentiles`, `A_maps`, `B_maps`, `metric_maps`. Point grid in EPSG:4326. |
| State boundaries | `/projects/rev/projects/scapes/maps/conus_state_boundaries.gpkg` | for the overlays. |
| Burnable mask (maps 3 & 4) | `/projects/rev/projects/ntps/fy26/underground_transmission/data/rasters/wildfire/resampled/wildfire_hazard_potential_conus_90m.tif` | USFS WHP 90 m resample. EPSG:5070, int32, `nodata = -2147483647`. **Value `0` = non-burnable** (water/urban/ag/barren); `> 0` = burnable. |
| TVA bus locations | `./tva_bus_geographic_data.csv` | defines the TVA region extent. |

All inputs are absolute paths under `/projects/`; this project writes only into
its own folder.

---

## 3. Region definitions

### 3a. TVA coverage area (from `tva_bus_geographic_data.csv`)
Computed from the bus lat/lon span:

- **Latitude:** 33.298 → 37.260
- **Longitude:** −90.049 → −82.808

Add a small pad (~0.25°) so edge buses aren't clipped:
`xlim ≈ (-90.3, -82.55)`, `ylim ≈ (33.05, 37.51)`.

### 3b. Southern California — ✅ confirmed: standard extent
The coordinates in the prompt were unusable: both the upper-left and lower-right
corners were identical — `(36.091326, -122.19206)` — a **zero-area box**, and
that point is on the **central** CA coast (near Monterey), not Southern
California. **Confirmed:** we use a **standard Southern California extent**:

- **Latitude:** 32.5 → 35.5
- **Longitude:** −121.0 → −114.0
- i.e. `xlim = (-121.0, -114.0)`, `ylim = (32.5, 35.5)` (San Diego / LA /
  Inland Empire / southern Central Valley).

---

## 4. Thresholds (same for all four maps)

Applied to `A` (p98), a cell is **high risk** where `A >= threshold`:

| Scenario | Threshold (days/yr) |
|---|---|
| low | 16.0 |
| medium | 18.0 |
| high | 20.0 |

Lower threshold → more cells flagged high risk. These live in the `THRESHOLDS`
dict at the top of `regional_high_risk_maps.py` and can be changed freely in
this project.

---

## 5. Deliverables

Written to `/projects/alcaps/bfuchs/wildfire_risk_changes_capacity/`:

| # | File | Region | Burnable mask |
|---|---|---|---|
| 1 | `high_risk_A_p98_socal.png` | SoCal | no |
| 2 | `high_risk_A_p98_tva.png` | TVA | no |
| 3 | `high_risk_A_p98_socal_burnable.png` | SoCal | yes |
| 4 | `high_risk_A_p98_tva_burnable.png` | TVA | yes |

Plus the code: `regional_high_risk_maps.py`, `submit_regional_high_risk_maps.sh`
(SLURM), `build_results_deck.py` → `wildfire_high_risk_results.pptx`.

Each PNG keeps the 3-panel (low/med/high) layout of the reference figure, with a
per-panel title reporting `% of in-region cells high-risk` (recomputed over the
cropped cells, not CONUS).

---

## 6. Method

### Maps 1 & 2 (no mask) — straightforward crop
1. Load `A_maps` for p98 and `lat`/`lon` from the NPZ.
2. Load state/country boundaries.
3. For each region, subset the finite `A` points to the region bbox (for the
   `%` stat and lighter rendering), set `xlim`/`ylim` to the region, and render
   the 3-panel figure (grey / crimson, boundaries, lines on top).
4. Save the two PNGs.

Implemented as a shared helper `plot_region(name, cfg, common, with_burnable)`
so all four maps share one code path.

### Maps 3 & 4 (with burnable mask) — added raster sample
The `A` field is a coarse Sup3rCC point grid (~4 km); the WHP raster is 90 m in
EPSG:5070. To attach a burnable flag to each `A` point:

1. Open the WHP GeoTIFF with `rasterio`.
2. For the region's `A` points (lon/lat), transform to EPSG:5070 and sample the
   WHP raster (nearest cell) → value per point.
3. Classify each point: `non-burnable` if WHP `== 0`; `burnable` if WHP `> 0`;
   `nodata` if `== -2147483647` (dropped).
4. Render as maps 1 & 2, then add the mask layer: non-burnable cells are drawn
   in **steel blue** *underneath* the grey/crimson so it's clear which high-risk
   cells sit on land that can actually burn. Panel title additionally reports
   `% burnable`.

> **Resolution mismatch — choice made: nearest-point.** One coarse `A` cell
> overlaps many 90 m WHP cells, so "burnable" for a coarse cell is not unique.
> We use the **nearest WHP cell at the point** (simplest). Alternative:
> **burnable fraction** within each coarse cell (windowed read + mean of
> `WHP > 0`), then threshold at e.g. 50%.

---

## 7. Environment & run

- **SLURM allocation (compute account): `alcaps`.** Not to be confused with the
  conda **env** named `rev` used below. `submit_regional_high_risk_maps.sh` sets
  `#SBATCH --account=alcaps`.
- **Envs (two-env split):** geopandas plotting runs in the **`reeds2`** conda
  env (geopandas + matplotlib + python-pptx). `reeds2` has **no rasterio**, so
  the WHP burnable sampling (maps 3 & 4) runs once in the **`rev`** env (has
  rasterio) and caches per-point flags to `_burnable_cache_<region>.npz`; the
  plotting pipeline then runs entirely in `reeds2` off the cache. `rasterio` is
  imported lazily so `reeds2` never needs it. To rebuild flags after a WHP
  change, delete the caches and run once in `rev`.
- Runtime is small (the heavy `A` computation is already cached in the NPZ; WHP
  sampling is only at the region's coarse points, not full-raster). Interactive
  runs suffice; `submit_regional_high_risk_maps.sh` (allocation `alcaps`) runs
  the cache-if-missing (`rev`) + plot (`reeds2`) steps as a batch job, writing
  logs to `./logs/`.

---

## 8. Step-by-step task list

1. [x] Confirm the SoCal bounding box — standard extent (Section 3b).
2. [x] Confirm burnable-mask rendering + resolution handling (Section 6).
3. [x] Verify conda env(s): WHP sampling runs in `rev`; plotting in `reeds2`.
4. [x] Write `regional_high_risk_maps.py` with a shared `plot_region()` helper.
5. [x] Generate maps 1 & 2 (no mask).
6. [x] Add WHP sampling → burnable flags; generate maps 3 & 4.
7. [x] Add color legends; save all four PNGs.
8. [x] Build the results deck (`build_results_deck.py`).
9. [x] Separate into its own project/repo under `/projects/alcaps/bfuchs/` and
   rename undergrounding → high risk throughout.

---

## 9. Notes / assumptions

- **SoCal box** — ✅ standard extent (32.5–35.5 N, −121.0 to −114.0 W).
- **Percentile** — **p98** (`A` also has p95 if wanted).
- **Mask rendering & resolution** — nearest-WHP-cell per point; non-burnable
  drawn as a distinct underlay. Burnable-fraction is the alternate.
- **Lines overlay** — removed. The upstream national map overlaid 3 AC
  transmission lines, but they sit at 39–42°N / west of −111°W, entirely outside
  the SoCal and TVA crops, so they never rendered.
- **Independence** — thresholds live in `regional_high_risk_maps.py`; changing
  them here does not touch the upstream wildfire/ project.
