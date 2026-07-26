"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Threshold Sensitivity Analysis
============================================================
Tests wet/dry detection metrics (POD, FAR, CSI, ETS) at
multiple rainfall thresholds across:
  - All products (vs GPCC obs)
  - All ecological zones
  - All West Africa (pooled)

Thresholds tested: 0.1, 0.5, 1.0, 2.0, 5.0 mm/day

OUTPUTS (saved to FIGURES_DIR)
────────────────────────────────
  fig_thresh_01_heatmap_csi.png   — CSI heatmap: zone × product per threshold
  fig_thresh_02_heatmap_pod.png   — POD heatmap
  fig_thresh_03_heatmap_far.png   — FAR heatmap
  fig_thresh_04_lineplots.png     — POD/FAR/CSI vs threshold per zone (all products)
  fig_thresh_05_product_lines.png — CSI vs threshold per product (all zones)
  fig_thresh_06_west_africa.png   — West Africa pooled: all metrics vs threshold
  fig_thresh_07_ets_heatmap.png   — ETS heatmap: zone × product per threshold

HOW TO RUN
───────────
  python threshold_sensitivity.py

Reads merged_obs_grid.csv from DATA_DIR.
============================================================
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import sys, types
sys.path.insert(0, str(Path(__file__).parent))

# ── Load CONFIG ───────────────────────────────────────────
def _load_config():
    src = Path(__file__).parent / "setup_config.py"
    if not src.exists():
        return None
    with open(src, encoding="utf-8") as f:
        code = f.read()
    lines = [
        "pass" if any(x in ln for x in
                      ["import ee","import geemap","ee.Initialize","ee.Authenticate"])
        else ln
        for ln in code.splitlines()
    ]
    mod = types.ModuleType("cfg_local")
    try:
        exec(compile("\n".join(lines), "setup_config.py", "exec"), mod.__dict__)
        return mod
    except Exception:
        return None

_cfg = _load_config()
if _cfg and hasattr(_cfg, "CONFIG"):
    CONFIG = _cfg.CONFIG
else:
    CONFIG = {
        "data_dir"   : r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR",
        "figures_dir": r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\figures",
    }

DATA_DIR    = Path(CONFIG["data_dir"])
FIGURES_DIR = Path(CONFIG["figures_dir"])
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

OBS_COL = "obs_mm_day"

# ── Plotting style ─────────────────────────────────────────
plt.rcParams.update({
    "font.family"   : "DejaVu Sans",
    "font.size"     : 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "figure.dpi"    : 150,
})

PRODUCT_COLORS = {
    "CHIRPS"       : "#1f77b4",
    "ERA5_LAND"    : "#9467bd",
    "GPM_IMERG"    : "#d62728",
    "MERRA2"       : "#e377c2",
    "PERSIANN_CDR" : "#ff7f0e",
    "TERRACLIMATE" : "#17becf",
}

ZONE_ORDER = [
    "Saharian", "Sahelian", "Soudanian",
    "Guinean", "Guineo-Congolean"
]

ZONE_COLORS = {
    "Saharian"        : "#C8A96E",
    "Sahelian"        : "#E8A838",
    "Soudanian"       : "#CC6600",
    "Guinean"         : "#78C850",
    "Guineo-Congolean": "#1A6B1A",
}

STATION_ZONE = {
    "WA001": "Sahelian",       "WA002": "Sahelian",
    "WA003": "Sahelian",       "WA004": "Sahelian",
    "WA005": "Soudanian",      "WA006": "Guineo-Congolean",
    "WA007": "Guineo-Congolean","WA008": "Soudanian",
    "WA009": "Guinean",        "WA010": "Guinean",
    "WA011": "Guineo-Congolean","WA012": "Guineo-Congolean",
    "WA013": "Soudanian",      "WA014": "Guinean",
    "WA015": "Sahelian",       "WA016": "Saharian",
}

THRESHOLDS = [0.1, 0.5, 1.0, 2.0, 5.0]


# ════════════════════════════════════════════════════════════
# § 1  CORE CATEGORICAL METRICS
# ════════════════════════════════════════════════════════════

def categorical_metrics(obs: np.ndarray, sim: np.ndarray,
                         threshold: float) -> dict:
    """
    Compute POD, FAR, CSI, ETS, FREQ_BIAS for one
    obs/sim pair at one threshold.
    Returns dict with NaN for degenerate cases.
    """
    mask = ~(np.isnan(obs) | np.isnan(sim))
    o, s = obs[mask], sim[mask]
    if len(o) < 3:
        return {m: np.nan for m in
                ["pod","far","csi","ets","freq_bias",
                 "hits","misses","false_al","correct_neg"]}

    ow = o >= threshold
    sw = s >= threshold
    h  = int(np.sum( ow &  sw))
    ms = int(np.sum( ow & ~sw))
    fa = int(np.sum(~ow &  sw))
    cn = int(np.sum(~ow & ~sw))
    tot = h + ms + fa + cn

    pod  = h / (h+ms)       if (h+ms)  > 0 else np.nan
    far  = fa / (h+fa)      if (h+fa)  > 0 else np.nan
    csi  = h / (h+ms+fa)    if (h+ms+fa) > 0 else np.nan
    hr   = ((h+ms)*(h+fa)) / tot if tot > 0 else 0
    den  = h+ms+fa - hr
    ets  = (h-hr)/den        if den    > 0 else np.nan
    fb   = (h+fa)/(h+ms)    if (h+ms) > 0 else np.nan

    return {
        "pod"      : round(float(pod), 4),
        "far"      : round(float(far), 4),
        "csi"      : round(float(csi), 4),
        "ets"      : round(float(ets), 4),
        "freq_bias": round(float(fb),  4),
        "hits": h, "misses": ms,
        "false_al": fa, "correct_neg": cn,
    }


# ════════════════════════════════════════════════════════════
# § 2  COMPUTE RESULTS TABLE
# ════════════════════════════════════════════════════════════

def compute_threshold_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute POD/FAR/CSI/ETS for every combination of:
      threshold × product × zone
    plus West Africa pooled (zone = 'All West Africa').

    Returns tidy DataFrame.
    """
    df = df.copy()
    df["zone_name"] = df["station_id"].map(STATION_ZONE)
    df = df.dropna(subset=["zone_name"])

    products = [c for c in df.columns
                if c not in {"station_id","year","month",
                              OBS_COL,"zone_name"}]

    records = []

    for thresh in THRESHOLDS:
        # ── Per zone ─────────────────────────────────────
        for zone in ZONE_ORDER:
            sub = df[df["zone_name"] == zone]
            if sub.empty:
                continue
            obs = sub[OBS_COL].values
            for p in products:
                m = categorical_metrics(obs, sub[p].values, thresh)
                records.append({
                    "threshold": thresh,
                    "zone"     : zone,
                    "product"  : p,
                    **{k: m[k] for k in
                       ["pod","far","csi","ets","freq_bias"]},
                })

        # ── West Africa pooled ────────────────────────────
        obs_all = df[OBS_COL].values
        for p in products:
            m = categorical_metrics(obs_all, df[p].values, thresh)
            records.append({
                "threshold": thresh,
                "zone"     : "All West Africa",
                "product"  : p,
                **{k: m[k] for k in
                   ["pod","far","csi","ets","freq_bias"]},
            })

    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════════
# § 3  FIGURES
# ════════════════════════════════════════════════════════════

def _save(fig, name):
    p = FIGURES_DIR / name
    fig.savefig(p, bbox_inches="tight")
    print(f"  Saved: {p.name}")
    plt.close(fig)


# ── Fig 1–3, 7: Heatmaps per threshold ───────────────────

def plot_metric_heatmaps(results: pd.DataFrame):
    """
    One figure per metric. Each figure has one subplot per threshold,
    showing zone × product heatmap.
    """
    metrics_cfg = {
        "csi": ("CSI (Critical Success Index)",
                "RdYlGn", 0, 1,
                "fig_thresh_01_heatmap_csi.png"),
        "pod": ("POD (Probability of Detection)",
                "RdYlGn", 0, 1,
                "fig_thresh_02_heatmap_pod.png"),
        "far": ("FAR (False Alarm Ratio)",
                "RdYlGn_r", 0, 1,
                "fig_thresh_03_heatmap_far.png"),
        "ets": ("ETS (Equitable Threat Score)",
                "RdYlGn", -0.2, 1,
                "fig_thresh_07_heatmap_ets.png"),
    }

    zones_plot = ZONE_ORDER + ["All West Africa"]

    for metric, (title, cmap, vmin, vmax, fname) in metrics_cfg.items():
        n = len(THRESHOLDS)
        fig, axes = plt.subplots(1, n,
                                  figsize=(4.5*n, 5),
                                  sharey=True)

        for ax, thresh in zip(axes, THRESHOLDS):
            sub = results[results["threshold"] == thresh]
            pivot = sub.pivot_table(
                index="zone", columns="product",
                values=metric
            )
            # Reorder rows
            order = [z for z in zones_plot if z in pivot.index]
            pivot = pivot.reindex(order)

            sns.heatmap(
                pivot.astype(float),
                annot=True, fmt=".2f",
                cmap=cmap, vmin=vmin, vmax=vmax,
                linewidths=0.4, ax=ax,
                cbar=(ax == axes[-1]),
                annot_kws={"size": 8},
            )
            ax.set_title(f"≥{thresh} mm/day", fontsize=10)
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=40, labelsize=8)
            ax.tick_params(axis="y", labelsize=8)
            if ax != axes[0]:
                ax.set_ylabel("")

        fig.suptitle(f"Threshold Sensitivity — {title}\nWest Africa 2001–2020",
                     fontsize=13, y=1.02)
        fig.tight_layout()
        _save(fig, fname)


# ── Fig 4: Line plots — metric vs threshold per zone ─────

def plot_zone_lineplots(results: pd.DataFrame):
    """
    For each zone: 3-panel subplot (POD, FAR, CSI) showing
    all products as lines across thresholds.
    """
    zones_plot = ZONE_ORDER + ["All West Africa"]
    products   = results["product"].unique()
    metrics    = [("pod","POD"), ("far","FAR"), ("csi","CSI")]

    nz = len(zones_plot)
    fig, axes = plt.subplots(nz, 3,
                              figsize=(14, 2.8*nz),
                              sharey=False)

    for zi, zone in enumerate(zones_plot):
        sub = results[results["zone"] == zone]
        if sub.empty:
            for ax in axes[zi]:
                ax.set_visible(False)
            continue

        for mi, (metric, mlabel) in enumerate(metrics):
            ax = axes[zi][mi]
            for p in products:
                psub = sub[sub["product"] == p].sort_values("threshold")
                ax.plot(
                    psub["threshold"], psub[metric],
                    "o-", lw=1.8, ms=5,
                    color=PRODUCT_COLORS.get(p, "grey"),
                    label=p, alpha=0.9
                )

            ax.set_xscale("log")
            ax.set_xticks(THRESHOLDS)
            ax.set_xticklabels([str(t) for t in THRESHOLDS], fontsize=8)
            ax.set_xlabel("Threshold (mm/day)", fontsize=9)
            ax.set_ylabel(mlabel, fontsize=9)
            ax.grid(True, alpha=0.25, which="both")
            ax.set_ylim(-0.05, 1.05)
            if metric == "far":
                ax.set_ylim(-0.05, 0.6)

            if zi == 0:
                ax.set_title(mlabel, fontsize=11, fontweight="bold")
            if mi == 0:
                c = ZONE_COLORS.get(zone, "#555555")
                ax.set_ylabel(zone, fontsize=9,
                               color=c, fontweight="bold")

    # Shared legend
    handles = [
        plt.Line2D([0],[0], color=PRODUCT_COLORS.get(p,"grey"),
                   lw=2, marker="o", ms=5, label=p)
        for p in products
    ]
    fig.legend(handles=handles, loc="lower center",
               ncol=len(products), fontsize=9,
               bbox_to_anchor=(0.5, -0.02), framealpha=0.9)
    fig.suptitle("POD / FAR / CSI vs Threshold — by Zone & Product\nWest Africa 2001–2020",
                 fontsize=13, y=1.01)
    fig.tight_layout()
    _save(fig, "fig_thresh_04_zone_lineplots.png")


# ── Fig 5: CSI vs threshold — per product, all zones ─────

def plot_product_lines(results: pd.DataFrame):
    """
    One subplot per product. Lines = zones. X = threshold, Y = CSI.
    Shows how each product's CSI varies across zones.
    """
    products   = results["product"].unique()
    zones_plot = ZONE_ORDER + ["All West Africa"]

    ncols = 3
    nrows = int(np.ceil(len(products) / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(5*ncols, 4*nrows),
                              sharey=True, sharex=True)
    axes = np.array(axes).flatten()

    for i, p in enumerate(products):
        ax  = axes[i]
        sub = results[results["product"] == p]
        for zone in zones_plot:
            zsub = sub[sub["zone"] == zone].sort_values("threshold")
            if zsub.empty:
                continue
            ls = "--" if zone == "All West Africa" else "-"
            ax.plot(
                zsub["threshold"], zsub["csi"],
                ls, lw=1.8, ms=5, marker="o",
                color=ZONE_COLORS.get(zone, "#555555"),
                label=zone, alpha=0.9
            )
        ax.set_xscale("log")
        ax.set_xticks(THRESHOLDS)
        ax.set_xticklabels([str(t) for t in THRESHOLDS], fontsize=8)
        ax.set_title(p, fontsize=11, fontweight="bold",
                     color=PRODUCT_COLORS.get(p, "black"))
        ax.set_xlabel("Threshold (mm/day)", fontsize=9)
        ax.set_ylabel("CSI", fontsize=9)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.25, which="both")

    for j in range(i+1, len(axes)):
        axes[j].set_visible(False)

    handles = [
        plt.Line2D([0],[0], color=ZONE_COLORS.get(z,"grey"),
                   lw=2, marker="o", ms=5,
                   linestyle="--" if z=="All West Africa" else "-",
                   label=z)
        for z in zones_plot
    ]
    fig.legend(handles=handles, loc="lower center",
               ncol=3, fontsize=9,
               bbox_to_anchor=(0.5, -0.04), framealpha=0.9)
    fig.suptitle("CSI vs Threshold — by Product across Ecological Zones\nWest Africa 2001–2020",
                 fontsize=13, y=1.01)
    fig.tight_layout()
    _save(fig, "fig_thresh_05_product_csi_lines.png")


# ── Fig 6: West Africa pooled — all metrics ───────────────

def plot_west_africa_summary(results: pd.DataFrame):
    """
    West Africa pooled: 4-panel figure showing POD, FAR, CSI, ETS
    vs threshold for all products on the same axes.
    """
    sub      = results[results["zone"] == "All West Africa"]
    products = sub["product"].unique()
    metrics  = [
        ("pod", "POD",  (0.3, 1.05)),
        ("far", "FAR",  (-0.02, 0.35)),
        ("csi", "CSI",  (0.3, 1.05)),
        ("ets", "ETS",  (0.2, 1.05)),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=False)
    axes = axes.flatten()

    for ax, (metric, label, ylim) in zip(axes, metrics):
        for p in products:
            psub = sub[sub["product"] == p].sort_values("threshold")
            ax.plot(
                psub["threshold"], psub[metric],
                "o-", lw=2, ms=6,
                color=PRODUCT_COLORS.get(p, "grey"),
                label=p, alpha=0.9
            )

        # Mark WMO standard threshold
        ax.axvline(x=1.0, color="black", lw=1, ls="--", alpha=0.5,
                   label="WMO standard (1.0)")

        ax.set_xscale("log")
        ax.set_xticks(THRESHOLDS)
        ax.set_xticklabels([f"{t}" for t in THRESHOLDS])
        ax.set_xlabel("Threshold (mm/day)")
        ax.set_ylabel(label)
        ax.set_title(label, fontsize=12, fontweight="bold")
        ax.set_ylim(ylim)
        ax.grid(True, alpha=0.25, which="both")

    handles = [
        plt.Line2D([0],[0], color=PRODUCT_COLORS.get(p,"grey"),
                   lw=2, marker="o", ms=6, label=p)
        for p in products
    ]
    handles.append(
        plt.Line2D([0],[0], color="black", lw=1, ls="--",
                   label="WMO standard (1.0 mm/day)")
    )
    fig.legend(handles=handles, loc="lower center",
               ncol=4, fontsize=9,
               bbox_to_anchor=(0.5, -0.04), framealpha=0.9)
    fig.suptitle(
        "Threshold Sensitivity — All West Africa (Pooled)\n"
        "POD · FAR · CSI · ETS vs Threshold, All Products 2001–2020",
        fontsize=13
    )
    fig.tight_layout()
    _save(fig, "fig_thresh_06_west_africa_summary.png")


# ── Fig 8: Radar/spider chart — zone profile ─────────────

def plot_zone_radar(results: pd.DataFrame, threshold: float = 1.0):
    """
    Radar chart: one spoke per metric (POD, 1-FAR, CSI, ETS),
    one polygon per zone, for each product at the standard threshold.
    One subplot per product.
    """
    sub      = results[
        (results["threshold"] == threshold) &
        (results["zone"] != "All West Africa")
    ]
    products = sub["product"].unique()
    zones    = [z for z in ZONE_ORDER if z in sub["zone"].unique()]

    # Metrics on radar (invert FAR so higher = better everywhere)
    spoke_labels = ["POD", "1−FAR", "CSI", "ETS"]

    def get_values(row):
        ets = max(0, row["ets"]) if not np.isnan(row["ets"]) else 0
        return [
            row["pod"]      if not np.isnan(row["pod"]) else 0,
            1 - row["far"]  if not np.isnan(row["far"]) else 0,
            row["csi"]      if not np.isnan(row["csi"]) else 0,
            ets,
        ]

    N      = len(spoke_labels)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    ncols = 3
    nrows = int(np.ceil(len(products) / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(5.5*ncols, 4.5*nrows),
                              subplot_kw=dict(polar=True))
    axes = np.array(axes).flatten()

    for i, p in enumerate(products):
        ax   = axes[i]
        psub = sub[sub["product"] == p]

        for zone in zones:
            row = psub[psub["zone"] == zone]
            if row.empty:
                continue
            vals   = get_values(row.iloc[0])
            vals  += vals[:1]
            color  = ZONE_COLORS.get(zone, "#555555")
            ax.plot(angles, vals, "o-", lw=1.5, color=color,
                    label=zone, alpha=0.85)
            ax.fill(angles, vals, alpha=0.07, color=color)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(spoke_labels, fontsize=9)
        ax.set_ylim(0, 1)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0.25","0.5","0.75","1.0"], fontsize=7)
        ax.set_title(p, fontsize=11, fontweight="bold",
                     pad=14, color=PRODUCT_COLORS.get(p,"black"))
        ax.grid(True, alpha=0.3)

    for j in range(i+1, len(axes)):
        axes[j].set_visible(False)

    handles = [
        plt.Line2D([0],[0], color=ZONE_COLORS.get(z,"grey"),
                   lw=2, marker="o", ms=5, label=z)
        for z in zones
    ]
    fig.legend(handles=handles, loc="lower center",
               ncol=3, fontsize=9,
               bbox_to_anchor=(0.5, -0.04), framealpha=0.9)
    fig.suptitle(
        f"Categorical Skill by Zone — Radar Chart\n"
        f"Threshold = {threshold} mm/day | West Africa 2001–2020",
        fontsize=13, y=1.01
    )
    fig.tight_layout()
    _save(fig, f"fig_thresh_08_radar_thresh{threshold}.png")


# ════════════════════════════════════════════════════════════
# § 4  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "="*60)
    print("  THRESHOLD SENSITIVITY ANALYSIS")
    print("="*60)
    print(f"  DATA_DIR    : {DATA_DIR}")
    print(f"  FIGURES_DIR : {FIGURES_DIR}")
    print(f"  Thresholds  : {THRESHOLDS} mm/day")

    # Load merged dataset
    merged_path = DATA_DIR / "merged_obs_grid.csv"
    if not merged_path.exists():
        raise FileNotFoundError(
            f"merged_obs_grid.csv not found at {merged_path}\n"
            "Run merge_extractions.py first."
        )
    merged = pd.read_csv(merged_path)

    # Rename legacy column if needed
    if "obs" in merged.columns and OBS_COL not in merged.columns:
        merged = merged.rename(columns={"obs": OBS_COL})

    print(f"  Loaded: {merged_path.name}  shape={merged.shape}")

    products = [c for c in merged.columns
                if c not in {"station_id","year","month",OBS_COL}]
    print(f"  Products: {products}")

    # Compute results table
    print("\n  Computing threshold sensitivity table...")
    results = compute_threshold_table(merged)
    print(f"  Results table shape: {results.shape}")

    # Save results table
    results_path = DATA_DIR / "threshold_sensitivity.csv"
    results.to_csv(results_path, index=False)
    print(f"  Saved: {results_path.name}")

    # Generate figures
    print("\n  Generating figures...")

    print("  Fig 1–3, 7 — metric heatmaps (CSI / POD / FAR / ETS)...")
    plot_metric_heatmaps(results)

    print("  Fig 4 — zone line plots (POD / FAR / CSI vs threshold)...")
    plot_zone_lineplots(results)

    print("  Fig 5 — product CSI lines (all zones)...")
    plot_product_lines(results)

    print("  Fig 6 — West Africa pooled summary...")
    plot_west_africa_summary(results)

    print("  Fig 8 — radar charts at 1.0 mm/day threshold...")
    plot_zone_radar(results, threshold=1.0)

    print("\n" + "="*60)
    print("  DONE — all threshold sensitivity figures saved")
    print("="*60)
    print(f"  Location: {FIGURES_DIR}")
    print("""
  Output files:
    threshold_sensitivity.csv         ← full results table
    fig_thresh_01_heatmap_csi.png     ← CSI: zone × product per threshold
    fig_thresh_02_heatmap_pod.png     ← POD heatmap
    fig_thresh_03_heatmap_far.png     ← FAR heatmap
    fig_thresh_04_zone_lineplots.png  ← POD/FAR/CSI vs threshold per zone
    fig_thresh_05_product_csi_lines.png ← CSI per product across zones
    fig_thresh_06_west_africa_summary.png ← West Africa pooled
    fig_thresh_07_heatmap_ets.png     ← ETS heatmap
    fig_thresh_08_radar_thresh1.0.png ← Radar chart at 1.0 mm/day
    """)
