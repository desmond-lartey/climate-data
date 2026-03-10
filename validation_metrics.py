"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 3: Statistical Validation Metrics
============================================================
Computes continuous + categorical metrics for each product
vs. gauge observations, both globally and per-station.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from setup_config import CONFIG, PRODUCTS, METRICS, RAIN_THRESHOLD

DATA_DIR = Path(CONFIG["data_dir"])


# ══════════════════════════════════════════════════════════
# 3.1  Continuous performance metrics
# ══════════════════════════════════════════════════════════

def compute_continuous_metrics(obs: np.ndarray,
                                sim: np.ndarray) -> dict:
    """
    Compute a suite of continuous verification statistics.
    obs, sim : 1-D arrays of equal length (mm/day)
    """
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]
    n = len(obs)

    if n < 3:
        return {m: np.nan for m in [
            "n","bias","pbias","mae","rmse","r","r2","nse","kge"]}

    bias  = float(np.mean(sim - obs))
    pbias = float(100 * np.sum(sim - obs) / np.sum(obs)) if np.sum(obs) else np.nan
    mae   = float(np.mean(np.abs(sim - obs)))
    rmse  = float(np.sqrt(np.mean((sim - obs)**2)))

    # Pearson r
    if obs.std() < 1e-10 or sim.std() < 1e-10:
        r, r2 = np.nan, np.nan
    else:
        r  = float(np.corrcoef(obs, sim)[0, 1])
        r2 = r**2

    # Nash-Sutcliffe efficiency
    nse = float(1 - np.sum((obs - sim)**2) / np.sum((obs - np.mean(obs))**2)) \
          if np.sum((obs - np.mean(obs))**2) > 0 else np.nan

    # Kling-Gupta efficiency
    alpha = sim.std() / obs.std() if obs.std() > 0 else np.nan
    beta  = sim.mean() / obs.mean() if obs.mean() > 0 else np.nan
    kge   = float(1 - np.sqrt((r - 1)**2 + (alpha - 1)**2 + (beta - 1)**2)) \
            if not any(np.isnan([r, alpha, beta])) else np.nan

    return {
        "n":     n,
        "bias":  round(bias,  3),
        "pbias": round(pbias, 2),
        "mae":   round(mae,   3),
        "rmse":  round(rmse,  3),
        "r":     round(r,     4),
        "r2":    round(r2,    4),
        "nse":   round(nse,   4),
        "kge":   round(kge,   4),
    }


# ══════════════════════════════════════════════════════════
# 3.2  Categorical (detection) metrics
# ══════════════════════════════════════════════════════════

def compute_categorical_metrics(obs: np.ndarray,
                                 sim: np.ndarray,
                                 threshold: float = RAIN_THRESHOLD) -> dict:
    """
    Binary rain / no-rain contingency metrics.
    threshold : mm/day above which an event is "rain"
    """
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]

    obs_rain = obs >= threshold
    sim_rain = sim >= threshold

    hits     = int(np.sum( obs_rain &  sim_rain))   # a
    misses   = int(np.sum( obs_rain & ~sim_rain))   # b
    false_al = int(np.sum(~obs_rain &  sim_rain))   # c
    correct  = int(np.sum(~obs_rain & ~sim_rain))   # d

    total = hits + misses + false_al + correct

    pod  = hits / (hits + misses)       if (hits + misses)       > 0 else np.nan
    far  = false_al / (hits + false_al) if (hits + false_al)     > 0 else np.nan
    csi  = hits / (hits + misses + false_al) \
           if (hits + misses + false_al) > 0 else np.nan

    # Equitable threat score
    hits_rand = ((hits + misses) * (hits + false_al)) / total if total > 0 else 0
    ets = (hits - hits_rand) / (hits + misses + false_al - hits_rand) \
          if (hits + misses + false_al - hits_rand) > 0 else np.nan

    bias_freq = (hits + false_al) / (hits + misses) \
                if (hits + misses) > 0 else np.nan

    return {
        "hits":      hits,
        "misses":    misses,
        "false_al":  false_al,
        "correct_neg": correct,
        "pod":       round(float(pod),      4),
        "far":       round(float(far),      4),
        "csi":       round(float(csi),      4),
        "ets":       round(float(ets),      4),
        "freq_bias": round(float(bias_freq),4),
    }


# ══════════════════════════════════════════════════════════
# 3.3  Per-station validation
# ══════════════════════════════════════════════════════════

def validate_per_station(merged_df: pd.DataFrame,
                          products: list = None) -> pd.DataFrame:
    """
    Run all metrics for each product × each station.
    merged_df columns: station_id, year, month, obs, <product_names…>
    Returns a tidy DataFrame: station_id × product × metric → value
    """
    if products is None:
        products = [c for c in merged_df.columns
                    if c not in ["station_id","year","month","obs"]]

    records = []
    for stn in merged_df["station_id"].unique():
        sub = merged_df[merged_df["station_id"] == stn]
        obs = sub["obs"].values

        for pname in products:
            if pname not in sub.columns:
                continue
            sim = sub[pname].values
            row = {"station_id": stn, "product": pname}
            row.update(compute_continuous_metrics(obs, sim))
            # row.update(compute_categorical_metrics(obs, sim))
            records.append(row)

    results = pd.DataFrame(records)
    out = DATA_DIR / "validation_per_station.csv"
    results.to_csv(out, index=False)
    print(f" Per-station validation saved → {out}  shape={results.shape}")
    return results


# ══════════════════════════════════════════════════════════
# 3.4  Overall (pooled) validation
# ══════════════════════════════════════════════════════════

def validate_overall(merged_df: pd.DataFrame,
                      products: list = None) -> pd.DataFrame:
    """
    Pool all station-months and compute aggregate metrics per product.
    """
    if products is None:
        products = [c for c in merged_df.columns
                    if c not in ["station_id","year","month","obs"]]

    records = []
    for pname in products:
        if pname not in merged_df.columns:
            continue
        obs = merged_df["obs"].values
        sim = merged_df[pname].values
        row = {"product": pname}
        row.update(compute_continuous_metrics(obs, sim))
        # row.update(compute_categorical_metrics(obs, sim))
        records.append(row)

    results = pd.DataFrame(records).set_index("product")
    out = DATA_DIR / "validation_overall.csv"
    results.to_csv(out)
    print(f" Overall validation saved → {out}")
    print(results[["bias","pbias","rmse","r","nse","kge","pod","csi"]].to_string())
    return results


# ══════════════════════════════════════════════════════════
# 3.5  Seasonal stratification
# ══════════════════════════════════════════════════════════

SEASONS = {
    "DJF": [12, 1, 2],
    "MAM": [3, 4, 5],
    "JJA": [6, 7, 8],
    "SON": [9, 10, 11],
}

def validate_by_season(merged_df: pd.DataFrame,
                        products: list = None) -> pd.DataFrame:
    """
    Compute continuous metrics for each product × season.
    """
    if products is None:
        products = [c for c in merged_df.columns
                    if c not in ["station_id","year","month","obs"]]

    records = []
    for season, months in SEASONS.items():
        sub = merged_df[merged_df["month"].isin(months)]
        for pname in products:
            if pname not in sub.columns:
                continue
            obs = sub["obs"].values
            sim = sub[pname].values
            row = {"season": season, "product": pname}
            row.update(compute_continuous_metrics(obs, sim))
            records.append(row)

    results = pd.DataFrame(records)
    out = DATA_DIR / "validation_by_season.csv"
    results.to_csv(out, index=False)
    print(f" Seasonal validation saved → {out}")
    return results


# ══════════════════════════════════════════════════════════
# 3.6  Rank products by composite score
# ══════════════════════════════════════════════════════════

def rank_products(overall_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a normalised composite score across key metrics.
    Higher score = better product.
    """
    df = overall_df.copy()

    # Normalise metrics to [0,1] (higher = better)
    def norm(col, invert=False):
        mn, mx = col.min(), col.max()
        if mx == mn:
            return col * 0 + 0.5
        n = (col - mn) / (mx - mn)
        return 1 - n if invert else n

    scores = pd.DataFrame(index=df.index)
    scores["s_bias"]  = norm(df["bias"].abs(),  invert=True)
    scores["s_rmse"]  = norm(df["rmse"],         invert=True)
    scores["s_r"]     = norm(df["r"])
    scores["s_nse"]   = norm(df["nse"])
    scores["s_kge"]   = norm(df["kge"])
    scores["s_pod"]   = norm(df["pod"])
    scores["s_csi"]   = norm(df["csi"])
    scores["s_far"]   = norm(df["far"],          invert=True)

    df["composite_score"] = scores.mean(axis=1).round(4)
    df = df.sort_values("composite_score", ascending=False)

    out = DATA_DIR / "product_ranking.csv"
    df[["bias","rmse","r","nse","kge","pod","csi","composite_score"]].to_csv(out)
    print(f"\n Product Rankings:\n{df['composite_score'].to_string()}")
    return df


# ══════════════════════════════════════════════════════════
# 3.7  Run
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    merged = pd.read_csv(DATA_DIR / "merged_obs_grid.csv")

    station_metrics  = validate_per_station(merged)
    overall_metrics  = validate_overall(merged)
    seasonal_metrics = validate_by_season(merged)
    ranked           = rank_products(overall_metrics)
