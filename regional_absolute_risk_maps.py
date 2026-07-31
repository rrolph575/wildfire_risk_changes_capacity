"""
Regional wildfire risk maps from ABSOLUTE fire-weather severity (SoCal + TVA),
with and without a burnable / non-burnable mask.

Companion to regional_high_risk_maps.py. That script classifies a cell by the
future exceedance rate A; this one classifies a cell by how severe its fire
weather is in absolute terms, with no future/trend information at all.

WHY A SEPARATE SCRIPT
    In the A-based maps every cell is compared against *its own* historical p98,
    so the historical exceedance count B is ~7.3 days/yr everywhere by
    construction (2% of 365) and A therefore measures only the *change* at that
    cell. In these two regions A carries essentially no information about
    absolute severity:
        corr(A, historical p98 FWI) = +0.005 (SoCal),  -0.487 (TVA)
    The TVA correlation is *negative*: the mildest cells have the lowest bar to
    clear, so they gain exceedance days fastest and light up as "high risk".
    This script drops the trend signal entirely.

METRIC
    Each cell's historical (2000-2014) p98 FWI value -- the FWI level reached on
    its worst 2% of days (~7 days/yr). Units are FWI_tc. This is `pct_maps` in
    the NPZ, the same field whose exceedance produced A. No future data is read.

    Note the two percentiles act on different axes and do not interact:
      * p98  is over TIME at one cell (which days) -> one FWI value per cell.
      * the 50/75/90 below are over SPACE across cells (which cells) and are
        only used to *pick* the cutoff numbers from each region's own spread.

THRESHOLDS (per region -- see CLASS_QUANTILES / FIXED_CUTOFFS)
    The regions are different fire-weather regimes: historical p98 spans
    21-316 in SoCal but only 14-47 in TVA, i.e. TVA's maximum falls below
    SoCal's 25th-percentile cell. One shared national cutoff would leave TVA
    with zero medium and zero high cells, so each region gets its own set, read
    off the 50th/75th/90th spatial percentile of hist-p98 among its own cells:
        none    hist p98 <  low cutoff        (the "no risk" class)
        low     hist p98 >= low cutoff
        medium  hist p98 >= medium cutoff
        high    hist p98 >= high cutoff
    By construction that is a 50 / 25 / 15 / 10 % split of cells in each region.

    CAVEAT, worth stating on any slide: the classes are region-relative. A SoCal
    "high" cell (FWI ~121) is far more severe than a TVA "high" cell (FWI ~41).
    Set FIXED_CUTOFFS to compare the regions on one absolute yardstick instead.

LAND MASK (matters -- it moves the cutoffs)
    The FWI grid is a full lat/lon rectangle and carries real values over water
    and over Mexico, not just over CONUS land: 27% of the SoCal box is ocean,
    with a median hist p98 of 46. Those cells cannot burn, so they are dropped
    before anything else. Including them pulls SoCal's median cell from FWI 99
    down to 83.5 and lets water set the class boundaries. Land = covered by the
    WHP raster (burnable sample is not nodata); see region_cells().

    Cutoffs are then computed over ALL in-region LAND cells, burnable or not,
    so the plain and _burnable maps use identical class boundaries and both
    agree with the GeoPackage.

Outputs (all written to OUT_DIR):
  * abs_risk_hist_p98_socal.png           -- SoCal, 4-class map, no mask
  * abs_risk_hist_p98_tva.png             -- TVA, 4-class map, no mask
  * abs_risk_hist_p98_socal_burnable.png  -- SoCal, same map + burnable mask
  * abs_risk_hist_p98_tva_burnable.png    -- TVA, same map + burnable mask
  * abs_risk_hist_p98_risk_classes.gpkg   -- one vector layer, "risk_classes",
        every in-region cell for both regions as a square polygon (EPSG:4326).
        Fields: region, lon, lat, hist_p98_fwi, risk_class, risk_level (0-3),
        whp_burnable (1/0/-1), and cut_low / cut_medium / cut_high so the
        cutoffs that produced the classes travel with the data.

Filenames follow TAG, so they change with PCTILE.

Reuses sample_burnable() / grid_step() from regional_high_risk_maps.py, so the
burnable flags and cell geometry are identical between the two projects (the
_burnable_cache_<region>.npz files are shared).

Run in the `rev` conda env (has geopandas + rasterio + matplotlib):
    conda activate rev
    python regional_absolute_risk_maps.py
"""

import os

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap
import geopandas as gpd

from regional_high_risk_maps import sample_burnable, grid_step

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
NPZ_PATH = ("/projects/rev/projects/ntps/fy26/underground_transmission/"
            "data/fwi/fwi_tc_AminusB_pcthist2000_2014_cnt2025_2059_maps.npz")
STATES_PATH = "/projects/rev/projects/scapes/maps/conus_state_boundaries.gpkg"

PCTILE = 98                          # historical percentile that defines "a bad
                                     # fire-weather day" (98th -> worst 2%)

# Spatial percentiles, within each region, used to pick that region's cutoffs.
CLASS_QUANTILES = {"low": 50, "medium": 75, "high": 90}

# Set to a dict to override the derived cutoffs with fixed absolute FWI values,
# e.g. {"socal": {"low": 60, "medium": 90, "high": 120},
#       "tva":   {"low": 30, "medium": 36, "high": 41}}
# or the same numbers for both regions for a single cross-region yardstick.
FIXED_CUTOFFS = None

CLASS_ORDER = ["none", "low", "medium", "high"]
# Sequential ramp: one hue, light -> dark, with a neutral grey for the "none"
# class. Monotonic in lightness so the order survives greyscale and CVD.
CLASS_COLORS = {"none": "#cfcfcf", "low": "#fc9272",
                "medium": "#ef3b2c", "high": "#99000d"}
NB_COLOR = "#6b8fb5"                 # non-burnable underlay (matches sibling)

# Basemap. The FWI grid is CONUS-only, so without these the ocean and the grey
# "none" cells are the same empty white. Ocean is the axes background; land is
# painted back over it from the state + country polygons, so anything still
# blue is water and a pale-cream cell is land the grid does not cover (Mexico).
OCEAN_COLOR = "#dbe7f0"
LAND_COLOR = "#fbfaf7"

# Region extents (lon/lat, EPSG:4326) -- same boxes as regional_high_risk_maps.
REGIONS = {
    "socal": {"label": "Southern California",
              "xlim": (-121.0, -114.0), "ylim": (32.5, 35.5)},
    "tva":   {"label": "TVA coverage area",
              "xlim": (-90.30, -82.55), "ylim": (33.05, 37.51)},
}

OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
TAG = f"abs_risk_hist_p{PCTILE}"


# ----------------------------------------------------------------------------
def load_common():
    """Historical p-th percentile FWI per cell, plus the basemap layers."""
    d = np.load(NPZ_PATH, allow_pickle=True)
    lat, lon = d["lat"], d["lon"]
    pex = list(d["percentiles"].astype(int))
    P = d["pct_maps"][pex.index(PCTILE)]       # historical p98 FWI value
    finite = np.isfinite(P)
    lon, lat, P = lon[finite], lat[finite], P[finite]
    base = tuple(int(v) for v in d["pct_baseline"])
    print(f"Loaded historical p{PCTILE} FWI ({base[0]}-{base[1]}): "
          f"{P.size:,} finite cells (range {P.min():.1f}-{P.max():.1f})")

    states = gpd.read_file(STATES_PATH).to_crs(4326)
    countries = None
    try:                                      # optional context border layer
        world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
        countries = world[world["name"].isin(["Canada", "Mexico"])].to_crs(4326)
    except Exception as e:                     # deprecated in newer geopandas
        print(f"  (skipping country borders: {e})")
    return {"lon": lon, "lat": lat, "P": P, "states": states,
            "countries": countries, "baseline": base,
            "step": grid_step(lon, lat)}


def region_cells(name, cfg, common):
    """Land cells in the region, that region's cutoffs, and each cell's class.

    The FWI grid is a full lat/lon rectangle, so it carries real values over the
    ocean and over Mexico as well as over CONUS land. Those cells are dropped
    here: they cannot burn, and leaving them in drags the regional cutoffs down
    badly (SoCal's median cell is FWI 83.5 with the ocean in, 99.0 without --
    27% of that box is off-raster water). Land is defined as "covered by the
    WHP raster", i.e. the burnable sample is not nodata; to instead set cutoffs
    over burnable land only, change the mask below to `burn == 1`.

    sample_burnable() is called once here, on the full in-region rectangle, so
    the cached flags stay the same shape the sibling script wrote them in --
    never call it again with the masked subset.

    Returns a dict of the land-masked cell arrays (lon, lat, hist p98, burnable
    flag), the cutoffs, the per-cell class 0-3, and the region's full grid
    origin/shape (taken before the land mask, so an all-water column still
    occupies its column when the classes are rasterized for plotting)."""
    lon, lat, P, step = common["lon"], common["lat"], common["P"], common["step"]
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]
    inreg = (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
    lon_s, lat_s, P_s = lon[inreg], lat[inreg], P[inreg]

    lon0, lat0 = float(lon_s.min()), float(lat_s.min())
    grid = {"lon0": lon0, "lat0": lat0,
            "nx": int(np.rint((lon_s.max() - lon0) / step)) + 1,
            "ny": int(np.rint((lat_s.max() - lat0) / step)) + 1}

    burn = sample_burnable(name, lon_s, lat_s)   # 1 burnable, 0 non, -1 nodata
    land = burn != -1
    lon_s, lat_s, P_s, burn = lon_s[land], lat_s[land], P_s[land], burn[land]

    if FIXED_CUTOFFS is not None:
        cuts = {k: float(v) for k, v in FIXED_CUTOFFS[name].items()}
    else:
        cuts = {k: float(np.percentile(P_s, q))
                for k, q in CLASS_QUANTILES.items()}

    # 0 = none, 1 = low, 2 = medium, 3 = high (highest cutoff the cell meets).
    level = np.zeros(P_s.size, dtype=np.int8)
    for i, s in enumerate(CLASS_ORDER[1:], start=1):
        level[P_s >= cuts[s]] = i
    return {"lon": lon_s, "lat": lat_s, "P": P_s, "burn": burn,
            "cuts": cuts, "level": level, "grid": grid}


def rasterize(r, code, step):
    """Per-cell integer codes painted onto the region's regular grid.

    The cells are a complete lon/lat lattice, so drawing them as an image tiles
    exactly -- unlike scatter markers, whose point size has to be guessed from
    the axes geometry and leaves seams when the layout reflows. Cells with no
    value (ocean, outside CONUS) stay masked and let the basemap show through.
    """
    g = r["grid"]
    col = np.rint((r["lon"] - g["lon0"]) / step).astype(int)
    row = np.rint((r["lat"] - g["lat0"]) / step).astype(int)
    img = np.full((g["ny"], g["nx"]), -1, dtype=np.int16)
    img[row, col] = code
    extent = [g["lon0"] - step / 2, g["lon0"] + (g["nx"] - 0.5) * step,
              g["lat0"] - step / 2, g["lat0"] + (g["ny"] - 0.5) * step]
    return np.ma.masked_less(img, 0), extent


def class_shares(level, mask=None):
    """% of cells (optionally within `mask`) in each class, in CLASS_ORDER."""
    lv = level if mask is None else level[mask]
    if lv.size == 0:
        return [float("nan")] * len(CLASS_ORDER)
    return [100 * (lv == i).mean() for i in range(len(CLASS_ORDER))]


# ----------------------------------------------------------------------------
def plot_region(name, cfg, common, with_burnable):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    states, countries = common["states"], common["countries"]
    b0, b1 = common["baseline"]
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]
    r = region_cells(name, cfg, common)
    burn, cuts, level = r["burn"], r["cuts"], r["level"]
    print(f"[{name}] {r['P'].size:,} in-region land cells; cutoffs "
          + ", ".join(f"{s} >= {cuts[s]:.1f}" for s in CLASS_ORDER[1:]), end="")
    if with_burnable:
        print(f"; {100*(burn == 1).mean():.1f}% burnable", end="")
    print()

    panel_w = 8.0
    panel_h = panel_w * (y1 - y0) / (x1 - x0)
    fig, ax = plt.subplots(figsize=(panel_w, panel_h + 2.4),
                           constrained_layout=True)

    # Basemap under the data: ocean-blue background, land painted back on top of
    # it. State fills use one colour so internal borders stay invisible here;
    # the boundary lines go on at zorder 4.
    ax.set_facecolor(OCEAN_COLOR)
    if countries is not None:
        countries.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)
    states.plot(ax=ax, color=LAND_COLOR, linewidth=0, zorder=0)

    # Codes 0-3 are the classes; 4 is the non-burnable overlay, which replaces
    # the class colour so the two never fight over one cell.
    code = level.astype(np.int16)
    if with_burnable:
        code = np.where(burn == 1, code, 4)
        shares = class_shares(level, burn == 1)   # % over burnable cells only
        denom_lbl = "of burnable cells"
    else:
        shares = class_shares(level)
        denom_lbl = "of land cells"

    cmap = ListedColormap([CLASS_COLORS[s] for s in CLASS_ORDER] + [NB_COLOR])
    img, extent = rasterize(r, code, common["step"])
    ax.imshow(img, extent=extent, origin="lower", interpolation="nearest",
              cmap=cmap, vmin=0, vmax=4, zorder=2)

    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal")

    if countries is not None:
        countries.boundary.plot(ax=ax, color="0.2", linewidth=0.8, zorder=4)
    states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)

    # Legend carries the actual cutoff numbers and the class shares, so the
    # figure is readable without the caption. One row, so the ramp is read in
    # order none -> high.
    def sq(color, lbl):
        return Line2D([0], [0], marker="s", linestyle="None", color=color,
                      markersize=12, label=lbl)
    handles = [sq(CLASS_COLORS["none"],
                  f"none (< {cuts['low']:.0f})  {shares[0]:.0f}%")]
    handles += [sq(CLASS_COLORS[s], f"{s} (≥ {cuts[s]:.0f})  {shares[i]:.0f}%")
                for i, s in enumerate(CLASS_ORDER[1:], start=1)]
    if with_burnable:
        handles.append(sq(NB_COLOR, "non-burnable"))

    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_xticks([]); ax.set_yticks([])
    how = ("cutoffs are this region's "
           f"{CLASS_QUANTILES['low']}th/{CLASS_QUANTILES['medium']}th/"
           f"{CLASS_QUANTILES['high']}th-percentile cells"
           if FIXED_CUTOFFS is None else "fixed cutoffs")
    ax.set_title(f"class labels are FWI cutoffs; share is {denom_lbl}; {how}",
                 fontsize=9)

    fig.legend(handles=handles, loc="outside lower center",
               ncol=len(handles), fontsize=10, frameon=True,
               borderpad=0.8, handletextpad=0.6, columnspacing=1.4)

    suffix = " (burnable mask)" if with_burnable else ""
    fig.suptitle(f"{cfg['label']}: wildfire risk from absolute fire-weather "
                 f"severity\n(historical {b0}-{b1} p{PCTILE} FWI, no trend "
                 f"information){suffix}", fontsize=12)
    out = os.path.join(OUT_DIR,
                       f"{TAG}_{name}{'_burnable' if with_burnable else ''}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


# ----------------------------------------------------------------------------
def write_risk_gpkg(common):
    """One GeoPackage with every in-region cell classified none/low/medium/high.

    Cells are square polygons (cell-center +/- half the grid step) so they tile
    without gaps in GIS. The cutoffs used are carried as columns."""
    import pandas as pd
    from shapely.geometry import box

    half = common["step"] / 2.0

    frames = []
    for name, cfg in REGIONS.items():
        r = region_cells(name, cfg, common)
        lon_s, lat_s, P_s = r["lon"], r["lat"], r["P"]
        burn, cuts, level = r["burn"], r["cuts"], r["level"]
        gdf = gpd.GeoDataFrame(
            {"region": name,
             "lon": lon_s,
             "lat": lat_s,
             "hist_p98_fwi": P_s.astype(float),
             "risk_level": level,
             "risk_class": np.array(CLASS_ORDER, dtype=object)[level],
             "whp_burnable": burn.astype(int),
             "cut_low": cuts["low"],
             "cut_medium": cuts["medium"],
             "cut_high": cuts["high"]},
            geometry=[box(x - half, y - half, x + half, y + half)
                      for x, y in zip(lon_s, lat_s)],
            crs="EPSG:4326")
        counts = {s: int((gdf["risk_class"] == s).sum()) for s in CLASS_ORDER}
        print(f"[{name}] gpkg cells: {counts}")
        frames.append(gdf)

    out = os.path.join(OUT_DIR, f"{TAG}_risk_classes.gpkg")
    gpd.GeoDataFrame(pd.concat(frames, ignore_index=True),
                     crs="EPSG:4326").to_file(
        out, layer="risk_classes", driver="GPKG")
    print(f"  saved -> {out}")


# ----------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    common = load_common()
    for name, cfg in REGIONS.items():
        plot_region(name, cfg, common, with_burnable=False)
    for name, cfg in REGIONS.items():
        plot_region(name, cfg, common, with_burnable=True)
    write_risk_gpkg(common)


if __name__ == "__main__":
    main()
