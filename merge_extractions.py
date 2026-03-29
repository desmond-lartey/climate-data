"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 3: Local Merge — CSV Extractions + Observations
============================================================
Runs ENTIRELY LOCALLY — no GEE calls, no Earth Engine imports,
no exports submitted. Safe to run repeatedly without triggering
any GEE tasks.

WHAT THIS SCRIPT DOES
──────────────────────
1. Merges the 22 MERRA2 yearly CSVs into one file
2. Loads all 6 product extraction CSVs from DATA_DIR
3. Loads station observations (demo or real)
4. Produces merged_obs_grid.csv — the core validation dataset

INPUT FILES EXPECTED IN DATA_DIR
──────────────────────────────────
  precip_extraction_CHIRPS.csv
  precip_extraction_ERA5_LAND.csv
  precip_extraction_GPM_IMERG.csv
  precip_extraction_PERSIANN_CDR.csv
  precip_extraction_TERRACLIMATE.csv
  precip_extraction_MERRA2_2000.csv   ← yearly splits
  precip_extraction_MERRA2_2001.csv
  ...
  precip_extraction_MERRA2_2021.csv

OUTPUT FILES
─────────────
  precip_extraction_MERRA2.csv        ← merged MERRA2 time series
  merged_obs_grid.csv                 ← final validation dataset

COLUMNS IN merged_obs_grid.csv
────────────────────────────────
  station_id | year | month | obs_mm_day |
  CHIRPS | ERA5_LAND | GPM_IMERG | MERRA2 | PERSIANN_CDR | TERRACLIMATE
  (all precipitation values in mm/day)

HOW TO RUN
───────────
  python merge_extractions.py

No arguments needed — DATA_DIR is read from setup_config.py.
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ════════════════════════════════════════════════════════════
# § 0  CONFIG — read from setup_config (no GEE needed)
# ════════════════════════════════════════════════════════════

# Import only the non-GEE parts of setup_config
from setup_config import CONFIG

DATA_DIR   = Path(CONFIG["data_dir"])
START_YEAR = int(CONFIG["start_date"][:4])   # 2001
END_YEAR   = int(CONFIG["end_date"][:4])     # 2020

print("=" * 60)
print("  LOCAL MERGE — Precipitation Assessment")
print("=" * 60)
print(f"  DATA_DIR   : {DATA_DIR}")
print(f"  Study period: {START_YEAR}–{END_YEAR}")
print()


# ════════════════════════════════════════════════════════════
# § 1  MERGE MERRA2 YEARLY CSVs → ONE FILE
# ════════════════════════════════════════════════════════════

def merge_merra2_yearly(data_dir: Path,
                         study_start: int,
                         study_end:   int) -> Path:
    """
    Concatenate all precip_extraction_MERRA2_<YEAR>.csv files
    into one precip_extraction_MERRA2.csv.

    Filters to study period only (2001–2020) — drops 2000 and
    2021 which exist in DATA_DIR but are outside the study window.

    Returns path to the merged file.
    """
    yearly_csvs = sorted(data_dir.glob("precip_extraction_MERRA2_????.csv"))

    if not yearly_csvs:
        print("  ⚠  No MERRA2 yearly CSVs found.")
        print(f"     Expected: {data_dir}/precip_extraction_MERRA2_2001.csv etc.")
        return None

    print(f"  Found {len(yearly_csvs)} MERRA2 yearly CSV(s):")
    dfs = []
    for csv_path in yearly_csvs:
        df  = pd.read_csv(csv_path)
        yr  = int(csv_path.stem.split("_")[-1])

        # Filter to study period only
        if yr < study_start or yr > study_end:
            print(f"    ⊘  {csv_path.name}  ({len(df):,} rows) "
                  f"— outside study period, skipping")
            continue

        dfs.append(df)
        print(f"    ✓  {csv_path.name}  ({len(df):,} rows)")

    if not dfs:
        print("  ❌ No MERRA2 CSVs within study period.")
        return None

    combined  = pd.concat(dfs, ignore_index=True)
    out_path  = data_dir / "precip_extraction_MERRA2.csv"
    combined.to_csv(out_path, index=False)

    print(f"\n   MERRA2 merged → {out_path.name}")
    print(f"     Rows     : {len(combined):,}")
    print(f"     Years    : {sorted(combined['year'].unique().tolist())}")
    print(f"     Stations : {combined['station_id'].nunique()}")
    return out_path


# ════════════════════════════════════════════════════════════
# § 2  LOAD ALL PRODUCT EXTRACTION CSVs
# ════════════════════════════════════════════════════════════

def load_extraction_csvs(data_dir: Path) -> pd.DataFrame:
    """
    Load all precip_extraction_<PRODUCT>.csv files from data_dir.
    Skips the yearly MERRA2 splits (precip_extraction_MERRA2_YYYY.csv)
    — only loads the merged precip_extraction_MERRA2.csv.

    Returns long-format DataFrame:
      station_id | product | year | month | precip_mm_day
    """
    # Match product-level CSVs only — not the yearly MERRA2 splits
    all_csvs = sorted(data_dir.glob("precip_extraction_*.csv"))
    product_csvs = [
        f for f in all_csvs
        if not f.stem.split("_")[-1].isdigit()   # exclude _YYYY suffix
    ]

    if not product_csvs:
        raise FileNotFoundError(
            f"No product-level extraction CSVs found in {data_dir}\n"
            f"  Expected: precip_extraction_CHIRPS.csv etc."
        )

    expected = {
        "CHIRPS", "ERA5_LAND", "GPM_IMERG",
        "MERRA2", "PERSIANN_CDR", "TERRACLIMATE",
    }

    print(f"\n  Loading {len(product_csvs)} product extraction CSV(s):")
    dfs = []
    found_products = set()

    for csv_path in product_csvs:
        df = pd.read_csv(csv_path)

        # Validate columns
        required = {"station_id", "product", "year", "month", "precip_mm_day"}
        missing  = required - set(df.columns)
        if missing:
            print(f"    ⚠  {csv_path.name} — missing columns: {missing}, skipping")
            continue

        # Enforce types
        df["year"]          = df["year"].astype(int)
        df["month"]         = df["month"].astype(int)
        df["precip_mm_day"] = pd.to_numeric(df["precip_mm_day"], errors="coerce")

        # Filter to study period
        df = df[(df["year"] >= START_YEAR) & (df["year"] <= END_YEAR)]

        products = df["product"].unique().tolist()
        found_products.update(products)
        dfs.append(df)
        print(f"    ✓  {csv_path.name:<45}  "
              f"{products}  {len(df):,} rows")

    if not dfs:
        raise ValueError("No valid extraction CSVs loaded.")

    grid_df = pd.concat(dfs, ignore_index=True)

    # Report missing products
    missing_products = expected - found_products
    if missing_products:
        print(f"\n  ⚠  Missing products (CSVs not found): {missing_products}")
        print(f"     Merge will proceed with available products only.")

    print(f"\n  Total extraction rows : {len(grid_df):,}")
    print(f"  Products loaded       : {sorted(found_products)}")
    return grid_df


# ════════════════════════════════════════════════════════════
# § 3  LOAD STATION OBSERVATIONS
# ════════════════════════════════════════════════════════════

def load_observations(stations_csv: str = None,
                       obs_csv:      str = None) -> pd.DataFrame:
    """
    Load station observations.

    Priority:
      1. Real CSV files if paths are provided and exist
      2. Demo synthetic observations generated locally
         (same cosine formula as data_ingestion.py — no GEE needed)

    Returns DataFrame: station_id, year, month, obs_mm_day
    """
    # Option 1: real CSV
    if stations_csv and obs_csv:
        s_path = Path(stations_csv)
        o_path = Path(obs_csv)
        if s_path.exists() and o_path.exists():
            obs_df = pd.read_csv(o_path)
            obs_df["year"]       = obs_df["year"].astype(int)
            obs_df["month"]      = obs_df["month"].astype(int)
            obs_df["obs_mm_day"] = obs_df["obs_mm_day"].astype(float)
            print(f"\n   Real observations loaded: {len(obs_df):,} rows")
            return obs_df

    # Option 2: generate demo observations locally (no GEE)
    print("\n  ℹ  Generating demo observations (no real gauge CSV provided)")
    print("     Replace with real data by passing stations_csv and obs_csv paths")

    STATIONS_META = [
        ("WA001", "Dakar",        -17.47,  14.73),
        ("WA002", "Bamako",        -7.95,  12.65),
        ("WA003", "Ouagadougou",   -1.52,  12.36),
        ("WA004", "Niamey",         2.17,  13.51),
        ("WA005", "Abuja",          7.33,   9.07),
        ("WA006", "Accra",         -0.17,   5.56),
        ("WA007", "Abidjan",       -3.93,   5.35),
        ("WA008", "Conakry",      -13.67,   9.53),
        ("WA009", "Freetown",     -13.23,   8.49),
        ("WA010", "Monrovia",     -10.80,   6.30),
        ("WA011", "Lomé",           1.22,   6.13),
        ("WA012", "Cotonou",        2.42,   6.37),
        ("WA013", "Kano",           8.52,  12.05),
        ("WA014", "Kumasi",        -1.62,   6.69),
        ("WA015", "Banjul",       -16.68,  13.45),
    ]

    rng  = np.random.default_rng(seed=42)
    rows = []
    for sid, name, lon, lat in STATIONS_META:
        for yr in range(START_YEAR, END_YEAR + 1):
            for mo in range(1, 13):
                phase = (mo - 8) if lat > 10 else (mo - 6)
                amp   = 4.0     if lat > 10 else 7.0
                obs   = max(0.0,
                    0.5 + amp * max(0.0, np.cos(phase * np.pi / 3))
                        + rng.normal(0, 1.25))
                rows.append({
                    "station_id" : sid,
                    "year"       : yr,
                    "month"      : mo,
                    "obs_mm_day" : round(float(obs), 2),
                })

    obs_df = pd.DataFrame(rows)
    print(f"  Demo observations: {len(obs_df):,} rows  "
          f"({START_YEAR}–{END_YEAR}, {len(STATIONS_META)} stations)")
    return obs_df


# ════════════════════════════════════════════════════════════
# § 4  PIVOT AND MERGE
# ════════════════════════════════════════════════════════════

def build_merged_dataset(grid_df:  pd.DataFrame,
                          obs_df:   pd.DataFrame,
                          out_path: Path) -> pd.DataFrame:
    """
    Pivot grid_df from long to wide format, then inner-join
    with obs_df on station_id + year + month.

    Output columns:
      station_id | year | month | obs_mm_day |
      CHIRPS | ERA5_LAND | GPM_IMERG | MERRA2 | PERSIANN_CDR | TERRACLIMATE
    """
    print("\n  Pivoting extraction data to wide format …")
    grid_wide = grid_df.pivot_table(
        index   = ["station_id", "year", "month"],
        columns = "product",
        values  = "precip_mm_day",
        aggfunc = "mean",   # take mean if duplicates exist
    ).reset_index()
    grid_wide.columns.name = None

    print(f"  Wide format shape: {grid_wide.shape}")
    print(f"  Product columns  : {[c for c in grid_wide.columns if c not in ['station_id','year','month']]}")

    print("\n  Merging with observations (inner join) …")
    merged = obs_df.merge(
        grid_wide,
        on  = ["station_id", "year", "month"],
        how = "inner",
    )

    merged.to_csv(out_path, index=False)

    print(f"\n   Merged dataset saved → {out_path.name}")
    print(f"     Shape    : {merged.shape}")
    print(f"     Columns  : {list(merged.columns)}")
    print(f"     Stations : {merged['station_id'].nunique()}")
    print(f"     Years    : {merged['year'].min()}–{merged['year'].max()}")

    # Summary statistics per product
    print("\n  ── Summary statistics (mean mm/day per product) ──")
    product_cols = [c for c in merged.columns
                    if c not in ["station_id", "year", "month", "obs_mm_day"]]
    summary = merged[["obs_mm_day"] + product_cols].describe().loc[["mean","std","min","max"]]
    print(summary.round(3).to_string())

    return merged


# ════════════════════════════════════════════════════════════
# § 5  MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── Step 1: Merge MERRA2 yearly CSVs ─────────────────────
    print("─" * 60)
    print("  STEP 1: Merging MERRA2 yearly CSVs")
    print("─" * 60)

    merra2_merged = merge_merra2_yearly(DATA_DIR, START_YEAR, END_YEAR)

    # ── Step 2: Load all product extraction CSVs ──────────────
    print("\n" + "─" * 60)
    print("  STEP 2: Loading all product extraction CSVs")
    print("─" * 60)

    grid_df = load_extraction_csvs(DATA_DIR)

    # ── Step 3: Load observations ─────────────────────────────
    print("\n" + "─" * 60)
    print("  STEP 3: Loading station observations")
    print("─" * 60)

    obs_df = load_observations(
        # Uncomment and set paths when real gauge data is available:
        # stations_csv = str(DATA_DIR / "wa_gauge_stations.csv"),
        # obs_csv      = str(DATA_DIR / "wa_gauge_obs_2001_2020.csv"),
    )

    # ── Step 4: Build merged dataset ──────────────────────────
    print("\n" + "─" * 60)
    print("  STEP 4: Building merged dataset")
    print("─" * 60)

    out_path = DATA_DIR / "merged_obs_grid.csv"
    merged   = build_merged_dataset(grid_df, obs_df, out_path)

    print("\n" + "=" * 60)
    print("  MERGE COMPLETE")
    print("=" * 60)
    print(f"""
  Output file : {out_path}
  Rows        : {len(merged):,}
  Products    : {[c for c in merged.columns if c not in ['station_id','year','month','obs_mm_day']]}

  NEXT STEPS:
  ─────────────────────────────────────────────────────
  1. Inspect merged_obs_grid.csv in Excel or pandas
  2. Run validation metrics against real gauge data
     (replace demo obs by uncommenting stations_csv/obs_csv above)
  3. Use merged dataset for r, PBIAS, NSE, KGE computation
     per station, per product, per ecological zone
  ─────────────────────────────────────────────────────
    """)
