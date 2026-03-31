"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 5: Visualisation & Reporting
============================================================
Produces publication-quality figures:
  Fig 1  – Taylor diagram (computed from actual data)
  Fig 2  – Metric heatmap
  Fig 3  – Scatter plots (obs vs product)
  Fig 4  – Seasonal box plots
  Fig 5  – Annual cycle by product
  Fig 6  – Time series at selected stations
  Fig 7  – Zonal metric heatmap (per ecological zone)
  Fig 8  – Zonal annual cycle (one panel per zone)
============================================================
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

from setup_config import CONFIG, PRODUCTS

DATA_DIR    = Path(CONFIG["data_dir"])
FIGURES_DIR = Path(CONFIG["figures_dir"])
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family"   : "DejaVu Sans",
    "font.size"     : 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "figure.dpi"    : 150,
})

# ── Product colours — includes all 6 products ─────────────
PRODUCT_COLORS = {
    "CHIRPS"       : "#1f77b4",   # blue
    "PERSIANN_CDR" : "#ff7f0e",   # orange
    "GPM_IMERG"    : "#d62728",   # red
    "ERA5_LAND"    : "#9467bd",   # purple
    "MERRA2"       : "#e377c2",   # pink
    "TERRACLIMATE" : "#17becf",   # cyan
    "OBS"          : "#000000",   # black
}

OBS_COL = "obs_mm_day"   # correct column name in merged_obs_grid.csv

def _get_products(df: pd.DataFrame, products: list = None) -> list:
    """Return product columns present in df, excluding metadata columns."""
    exclude = {"station_id","year","month", OBS_COL,
               "zone_name","season"}
    if products is not None:
        return [p for p in products if p in df.columns]
    return [c for c in df.columns if c not in exclude]


# ════════════════════════════════════════════════════════════
# Fig 1 — Taylor Diagram (computed from actual data)
# ════════════════════════════════════════════════════════════

def plot_taylor_diagram(merged_df: pd.DataFrame,
                         overall_df: pd.DataFrame = None,
                         products: list = None,
                         save: bool = True):
    """
    Taylor diagram computed from actual obs and sim arrays.
    Uses merged_df to compute obs_std, sim_std, and r directly.
    No random noise — all positions are data-driven.
    """
    products = _get_products(merged_df, products)
    obs      = merged_df[OBS_COL].values

    # Mask NaNs in obs
    obs_mask  = ~np.isnan(obs)
    obs_clean = obs[obs_mask]
    obs_std   = float(np.std(obs_clean, ddof=1))
    obs_mean  = float(np.mean(obs_clean))

    fig = plt.figure(figsize=(9, 8))
    ax  = fig.add_subplot(111, polar=True)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamin(0)
    ax.set_thetamax(90)

    max_std = obs_std * 1.8
    ax.set_rlim(0, max_std)

    # Correlation gridlines
    for r_val in [0.4, 0.6, 0.8, 0.9, 0.95, 0.99]:
        theta = np.arccos(r_val)
        ax.plot([theta, theta], [0, max_std],
                color="grey", lw=0.5, ls="--", alpha=0.5)
        ax.text(theta, max_std * 1.02, f"r={r_val}",
                ha="center", va="bottom", fontsize=7, color="grey",
                rotation=0)

    # Centred RMS circles
    thetas = np.linspace(0, np.pi / 2, 300)
    for rms_val in [0.5, 1.0, 1.5, 2.0, 2.5]:
        radii = np.sqrt(obs_std**2 + rms_val**2
                        - 2 * obs_std * rms_val * np.cos(thetas))
        valid = radii <= max_std
        if valid.any():
            ax.plot(thetas[valid], radii[valid],
                    "--", color="#AED6F1", lw=0.8, alpha=0.8)
            # Label at end of arc
            last = np.where(valid)[0][-1]
            ax.text(thetas[last], radii[last],
                    f" cRMSE={rms_val}", fontsize=7,
                    color="#2E86C1", va="center")

    # Reference point (observations)
    ax.plot(0, obs_std, "k*", ms=16, label="OBS (reference)", zorder=6)

    # Product points — computed from data
    for pname in products:
        sim  = merged_df[pname].values
        mask = ~(np.isnan(obs) | np.isnan(sim))
        if mask.sum() < 3:
            continue
        o, s = obs[mask], sim[mask]
        r_val    = float(np.corrcoef(o, s)[0, 1])
        sim_std  = float(np.std(s, ddof=1))
        theta    = np.arccos(np.clip(r_val, -1, 1))
        color    = PRODUCT_COLORS.get(pname, "black")
        ax.scatter(theta, sim_std, s=120, c=color,
                   label=f"{pname} (r={r_val:.3f})",
                   zorder=5, edgecolors="k", linewidths=0.6)

    ax.set_rlabel_position(135)
    ax.tick_params(labelsize=9)
    ax.set_title("Taylor Diagram — Monthly Precipitation\nWest Africa 2001–2020",
                 pad=20, fontsize=12)
    ax.legend(loc="upper right", bbox_to_anchor=(1.45, 1.1),
              fontsize=9, framealpha=0.9)

    if save:
        p = FIGURES_DIR / "fig1_taylor_diagram.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 2 — Metric heatmap
# ════════════════════════════════════════════════════════════

def plot_metric_heatmap(overall_df: pd.DataFrame,
                         save: bool = True):
    """Overall metric heatmap — all products × all metrics."""
    SHOW  = ["bias","pbias","rmse","r","nse","kge",
             "pod","far","csi","ets","freq_bias"]
    avail = [c for c in SHOW if c in overall_df.columns]
    data  = overall_df[avail].copy().astype(float)

    # Normalise [0,1] — green = better
    norm_data     = data.copy()
    better_higher = {"r","nse","kge","pod","csi","ets"}
    better_lower  = {"rmse","far"}
    for col in avail:
        mn, mx = data[col].min(), data[col].max()
        if mx > mn:
            n = (data[col] - mn) / (mx - mn)
            if col in better_lower or col in {"bias","pbias"}:
                norm_data[col] = 1 - data[col].abs().sub(
                    data[col].abs().min()).div(
                    data[col].abs().max() - data[col].abs().min() + 1e-9)
            else:
                norm_data[col] = n if col in better_higher else 1 - n
        else:
            norm_data[col] = 0.5

    fig, ax = plt.subplots(figsize=(len(avail) * 1.3 + 1,
                                    len(data) * 0.7 + 1.5))
    sns.heatmap(norm_data, annot=data.round(3), fmt=".3f",
                cmap="RdYlGn", linewidths=0.5, ax=ax,
                cbar_kws={"label": "Normalised score (green = better)"},
                vmin=0, vmax=1)
    ax.set_title("Validation Metric Heatmap — All Products", fontsize=13)
    ax.set_ylabel("Product")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=40)

    if save:
        p = FIGURES_DIR / "fig2_metric_heatmap.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 3 — Scatter plots
# ════════════════════════════════════════════════════════════

def plot_scatter_grid(merged_df: pd.DataFrame,
                       products: list = None,
                       save: bool = True):
    """Obs vs gridded scatter for each product."""
    products = _get_products(merged_df, products)
    obs      = merged_df[OBS_COL].values
    mx       = float(np.nanpercentile(obs, 99))

    ncols = min(3, len(products))
    nrows = int(np.ceil(len(products) / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(5 * ncols, 4.5 * nrows),
                              sharex=True, sharey=True)
    axes = np.array(axes).flatten()

    for i, pname in enumerate(products):
        ax  = axes[i]
        sim = merged_df[pname].values
        mask = ~(np.isnan(obs) | np.isnan(sim))
        ox, sx = obs[mask], sim[mask]

        ax.scatter(ox, sx, s=4, alpha=0.3,
                   color=PRODUCT_COLORS.get(pname, "steelblue"))
        ax.plot([0, mx], [0, mx], "k--", lw=1, label="1:1")

        if len(ox) > 2:
            slope, intercept, r, *_ = stats.linregress(ox, sx)
            x_line = np.linspace(0, mx, 100)
            ax.plot(x_line, slope * x_line + intercept,
                    color="red", lw=1.2)
            ax.set_title(f"{pname}  r={r:.3f}", fontsize=10)

        ax.set_xlim(0, mx)
        ax.set_ylim(0, mx)
        ax.set_xlabel("Observed (mm/day)")
        ax.set_ylabel("Gridded (mm/day)")
        ax.grid(True, alpha=0.2)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Scatter: Observed vs Gridded Products", fontsize=14, y=1.01)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / "fig3_scatter_plots.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 4 — Seasonal box plots
# ════════════════════════════════════════════════════════════

SEASON_MAP = {12:"DJF",1:"DJF",2:"DJF",
              3:"MAM",4:"MAM",5:"MAM",
              6:"JJA",7:"JJA",8:"JJA",
              9:"SON",10:"SON",11:"SON"}

def plot_seasonal_boxplot(merged_df: pd.DataFrame,
                           products: list = None,
                           save: bool = True):
    """Seasonal distribution boxplots for each product vs observations."""
    products = _get_products(merged_df, products)

    df = merged_df.copy()
    df["season"] = df["month"].map(SEASON_MAP)

    # Build combined long-format df with obs as one of the series
    long = df.melt(
        id_vars=["station_id","year","month","season", OBS_COL],
        value_vars=products,
        var_name="product", value_name="precip"
    )

    # Add obs rows
    obs_long = df[["station_id","year","month","season", OBS_COL]].copy()
    obs_long = obs_long.rename(columns={OBS_COL: "precip"})
    obs_long["product"] = "OBS"
    combined = pd.concat(
        [long[["season","product","precip"]], obs_long[["season","product","precip"]]],
        ignore_index=True
    )

    order   = ["OBS"] + products
    palette = {k: PRODUCT_COLORS.get(k, "#888888") for k in order}

    fig, axes = plt.subplots(1, 4, figsize=(18, 5), sharey=True)
    for ax, season in zip(axes, ["DJF","MAM","JJA","SON"]):
        sub = combined[combined["season"] == season]
        present = [o for o in order if o in sub["product"].unique()]
        sns.boxplot(
            data    = sub,
            x       = "product",
            y       = "precip",
            order   = present,
            palette = {k: palette[k] for k in present},
            ax      = ax,
            flierprops = dict(marker="o", ms=2, alpha=0.3),
            linewidth  = 0.8,
        )
        ax.set_title(season, fontsize=12)
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, axis="y", alpha=0.2)

    axes[0].set_ylabel("Precipitation (mm/day)")
    fig.suptitle("Seasonal Distribution: Observed vs Products",
                 fontsize=14, y=1.01)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / "fig4_seasonal_boxplots.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 5 — Annual cycle
# ════════════════════════════════════════════════════════════

def plot_annual_cycle(merged_df: pd.DataFrame,
                       products: list = None,
                       save: bool = True):
    """Mean annual cycle — all products vs observations."""
    products = _get_products(merged_df, products)

    fig, ax = plt.subplots(figsize=(10, 5))

    obs_cycle = merged_df.groupby("month")[OBS_COL].mean()
    ax.plot(obs_cycle.index, obs_cycle.values, "ko-",
            ms=6, lw=2, label="OBS (gauge)", zorder=5)

    for pname in products:
        if pname not in merged_df.columns:
            continue
        cycle = merged_df.groupby("month")[pname].mean()
        ax.plot(cycle.index, cycle.values, "-",
                color=PRODUCT_COLORS.get(pname, "grey"),
                lw=1.8, label=pname, alpha=0.9)

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun",
                         "Jul","Aug","Sep","Oct","Nov","Dec"],
                        rotation=30, ha="right")
    ax.set_xlabel("Month")
    ax.set_ylabel("Precipitation (mm/day)")
    ax.set_title("Mean Annual Cycle — All Products vs Observations\n"
                 "West Africa 2001–2020 (15 stations pooled)")
    ax.legend(fontsize=9, ncol=2, framealpha=0.9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / "fig5_annual_cycle.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 6 — Station time series
# ════════════════════════════════════════════════════════════

def plot_station_timeseries(merged_df: pd.DataFrame,
                             station_id: str,
                             products: list = None,
                             save: bool = True):
    """Monthly time series for one station — obs + all products."""
    products = _get_products(merged_df, products)

    sub = merged_df[merged_df["station_id"] == station_id].copy()
    sub = sub.sort_values(["year","month"])
    sub["date"] = pd.to_datetime(
        sub["year"].astype(str) + "-" +
        sub["month"].astype(str).str.zfill(2),
        format="%Y-%m"
    )

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(sub["date"], sub[OBS_COL], "k-",
            lw=1.8, label="OBS", alpha=0.9, zorder=5)

    for pname in products:
        if pname not in sub.columns:
            continue
        ax.plot(sub["date"], sub[pname],
                color=PRODUCT_COLORS.get(pname, "grey"),
                lw=0.9, ls="--", label=pname, alpha=0.85)

    ax.set_xlabel("Date")
    ax.set_ylabel("Precipitation (mm/day)")
    ax.set_title(f"Monthly Precipitation — Station {station_id}")
    ax.legend(fontsize=8, ncol=4, framealpha=0.9)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / f"fig6_timeseries_{station_id}.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 7 — Zonal metric heatmap
# ════════════════════════════════════════════════════════════

def plot_zonal_metric_heatmap(zone_df: pd.DataFrame,
                               metric: str = "kge",
                               save: bool = True):
    """
    Heatmap of one metric per ecological zone × product.
    Default metric: KGE. Change to "r", "nse", "pbias" etc.
    """
    pivot = zone_df.pivot_table(
        index="zone_name", columns="product", values=metric
    )
    # Order zones north → south
    zone_order = ["Saharian","Sahelian","Soudanian",
                  "Guinean","Guineo-Congolean"]
    pivot = pivot.reindex([z for z in zone_order if z in pivot.index])

    fig, ax = plt.subplots(figsize=(len(pivot.columns) * 1.4 + 1,
                                    len(pivot) * 0.9 + 1.5))
    vmin = -1 if metric in ["kge","nse","r"] else None
    vmax =  1 if metric in ["kge","nse","r","pod","csi","far"] else None
    cmap = "RdYlGn" if metric not in ["far","rmse","bias","pbias"]            else "RdYlGn_r"

    sns.heatmap(pivot.astype(float), annot=True, fmt=".3f",
                cmap=cmap, linewidths=0.5, ax=ax,
                vmin=vmin, vmax=vmax,
                cbar_kws={"label": metric.upper()})
    ax.set_title(f"{metric.upper()} by Ecological Zone × Product",
                 fontsize=13)
    ax.set_xlabel("Product")
    ax.set_ylabel("Ecological Zone")
    ax.tick_params(axis="x", rotation=40)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / f"fig7_zonal_heatmap_{metric}.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# Fig 8 — Zonal annual cycle (one panel per zone)
# ════════════════════════════════════════════════════════════

def plot_zonal_annual_cycle(merged_df: pd.DataFrame,
                             zone_df:   pd.DataFrame,
                             products:  list = None,
                             save:      bool = True):
    """
    Annual cycle per ecological zone.
    One subplot per zone — all products + obs on each panel.
    Requires zone assignments in zone_df (zone_name × station mapping).
    """
    products = _get_products(merged_df, products)

    # Get station→zone mapping from zone_df
    station_zone = (zone_df[["zone_name"]]
                    .drop_duplicates()
                    if "station_id" not in zone_df.columns
                    else zone_df[["station_id","zone_name"]]
                         .drop_duplicates()
                         .set_index("station_id")["zone_name"]
                         .to_dict())

    if isinstance(station_zone, dict):
        df = merged_df.copy()
        df["zone_name"] = df["station_id"].map(station_zone)
    else:
        # Fallback: assign by latitude using hardcoded coords
        STATION_LAT = {
            "WA001":14.73,"WA002":12.65,"WA003":12.36,"WA004":13.51,
            "WA005": 9.07,"WA006": 5.56,"WA007": 5.35,"WA008": 9.53,
            "WA009": 8.49,"WA010": 6.30,"WA011": 6.13,"WA012": 6.37,
            "WA013":12.05,"WA014": 6.69,"WA015":13.45,
        }
        def lat_to_zone(sid):
            lat = STATION_LAT.get(sid, 10)
            if lat > 18: return "Saharian"
            if lat > 14: return "Sahelian"
            if lat > 10: return "Soudanian"
            if lat > 7:  return "Guinean"
            return "Guineo-Congolean"
        df = merged_df.copy()
        df["zone_name"] = df["station_id"].map(lat_to_zone)

    zones = ["Saharian","Sahelian","Soudanian","Guinean","Guineo-Congolean"]
    zones = [z for z in zones if z in df["zone_name"].unique()]

    fig, axes = plt.subplots(1, len(zones),
                              figsize=(4 * len(zones), 5),
                              sharey=False)
    if len(zones) == 1:
        axes = [axes]

    for ax, zone in zip(axes, zones):
        sub = df[df["zone_name"] == zone]
        if sub.empty:
            ax.set_visible(False)
            continue

        obs_cycle = sub.groupby("month")[OBS_COL].mean()
        ax.plot(obs_cycle.index, obs_cycle.values, "ko-",
                ms=5, lw=2, label="OBS", zorder=5)

        for pname in products:
            if pname not in sub.columns:
                continue
            cycle = sub.groupby("month")[pname].mean()
            ax.plot(cycle.index, cycle.values, "-",
                    color=PRODUCT_COLORS.get(pname, "grey"),
                    lw=1.5, label=pname, alpha=0.9)

        ax.set_title(zone, fontsize=10, fontweight="bold")
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(["J","F","M","A","M","J",
                             "J","A","S","O","N","D"],
                            fontsize=7)
        ax.set_xlabel("Month", fontsize=9)
        ax.set_ylabel("mm/day", fontsize=9)
        ax.grid(True, alpha=0.2)

    # Shared legend below figure
    handles = [mpatches.Patch(color="black", label="OBS")] + [
        mpatches.Patch(color=PRODUCT_COLORS.get(p, "grey"), label=p)
        for p in products
    ]
    fig.legend(handles=handles, loc="lower center",
               ncol=len(products) + 1, fontsize=9,
               bbox_to_anchor=(0.5, -0.08), framealpha=0.9)
    fig.suptitle("Annual Cycle by Ecological Zone — All Products",
                 fontsize=13, y=1.02)
    fig.tight_layout()

    if save:
        p = FIGURES_DIR / "fig8_zonal_annual_cycle.png"
        fig.savefig(p, bbox_inches="tight")
        print(f"  Saved: {p.name}")
    return fig


# ════════════════════════════════════════════════════════════
# § ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  VISUALISATION — Step 5")
    print("=" * 60)
    print(f"  DATA_DIR    : {DATA_DIR}")
    print(f"  FIGURES_DIR : {FIGURES_DIR}")

    # ── Load data ─────────────────────────────────────────────
    merged  = pd.read_csv(DATA_DIR / "merged_obs_grid.csv")
    overall = pd.read_csv(DATA_DIR / "validation_overall.csv",
                           index_col="product")

    zone_path = DATA_DIR / "validation_by_zone.csv"
    zone_df   = pd.read_csv(zone_path) if zone_path.exists() else None

    products = _get_products(merged)
    print(f"  Products found : {products}")
    print(f"  Merged shape   : {merged.shape}")
    print(f"  Zonal data     : {'yes' if zone_df is not None else 'not found — run validation_metrics.py first'}")

    print("\nGenerating figures …")

    print("  Fig 1 — Taylor diagram …")
    plot_taylor_diagram(merged, overall)

    print("  Fig 2 — Metric heatmap …")
    plot_metric_heatmap(overall)

    print("  Fig 3 — Scatter plots …")
    plot_scatter_grid(merged, products)

    print("  Fig 4 — Seasonal boxplots …")
    plot_seasonal_boxplot(merged, products)

    print("  Fig 5 — Annual cycle …")
    plot_annual_cycle(merged, products)

    print("  Fig 6 — Station time series (all 15 stations) …")
    for stn in merged["station_id"].unique():
        plot_station_timeseries(merged, stn, products)

    if zone_df is not None:
        print("  Fig 7 — Zonal metric heatmaps (KGE, r, NSE, PBIAS) …")
        for metric in ["kge", "r", "nse", "pbias"]:
            if metric in zone_df.columns:
                plot_zonal_metric_heatmap(zone_df, metric=metric)

        print("  Fig 8 — Zonal annual cycle …")
        plot_zonal_annual_cycle(merged, zone_df, products)
    else:
        print("  ⚠  Skipping zonal figures — run validation_metrics.py first")

    print("\n" + "=" * 60)
    print("  ALL FIGURES SAVED")
    print("=" * 60)
    print(f"  Location: {FIGURES_DIR}")
