"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 3: Statistical Validation Metrics
============================================================
Runs ENTIRELY LOCALLY — no GEE calls.
Reads merged_obs_grid.csv produced by merge_extractions.py.

OUTPUTS (all saved to DATA_DIR)
────────────────────────────────
  validation_per_station.csv    — 8 continuous + 5 categorical
                                  metrics per station × product
  validation_overall.csv        — pooled metrics per product
  validation_by_season.csv      — metrics per season × product
  validation_by_zone.csv        — metrics per eco zone × product
  product_ranking.csv           — composite score ranking
  product_ranking_by_zone.csv   — ranking per ecological zone

HOW TO RUN
───────────
  python validation_metrics.py
============================================================
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point

# ── No GEE imports — read CONFIG directly ─────────────────
import sys, os
sys.path.insert(0, str(Path(__file__).parent))

# Read CONFIG without triggering GEE initialisation
# We only need data_dir, start_date, end_date from CONFIG
import importlib.util, types

def _load_config_only():
    """Load setup_config.py but skip the ee.Initialize() call."""
    src_path = Path(__file__).parent / "setup_config.py"
    if not src_path.exists():
        raise FileNotFoundError(f"setup_config.py not found at {src_path}")
    with open(src_path) as f:
        src = f.read()
    # Strip GEE-dependent lines
    lines = []
    skip_next = False
    for line in src.splitlines():
        if any(x in line for x in [
            "import ee", "import geemap", "ee.Initialize",
            "ee.Authenticate", "geemap"
        ]):
            lines.append("# (skipped for local run)")
        elif "try:" in line and "ee.Initialize" in "".join(
                src.splitlines()[src.splitlines().index(line):
                                  src.splitlines().index(line)+3]):
            lines.append("# (skipped for local run)")
        else:
            lines.append(line)
    mod_src = "\n".join(lines)
    mod = types.ModuleType("setup_config_local")
    try:
        exec(compile(mod_src, "setup_config.py", "exec"), mod.__dict__)
    except Exception:
        pass
    return mod

try:
    _cfg_mod = _load_config_only()
    CONFIG         = _cfg_mod.CONFIG
    PRODUCTS       = _cfg_mod.PRODUCTS
    RAIN_THRESHOLD = getattr(_cfg_mod, "RAIN_THRESHOLD", 1.0) or 1.0
    METRICS        = getattr(_cfg_mod, "METRICS", [])
except Exception as e:
    print(f"  ⚠  Could not load setup_config.py ({e})")
    print("     Using fallback defaults.")
    CONFIG = {
        "data_dir"   : "outputs/precipitation_assessment/data",
        "figures_dir": "outputs/precipitation_assessment/figures",
        "start_date" : "2001-01-01",
        "end_date"   : "2020-12-31",
    }
    RAIN_THRESHOLD = 1.0

DATA_DIR    = Path(CONFIG["data_dir"])
FIGURES_DIR = Path(CONFIG["figures_dir"])
START_YEAR  = int(CONFIG["start_date"][:4])
END_YEAR    = int(CONFIG["end_date"][:4])

# Rain threshold — override None with 1.0 mm/day (WMO convention)
RAIN_THRESHOLD = RAIN_THRESHOLD if RAIN_THRESHOLD else 1.0

# ── Product list (all products in merged CSV) ─────────────
ALL_PRODUCTS = [
    "CHIRPS", "ERA5_LAND", "GPM_IMERG",
    "MERRA2", "PERSIANN_CDR", "TERRACLIMATE",
]

# ── Seasons ───────────────────────────────────────────────
SEASONS = {
    "DJF": [12, 1, 2],
    "MAM": [3, 4, 5],
    "JJA": [6, 7, 8],
    "SON": [9, 10, 11],
}


# ════════════════════════════════════════════════════════════
# § 1  CORE METRIC FUNCTIONS
# ════════════════════════════════════════════════════════════

def compute_continuous_metrics(obs: np.ndarray,
                                sim: np.ndarray) -> dict:
    """
    Compute 8 continuous verification statistics.
    obs, sim : 1-D arrays (mm/day). NaNs are dropped automatically.
    """
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]
    n = len(obs)

    if n < 3:
        return {m: np.nan for m in
                ["n","bias","pbias","mae","rmse","r","nse","kge"]}

    bias  = float(np.mean(sim - obs))
    pbias = float(100 * np.sum(sim - obs) / np.sum(obs))             if np.sum(obs) != 0 else np.nan
    mae   = float(np.mean(np.abs(sim - obs)))
    rmse  = float(np.sqrt(np.mean((sim - obs) ** 2)))

    r = float(np.corrcoef(obs, sim)[0, 1])         if obs.std() > 1e-10 and sim.std() > 1e-10 else np.nan

    nse = float(1 - np.sum((obs - sim) ** 2) /
                np.sum((obs - np.mean(obs)) ** 2))           if np.sum((obs - np.mean(obs)) ** 2) > 0 else np.nan

    alpha = sim.std() / obs.std() if obs.std() > 0 else np.nan
    beta  = sim.mean() / obs.mean() if obs.mean() > 0 else np.nan
    kge   = float(1 - np.sqrt((r - 1)**2 +
                               (alpha - 1)**2 +
                               (beta - 1)**2))             if not any(np.isnan([r, alpha, beta])) else np.nan

    return {
        "n"    : n,
        "bias" : round(bias,  3),
        "pbias": round(pbias, 2),
        "mae"  : round(mae,   3),
        "rmse" : round(rmse,  3),
        "r"    : round(r,     4),
        "nse"  : round(nse,   4),
        "kge"  : round(kge,   4),
    }


def compute_categorical_metrics(obs: np.ndarray,
                                 sim: np.ndarray,
                                 threshold: float = 1.0) -> dict:
    """
    Binary wet/dry contingency metrics.
    threshold : mm/day — WMO convention = 1.0
    """
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]
    if len(obs) < 3:
        return {m: np.nan for m in
                ["pod","far","csi","ets","freq_bias",
                 "hits","misses","false_al","correct_neg"]}

    obs_wet = obs >= threshold
    sim_wet = sim >= threshold

    hits     = int(np.sum( obs_wet &  sim_wet))
    misses   = int(np.sum( obs_wet & ~sim_wet))
    false_al = int(np.sum(~obs_wet &  sim_wet))
    correct  = int(np.sum(~obs_wet & ~sim_wet))
    total    = hits + misses + false_al + correct

    pod       = hits / (hits + misses)       if (hits + misses)   > 0 else np.nan
    far       = false_al / (hits + false_al) if (hits + false_al) > 0 else np.nan
    csi       = hits / (hits + misses + false_al)                 if (hits + misses + false_al) > 0 else np.nan
    hits_rand = ((hits + misses) * (hits + false_al)) / total if total > 0 else 0
    denom_ets = hits + misses + false_al - hits_rand
    ets       = (hits - hits_rand) / denom_ets if denom_ets > 0 else np.nan
    freq_bias = (hits + false_al) / (hits + misses)                 if (hits + misses) > 0 else np.nan

    return {
        "pod"        : round(float(pod),       4),
        "far"        : round(float(far),       4),
        "csi"        : round(float(csi),       4),
        "ets"        : round(float(ets),       4),
        "freq_bias"  : round(float(freq_bias), 4),
        "hits"       : hits,
        "misses"     : misses,
        "false_al"   : false_al,
        "correct_neg": correct,
    }


def _all_metrics(obs: np.ndarray, sim: np.ndarray,
                  threshold: float = 1.0) -> dict:
    """Combine continuous + categorical into one dict."""
    m = compute_continuous_metrics(obs, sim)
    m.update(compute_categorical_metrics(obs, sim, threshold))
    return m


def _get_products(df: pd.DataFrame, products: list = None) -> list:
    """Return product columns present in df."""
    if products is not None:
        return [p for p in products if p in df.columns]
    exclude = {"station_id","year","month","obs_mm_day",
               "zone_name","season"}
    return [c for c in df.columns if c not in exclude]


# ════════════════════════════════════════════════════════════
# § 2  VALIDATION FUNCTIONS
# ════════════════════════════════════════════════════════════

def validate_per_station(merged_df: pd.DataFrame,
                          products: list = None,
                          threshold: float = None) -> pd.DataFrame:
    """
    All metrics for each product × each station.
    Returns tidy DataFrame: station_id | product | metric…
    """
    thresh   = threshold if threshold is not None else RAIN_THRESHOLD
    products = _get_products(merged_df, products)
    records  = []

    for stn in merged_df["station_id"].unique():
        sub = merged_df[merged_df["station_id"] == stn]
        obs = sub["obs_mm_day"].values
        for pname in products:
            sim = sub[pname].values
            row = {"station_id": stn, "product": pname}
            row.update(_all_metrics(obs, sim, thresh))
            records.append(row)

    results = pd.DataFrame(records)
    out = DATA_DIR / "validation_per_station.csv"
    results.to_csv(out, index=False)
    print(f"  ✅ Per-station validation → {out.name}  "
          f"shape={results.shape}")
    return results


def validate_overall(merged_df: pd.DataFrame,
                      products: list = None,
                      threshold: float = None) -> pd.DataFrame:
    """
    Pool all station-months and compute aggregate metrics per product.
    Returns DataFrame indexed by product.
    """
    thresh   = threshold if threshold is not None else RAIN_THRESHOLD
    products = _get_products(merged_df, products)
    records  = []

    for pname in products:
        obs = merged_df["obs_mm_day"].values
        sim = merged_df[pname].values
        row = {"product": pname}
        row.update(_all_metrics(obs, sim, thresh))
        records.append(row)

    results = pd.DataFrame(records).set_index("product")
    out = DATA_DIR / "validation_overall.csv"
    results.to_csv(out)
    print(f"  ✅ Overall validation → {out.name}")
    cols = ["bias","pbias","rmse","r","nse","kge","pod","far","csi","ets"]
    print(results[[c for c in cols if c in results.columns]]
          .round(4).to_string())
    return results


def validate_by_season(merged_df: pd.DataFrame,
                        products: list = None,
                        threshold: float = None) -> pd.DataFrame:
    """
    Metrics per season × product.
    """
    thresh   = threshold if threshold is not None else RAIN_THRESHOLD
    products = _get_products(merged_df, products)
    records  = []

    for season, months in SEASONS.items():
        sub = merged_df[merged_df["month"].isin(months)]
        for pname in products:
            obs = sub["obs_mm_day"].values
            sim = sub[pname].values
            row = {"season": season, "product": pname}
            row.update(_all_metrics(obs, sim, thresh))
            records.append(row)

    results = pd.DataFrame(records)
    out = DATA_DIR / "validation_by_season.csv"
    results.to_csv(out, index=False)
    print(f"  ✅ Seasonal validation → {out.name}  shape={results.shape}")
    return results


def validate_by_zone(merged_df:         pd.DataFrame,
                      eco_zones_path:    str = None,
                      stations_meta:     pd.DataFrame = None,
                      products:          list = None,
                      threshold:         float = None) -> pd.DataFrame:
    """
    Metrics per ecological zone × product.

    Each station is assigned to a zone based on its coordinates
    intersecting the ecological zone GeoJSON/SHP.

    Parameters
    ──────────
    merged_df       : merged_obs_grid.csv as DataFrame
    eco_zones_path  : path to ecological_zones_5class.geojson or .shp
                      (default: looks in DATA_DIR parent folders)
    stations_meta   : DataFrame with station_id, lon, lat
                      (if None, uses hardcoded WA station coords)
    products        : product columns to evaluate
    threshold       : wet/dry threshold in mm/day

    Returns
    ───────
    DataFrame: zone_name | product | n | bias | pbias | … | kge | pod | …
    Also saves: validation_by_zone.csv
    """
    thresh   = threshold if threshold is not None else RAIN_THRESHOLD
    products = _get_products(merged_df, products)

    # ── Locate ecological zones file ─────────────────────────
    if eco_zones_path is None:
        # Search common locations
        search_paths = [
            DATA_DIR / "ecological_zones_5class.geojson",
            DATA_DIR.parent / "ecological_zones_5class.geojson",
            DATA_DIR.parent / "ecological_zones_5class" / "ecological_zones_5class.shp",
            Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class.geojson"),
            Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class") / "ecological_zones_5class.shp",
        ]
        for p in search_paths:
            if p.exists():
                eco_zones_path = str(p)
                print(f"  Found ecological zones: {p}")
                break

    if eco_zones_path is None or not Path(eco_zones_path).exists():
        print("  ⚠  Ecological zones file not found.")
        print("     Pass eco_zones_path= explicitly or place")
        print("     ecological_zones_5class.geojson in DATA_DIR.")
        print("     Falling back to latitude-band approximation.")
        eco_zones_gdf = None
    else:
        eco_zones_gdf = gpd.read_file(eco_zones_path)
        print(f"  Zones loaded: {eco_zones_gdf['zone_name'].tolist()}")

    # ── Station coordinates ───────────────────────────────────
    STATIONS_COORDS = {
        "WA001": (-17.47, 14.73), "WA002": ( -7.95, 12.65),
        "WA003": ( -1.52, 12.36), "WA004": (  2.17, 13.51),
        "WA005": (  7.33,  9.07), "WA006": ( -0.17,  5.56),
        "WA007": ( -3.93,  5.35), "WA008": (-13.67,  9.53),
        "WA009": (-13.23,  8.49), "WA010": (-10.80,  6.30),
        "WA011": (  1.22,  6.13), "WA012": (  2.42,  6.37),
        "WA013": (  8.52, 12.05), "WA014": ( -1.62,  6.69),
        "WA015": (-16.68, 13.45),
    }

    if stations_meta is not None:
        for _, row in stations_meta.iterrows():
            STATIONS_COORDS[row["station_id"]] = (row["lon"], row["lat"])

    # ── Assign each station to a zone ─────────────────────────
    station_zone = {}
    for stn_id, (lon, lat) in STATIONS_COORDS.items():
        pt = Point(lon, lat)
        if eco_zones_gdf is not None:
            match = eco_zones_gdf[eco_zones_gdf.geometry.contains(pt)]
            if len(match) > 0:
                station_zone[stn_id] = match.iloc[0]["zone_name"]
                continue
        # Fallback: latitude bands
        if lat > 18:
            station_zone[stn_id] = "Saharian"
        elif lat > 14:
            station_zone[stn_id] = "Sahelian"
        elif lat > 10:
            station_zone[stn_id] = "Soudanian"
        elif lat > 7:
            station_zone[stn_id] = "Guinean"
        else:
            station_zone[stn_id] = "Guineo-Congolean"

    print(f"  Station → zone assignments:")
    for stn, zone in sorted(station_zone.items()):
        print(f"    {stn}: {zone}")

    # ── Add zone column to merged_df ──────────────────────────
    df = merged_df.copy()
    df["zone_name"] = df["station_id"].map(station_zone)
    unmapped = df["zone_name"].isna().sum()
    if unmapped > 0:
        print(f"  ⚠  {unmapped} rows have no zone assignment — dropped")
    df = df.dropna(subset=["zone_name"])

    # ── Compute metrics per zone × product ────────────────────
    records = []
    for zone in sorted(df["zone_name"].unique()):
        sub = df[df["zone_name"] == zone]
        for pname in products:
            obs = sub["obs_mm_day"].values
            sim = sub[pname].values
            row = {"zone_name": zone, "product": pname,
                   "n_station_months": len(obs[~np.isnan(obs)])}
            row.update(_all_metrics(obs, sim, thresh))
            records.append(row)

    results = pd.DataFrame(records)
    out = DATA_DIR / "validation_by_zone.csv"
    results.to_csv(out, index=False)
    print(f"  ✅ Zonal validation → {out.name}  shape={results.shape}")

    # Print summary
    pivot = results.pivot_table(
        index="zone_name", columns="product", values="kge"
    ).round(3)
    print(f"\n  KGE by zone × product:")
    print(pivot.to_string())
    return results


def rank_products(overall_df: pd.DataFrame,
                   zone_df:    pd.DataFrame = None) -> pd.DataFrame:
    """
    Composite score ranking — overall and optionally per zone.

    Scoring:
      Higher is better: r, nse, kge, pod, csi, ets
      Lower is better : |bias|, rmse, far, |pbias|
    Each metric normalised to [0,1] then averaged.
    """
    def _score(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        metrics_higher = ["r", "nse", "kge", "pod", "csi", "ets"]
        metrics_lower  = ["rmse", "far"]
        metrics_abs    = ["bias", "pbias"]   # absolute value, lower is better

        scores = pd.DataFrame(index=df.index)

        def norm(col, invert=False):
            mn, mx = col.min(), col.max()
            if mx == mn:
                return pd.Series(0.5, index=col.index)
            n = (col - mn) / (mx - mn)
            return 1 - n if invert else n

        for m in metrics_higher:
            if m in df.columns:
                scores[f"s_{m}"] = norm(df[m].fillna(0))
        for m in metrics_lower:
            if m in df.columns:
                scores[f"s_{m}"] = norm(df[m].fillna(df[m].max()), invert=True)
        for m in metrics_abs:
            if m in df.columns:
                scores[f"s_{m}"] = norm(df[m].abs().fillna(df[m].abs().max()),
                                         invert=True)

        df["composite_score"] = scores.mean(axis=1).round(4)
        return df.sort_values("composite_score", ascending=False)

    # Overall ranking
    ranked_overall = _score(overall_df)
    out = DATA_DIR / "product_ranking.csv"
    ranked_overall[["bias","pbias","rmse","r","nse","kge",
                    "pod","csi","composite_score"]].to_csv(out)
    print(f"\n  ✅ Product ranking → {out.name}")
    print(ranked_overall["composite_score"].to_string())

    # Per-zone ranking
    if zone_df is not None:
        zone_records = []
        for zone in sorted(zone_df["zone_name"].unique()):
            sub = zone_df[zone_df["zone_name"] == zone].set_index("product")
            scored = _score(sub)
            for prod, row in scored.iterrows():
                zone_records.append({
                    "zone_name"      : zone,
                    "product"        : prod,
                    "composite_score": row["composite_score"],
                    "kge"            : row.get("kge", np.nan),
                    "nse"            : row.get("nse", np.nan),
                    "r"              : row.get("r",   np.nan),
                    "pbias"          : row.get("pbias",np.nan),
                })
        zone_ranked = pd.DataFrame(zone_records)
        out2 = DATA_DIR / "product_ranking_by_zone.csv"
        zone_ranked.to_csv(out2, index=False)
        print(f"  ✅ Zone-based ranking → {out2.name}")

        # Print ranking per zone
        pivot = zone_ranked.pivot_table(
            index="zone_name", columns="product",
            values="composite_score"
        ).round(3)
        print(f"\n  Composite score by zone × product (higher = better):")
        print(pivot.to_string())

    return ranked_overall


# ════════════════════════════════════════════════════════════
# § 3  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  VALIDATION METRICS — Step 3")
    print("=" * 60)
    print(f"  DATA_DIR : {DATA_DIR}")
    print(f"  Threshold: {RAIN_THRESHOLD} mm/day")

    # ── Load merged dataset ───────────────────────────────────
    merged_path = DATA_DIR / "merged_obs_grid.csv"
    if not merged_path.exists():
        raise FileNotFoundError(
            f"merged_obs_grid.csv not found at {merged_path}\n"
            f"Run merge_extractions.py first."
        )

    merged = pd.read_csv(merged_path)
    print(f"  Loaded: {merged_path.name}  shape={merged.shape}")
    print(f"  Columns: {list(merged.columns)}")

    # Filter to study period
    merged = merged[
        (merged["year"] >= START_YEAR) &
        (merged["year"] <= END_YEAR)
    ]
    print(f"  After study period filter: {merged.shape}")

    # Detect product columns automatically
    products = [c for c in merged.columns
                if c not in ["station_id","year","month","obs_mm_day"]]
    print(f"  Products found: {products}")

    # ── Run all validations ───────────────────────────────────
    print("\n" + "─" * 60)
    print("  Running per-station validation …")
    station_metrics = validate_per_station(merged, products)

    print("\n" + "─" * 60)
    print("  Running overall (pooled) validation …")
    overall_metrics = validate_overall(merged, products)

    print("\n" + "─" * 60)
    print("  Running seasonal validation …")
    seasonal_metrics = validate_by_season(merged, products)

    print("\n" + "─" * 60)
    print("  Running ecological zone validation …")
    zone_metrics = validate_by_zone(merged, products=products)

    print("\n" + "─" * 60)
    print("  Computing product rankings …")
    ranked = rank_products(overall_metrics, zone_metrics)

    print("\n" + "=" * 60)
    print("  VALIDATION COMPLETE")
    print("=" * 60)
    print(f"""
  Output files in {DATA_DIR}:
    validation_per_station.csv
    validation_overall.csv
    validation_by_season.csv
    validation_by_zone.csv
    product_ranking.csv
    product_ranking_by_zone.csv

  NEXT STEP:
    python visualisation.py
    """)
