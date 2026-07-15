"""
Regional wildfire high-risk maps (SoCal + TVA), with and without a burnable /
non-burnable mask.

A follow-on to the wildfire/ undergrounding project. Same future fire-weather
exceedance field and the same thresholds, but here a cell that meets a threshold
is labeled "high risk" (this project is about mapping high wildfire risk, not
undergrounding). Zoomed-in versions of the national high-risk map (the layout
mirrors undergrounding_thresholds.py::_plot_national in the upstream project).
Same 3-panel low/med/high layout: a cell is high risk where the future
exceedance rate A >= a threshold, else grey; the map extent is cropped to a
region and the % is computed over in-region cells.

Regions:
  * socal -- Southern California (standard box; see PROJECT_PLAN).
  * tva   -- TVA coverage area, from tva_bus_geographic_data.csv bus span.

For the *_burnable.png variants, each in-region cell is additionally sampled
against the USFS WHP 90 m raster (EPSG:5070): value 0 = non-burnable
(water/urban/ag/barren), > 0 = burnable. Non-burnable cells are drawn as a
distinct steel-blue underlay so it is clear which high-risk (crimson) cells sit
on burnable land.

Run in the `rev` conda env (has geopandas + rasterio + matplotlib):
    conda activate rev
    python regional_high_risk_maps.py
"""

import os

import numpy as np
from matplotlib.lines import Line2D
import geopandas as gpd
# NOTE: `rasterio` is imported lazily inside sample_burnable() so the plotting
# pipeline can run in the `reeds2` env (no rasterio). The WHP burnable flags are
# cached to an .npz per region; regenerate the cache once in the `rev` env
# (which has rasterio) by deleting the cache files or running:
#   conda run -n rev python regional_high_risk_maps.py

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
NPZ_PATH = ("/projects/rev/projects/ntps/fy26/underground_transmission/"
            "data/fwi/fwi_tc_AminusB_pcthist2000_2014_cnt2025_2059_maps.npz")
STATES_PATH = "/projects/rev/projects/scapes/maps/conus_state_boundaries.gpkg"
WHP_PATH = ("/projects/rev/projects/ntps/fy26/underground_transmission/data/"
            "rasters/wildfire/resampled/wildfire_hazard_potential_conus_90m.tif")

PCTILE = 98                                   # 98th-percentile exceedance field
# Fire-weather exceedance thresholds (days/yr above the historical p-th
# percentile). A cell is HIGH RISK where A >= threshold. These are the same
# thresholds carried over from the upstream wildfire/ project; change them here
# freely -- this project is independent of wildfire/.
THRESHOLDS = {"low": 16.0, "medium": 18.0, "high": 20.0}   # days/yr
SCEN_ORDER = ["low", "medium", "high"]

# Region extents (lon/lat, EPSG:4326). SoCal is a standard box (see
# PROJECT_PLAN). TVA is the bus span padded ~0.25 deg.
REGIONS = {
    "socal": {"label": "Southern California",
              "xlim": (-121.0, -114.0), "ylim": (32.5, 35.5)},
    "tva":   {"label": "TVA coverage area",
              "xlim": (-90.30, -82.55), "ylim": (33.05, 37.51)},
}

OUT_DIR = "/projects/alcaps/bfuchs/wildfire_risk_changes_capacity"
TAG = f"high_risk_A_p{PCTILE}"


# ----------------------------------------------------------------------------
def load_common():
    d = np.load(NPZ_PATH, allow_pickle=True)
    lat, lon = d["lat"], d["lon"]
    pex = list(d["percentiles"].astype(int))
    A = d["A_maps"][pex.index(PCTILE)]        # future exceedance rate, days/yr
    finite = np.isfinite(A)
    lon, lat, A = lon[finite], lat[finite], A[finite]
    print(f"Loaded A p{PCTILE}: {A.size:,} finite cells "
          f"(range {A.min():.1f}-{A.max():.1f} days/yr)")

    states = gpd.read_file(STATES_PATH).to_crs(4326)
    countries = None
    try:                                      # optional context border layer
        world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
        countries = world[world["name"].isin(["Canada", "Mexico"])].to_crs(4326)
    except Exception as e:                     # deprecated in newer geopandas
        print(f"  (skipping country borders: {e})")
    return lon, lat, A, states, countries


def sample_burnable(name, lon_sub, lat_sub):
    """Per-point burnable class from the WHP raster (nearest 90 m cell):
    1 = burnable (WHP > 0), 0 = non-burnable (WHP == 0), -1 = nodata/off-raster.

    Cached to `_burnable_cache_<name>.npz` so this only needs rasterio (the
    `rev` env) on first run; later runs (e.g. in `reeds2`) load the cache."""
    cache = os.path.join(OUT_DIR, f"_burnable_cache_{name}.npz")
    if os.path.exists(cache):
        c = np.load(cache)
        if c["cls"].shape[0] == lon_sub.shape[0]:
            print("  (burnable flags from cache)", end="")
            return c["cls"]

    import rasterio                                   # lazy: rev env only
    from rasterio.warp import transform as warp_transform
    with rasterio.open(WHP_PATH) as r:
        nodata = r.nodata
        xs, ys = warp_transform("EPSG:4326", r.crs.to_string(),
                                list(lon_sub), list(lat_sub))
        vals = np.fromiter((v[0] for v in r.sample(zip(xs, ys))),
                           dtype=np.int64, count=len(xs))
    cls = np.where(vals > 0, 1, 0).astype(np.int8)
    cls[vals == nodata] = -1
    np.savez(cache, cls=cls)
    print("  (burnable flags computed + cached)", end="")
    return cls


# ----------------------------------------------------------------------------
def plot_region(name, cfg, common, with_burnable):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lon, lat, A, states, countries = common
    (x0, x1), (y0, y1) = cfg["xlim"], cfg["ylim"]

    inreg = (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
    lon_s, lat_s, A_s = lon[inreg], lat[inreg], A[inreg]
    print(f"[{name}] {A_s.size:,} in-region cells", end="")

    burn = None
    if with_burnable:
        burn = sample_burnable(name, lon_s, lat_s)   # 1 burnable, 0 non, -1 nodata
        nb = burn == 0
        print(f"; {100*(burn == 1).mean():.1f}% burnable, "
              f"{100*nb.mean():.1f}% non-burnable", end="")
    print()

    n = len(SCEN_ORDER)
    fig, axes = plt.subplots(n, 1, figsize=(8.5, 4.6 * n),
                             constrained_layout=True)
    if n == 1:
        axes = [axes]
    for c, s in enumerate(SCEN_ORDER):
        ax = axes[c]
        thr = THRESHOLDS[s]
        hr = A_s >= thr                           # high-risk cells

        if with_burnable:
            nb = burn == 0
            valid = burn != -1                    # drop off-raster/nodata cells
            bok = valid & (burn == 1)             # burnable cells
            # Non-burnable underlay (steel blue), then burnable grey/crimson.
            ax.scatter(lon_s[nb], lat_s[nb], c="#6b8fb5", s=0.3, marker="s",
                       linewidths=0, rasterized=True)
            ax.scatter(lon_s[bok & ~hr], lat_s[bok & ~hr], c="0.85", s=0.3,
                       marker="s", linewidths=0, rasterized=True)
            ax.scatter(lon_s[bok & hr], lat_s[bok & hr], c="crimson", s=0.3,
                       marker="s", linewidths=0, rasterized=True)
            denom = bok.sum()
            hr_pct = 100 * (bok & hr).sum() / denom if denom else float("nan")
            burn_pct = 100 * (burn == 1).mean()
            title = (f"{s} threshold: A >= {thr:.0f} days/yr  |  "
                     f"{hr_pct:.1f}% of burnable cells high-risk  |  "
                     f"{burn_pct:.1f}% burnable")
        else:
            ax.scatter(lon_s[~hr], lat_s[~hr], c="0.85", s=0.3, marker="s",
                       linewidths=0, rasterized=True)
            ax.scatter(lon_s[hr], lat_s[hr], c="crimson", s=0.3, marker="s",
                       linewidths=0, rasterized=True)
            hr_pct = 100 * hr.mean() if A_s.size else float("nan")
            title = (f"{s} threshold: A >= {thr:.0f} days/yr  |  "
                     f"{hr_pct:.1f}% of cells high-risk")

        def sq(color, lbl):
            return Line2D([0], [0], marker="s", linestyle="None", color=color,
                          markersize=8, label=lbl)
        if with_burnable:
            handles = [sq("crimson", "high risk (A ≥ threshold, burnable)"),
                       sq("0.85", "burnable, not high-risk"),
                       sq("#6b8fb5", "non-burnable (WHP = 0)")]
        else:
            handles = [sq("crimson", "high risk (A ≥ threshold)"),
                       sq("0.85", "not high-risk (A < threshold)")]
        ax.legend(handles=handles, loc="lower left", fontsize=8,
                  framealpha=0.9, borderpad=0.6, handletextpad=0.4).set_zorder(6)

        if countries is not None:
            countries.boundary.plot(ax=ax, color="0.2", linewidth=0.8, zorder=4)
        states.boundary.plot(ax=ax, color="0.35", linewidth=0.4, zorder=4)

        ax.set_title(title, fontsize=10)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])

    suffix = " (burnable mask)" if with_burnable else ""
    fig.suptitle(f"{cfg['label']}: wildfire high-risk extent from future "
                 f"fire-weather exceedance (A > historical p{PCTILE}){suffix}",
                 fontsize=12)
    out = os.path.join(OUT_DIR,
                       f"{TAG}_{name}{'_burnable' if with_burnable else ''}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {out}")


# ----------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    common = load_common()
    for name, cfg in REGIONS.items():
        plot_region(name, cfg, common, with_burnable=False)
    for name, cfg in REGIONS.items():
        plot_region(name, cfg, common, with_burnable=True)


if __name__ == "__main__":
    main()
