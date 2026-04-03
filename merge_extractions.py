"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 2: Local Merge — CSV Extractions + Observations
============================================================
IMPORTANT — CORRECT RUN ORDER:
  1. python append_wa016.py        ← add WA016 to all product CSVs
  2. python merge_extractions.py   ← rebuild merged_obs_grid.csv
  3. python validation_metrics.py
  4. python visualisation.py

Do NOT run merge_extractions.py before append_wa016.py —
the rebuild_merra2() step will preserve WA016 rows only if
they already exist in precip_extraction_MERRA2.csv.
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path

from setup_config import CONFIG

DATA_DIR   = Path(CONFIG["data_dir"])
START_YEAR = int(CONFIG["start_date"][:4])
END_YEAR   = int(CONFIG["end_date"][:4])

USE_REAL_OBS = True
GPCC_OBS_CSV = DATA_DIR / "gpcc_obs_2001_2020.csv"

print("=" * 60)
print("  LOCAL MERGE — Precipitation Assessment")
print("=" * 60)
print(f"  DATA_DIR    : {DATA_DIR}")
print(f"  Study period: {START_YEAR}–{END_YEAR}")
print(f"  Observations: {'GPCC real' if USE_REAL_OBS else 'Synthetic demo'}")


# ════════════════════════════════════════════════════════════
# UTILITY: find the precip value column
# ════════════════════════════════════════════════════════════

def _find_precip_col(df: pd.DataFrame) -> str:
    non_precip = {
        "system:index", ".geo", "station_id", "product",
        "year", "month", "zone_name", "zone_id",
    }
    candidates = [
        c for c in df.columns
        if c not in non_precip
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not candidates:
        raise ValueError(f"No precip column found. Columns: {list(df.columns)}")
    if len(candidates) == 1:
        return candidates[0]
    for pref in ["precip_mm_day","precip","mm_day","precipitation","value","mean"]:
        for c in candidates:
            if pref in c.lower():
                return c
    return candidates[0]


# ════════════════════════════════════════════════════════════
# § 1  REBUILD MERRA2 FROM YEARLY SPLITS
#       Preserves extra stations (e.g. WA016) already appended
# ════════════════════════════════════════════════════════════

def rebuild_merra2(data_dir: Path, start: int, end: int) -> Path:
    yearly = sorted(data_dir.glob("precip_extraction_MERRA2_????.csv"))
    if not yearly:
        print("  ⚠  No MERRA2 yearly CSVs found")
        return None

    print(f"\n  Rebuilding MERRA2 from {len(yearly)} yearly CSVs...")
    dfs = []

    for csv_path in yearly:
        yr = int(csv_path.stem.split("_")[-1])
        if yr < start or yr > end:
            print(f"  ⊘  {csv_path.name}  (outside {start}-{end})")
            continue

        df = pd.read_csv(csv_path)
        try:
            pcol = _find_precip_col(df)
        except ValueError as e:
            print(f"  ⚠  {csv_path.name}: {e} — skipping")
            continue

        if pcol != "precip_mm_day":
            df = df.rename(columns={pcol: "precip_mm_day"})

        df = df.dropna(subset=["precip_mm_day"])
        if "year" in df.columns:
            df = df[df["year"].astype(int) == yr]

        df["year"]          = df["year"].astype(int)
        df["month"]         = df["month"].astype(int)
        df["precip_mm_day"] = pd.to_numeric(df["precip_mm_day"], errors="coerce")

        keep = ["station_id","product","year","month","precip_mm_day"]
        df = df[[c for c in keep if c in df.columns]]
        if "product" not in df.columns:
            df["product"] = "MERRA2"

        n = len(df)
        expected = df["station_id"].nunique() * 12
        flag = "✓" if n >= expected * 0.9 else "⚠"
        print(f"  {flag}  {csv_path.name}  → {n} rows")
        dfs.append(df)

    if not dfs:
        print("   No MERRA2 data loaded")
        return None

    combined = pd.concat(dfs, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["station_id","year","month"])
    if before != len(combined):
        print(f"  Removed {before-len(combined)} duplicates")

    combined = combined.sort_values(["year","month","station_id"]).reset_index(drop=True)

    out = data_dir / "precip_extraction_MERRA2.csv"

    # ── KEY FIX: preserve extra stations already appended ──
    # (e.g. WA016 added via append_wa016.py before this runs)
    if out.exists():
        existing = pd.read_csv(out)
        rebuilt_stations = set(combined["station_id"].unique())
        extra = existing[~existing["station_id"].isin(rebuilt_stations)]
        if len(extra) > 0:
            extra_stns = sorted(extra["station_id"].unique())
            print(f"  Preserving {len(extra)} rows from extra stations: {extra_stns}")
            combined = pd.concat([combined, extra], ignore_index=True)
            combined = combined.sort_values(
                ["year","month","station_id"]
            ).reset_index(drop=True)

    combined.to_csv(out, index=False)

    expected_total = (end-start+1) * 12 * combined["station_id"].nunique()
    print(f"\n   MERRA2 rebuilt → {out.name}")
    print(f"     Rows     : {len(combined):,}")
    print(f"     Stations : {sorted(combined['station_id'].unique())}")
    print(f"     NaN      : {combined['precip_mm_day'].isna().sum()}")
    return out


# ════════════════════════════════════════════════════════════
# § 2  LOAD ALL PRODUCT EXTRACTION CSVs
# ════════════════════════════════════════════════════════════

def load_extraction_csvs(data_dir: Path) -> pd.DataFrame:
    all_csvs     = sorted(data_dir.glob("precip_extraction_*.csv"))
    product_csvs = [f for f in all_csvs if not f.stem.split("_")[-1].isdigit()]

    if not product_csvs:
        raise FileNotFoundError(f"No product extraction CSVs in {data_dir}")

    print(f"\n  Loading {len(product_csvs)} product CSV(s):")
    dfs = []

    for csv_path in product_csvs:
        df = pd.read_csv(csv_path)

        missing_req = [r for r in ["station_id","year","month"] if r not in df.columns]
        if missing_req:
            print(f"  ⚠  {csv_path.name}: missing {missing_req} — skipping")
            continue

        try:
            pcol = _find_precip_col(df)
        except ValueError as e:
            print(f"  ⚠  {csv_path.name}: {e} — skipping")
            continue

        if pcol != "precip_mm_day":
            df = df.rename(columns={pcol: "precip_mm_day"})

        if "product" not in df.columns:
            parts = csv_path.stem.split("_")
            df["product"] = "_".join(parts[2:]).upper()

        df["year"]          = pd.to_numeric(df["year"],  errors="coerce")
        df["month"]         = pd.to_numeric(df["month"], errors="coerce")
        df["precip_mm_day"] = pd.to_numeric(df["precip_mm_day"], errors="coerce")
        df = df.dropna(subset=["year","month"])
        df["year"]  = df["year"].astype(int)
        df["month"] = df["month"].astype(int)
        df = df[(df["year"] >= START_YEAR) & (df["year"] <= END_YEAR)]

        products = df["product"].unique().tolist()
        n_stns   = df["station_id"].nunique()
        print(f"  ✓  {csv_path.name:<45}  {products}  "
              f"{len(df):,} rows  ({n_stns} stations)")
        dfs.append(df[["station_id","product","year","month","precip_mm_day"]])

    if not dfs:
        raise ValueError("No valid extraction CSVs loaded")

    out = pd.concat(dfs, ignore_index=True)
    print(f"\n  Total rows: {len(out):,}")
    print(f"  Products : {sorted(out['product'].unique())}")
    print(f"  Stations : {sorted(out['station_id'].unique())}")
    return out


# ════════════════════════════════════════════════════════════
# § 3  OBSERVATIONS
# ════════════════════════════════════════════════════════════

STATIONS_META = [
    ("WA001","Dakar",       -17.47, 14.73),
    ("WA002","Bamako",       -7.95, 12.65),
    ("WA003","Ouagadougou",  -1.52, 12.36),
    ("WA004","Niamey",        2.17, 13.51),
    ("WA005","Abuja",         7.33,  9.07),
    ("WA006","Accra",        -0.17,  5.56),
    ("WA007","Abidjan",      -3.93,  5.35),
    ("WA008","Conakry",     -13.67,  9.53),
    ("WA009","Freetown",    -13.23,  8.49),
    ("WA010","Monrovia",    -10.80,  6.30),
    ("WA011","Lomé",          1.22,  6.13),
    ("WA012","Cotonou",       2.42,  6.37),
    ("WA013","Kano",          8.52, 12.05),
    ("WA014","Kumasi",       -1.62,  6.69),
    ("WA015","Banjul",      -16.68, 13.45),
    ("WA016","Nouakchott",  -15.97, 18.07),
]

def _make_demo_obs() -> pd.DataFrame:
    rng  = np.random.default_rng(seed=42)
    rows = []
    for sid, name, lon, lat in STATIONS_META:
        for yr in range(START_YEAR, END_YEAR+1):
            for mo in range(1, 13):
                phase = (mo-8) if lat > 10 else (mo-6)
                amp   = 4.0 if lat > 10 else 7.0
                obs   = max(0.0, 0.5 + amp*max(0.0, np.cos(phase*np.pi/3))
                            + rng.normal(0, 1.25))
                rows.append({"station_id":sid,"year":yr,
                             "month":mo,"obs_mm_day":round(float(obs),2)})
    return pd.DataFrame(rows)

def load_observations(use_real=True, obs_csv=None) -> pd.DataFrame:
    if use_real and obs_csv is not None:
        o = Path(obs_csv)
        if o.exists():
            df = pd.read_csv(o)
            df["year"]       = df["year"].astype(int)
            df["month"]      = df["month"].astype(int)
            df["obs_mm_day"] = df["obs_mm_day"].astype(float)
            df = df[(df["year"]>=START_YEAR) & (df["year"]<=END_YEAR)]
            print(f"\n   GPCC observations loaded: {o.name}")
            print(f"     Rows    : {len(df):,}")
            print(f"     Stations: {sorted(df['station_id'].unique())}")
            print(f"     Mean obs: {df['obs_mm_day'].mean():.3f} mm/day")
            return df
        else:
            print(f"  ⚠  GPCC file not found: {o} — using demo")

    print("\n  ℹ  Using SYNTHETIC demo observations")
    df = _make_demo_obs()
    print(f"     Rows: {len(df):,}")
    return df


# ════════════════════════════════════════════════════════════
# § 4  PIVOT AND MERGE
# ════════════════════════════════════════════════════════════

def build_merged(grid_df: pd.DataFrame,
                  obs_df:  pd.DataFrame,
                  out_path: Path) -> pd.DataFrame:
    print("\n  Pivoting to wide format...")
    wide = grid_df.pivot_table(
        index   = ["station_id","year","month"],
        columns = "product",
        values  = "precip_mm_day",
        aggfunc = "mean",
    ).reset_index()
    wide.columns.name = None
    print(f"  Wide shape: {wide.shape}")

    product_cols = [c for c in wide.columns
                    if c not in ["station_id","year","month"]]
    print(f"  Products  : {product_cols}")
    print(f"  Stations  : {sorted(wide['station_id'].unique())}")

    for p in product_cols:
        nan_pct = 100 * wide[p].isna().sum() / len(wide)
        flag = "⚠" if nan_pct > 20 else "✓"
        print(f"    {flag}  {p:<18} NaN={nan_pct:.1f}%")

    print("\n  Merging with observations...")

    # Inner join — only keeps station-months present in BOTH obs and grid
    # WA016 will appear only if it exists in BOTH
    obs_stns  = set(obs_df["station_id"].unique())
    grid_stns = set(wide["station_id"].unique())
    common    = obs_stns & grid_stns
    missing   = obs_stns - grid_stns
    if missing:
        print(f"  ⚠  Stations in obs but NOT in grid (will be dropped): {sorted(missing)}")
    print(f"  Stations in merge: {sorted(common)}")

    merged = obs_df.merge(wide, on=["station_id","year","month"], how="inner")
    merged.to_csv(out_path, index=False)

    print(f"\n   Saved → {out_path.name}")
    print(f"     Shape   : {merged.shape}")
    print(f"     Stations: {sorted(merged['station_id'].unique())}")
    print(f"     Years   : {merged['year'].min()}–{merged['year'].max()}")

    print("\n  NaN per product:")
    for p in product_cols:
        if p in merged.columns:
            n   = merged[p].isna().sum()
            pct = 100*n/len(merged)
            flag = "⚠" if pct > 5 else "✓"
            print(f"    {flag}  {p:<18} NaN={n} ({pct:.1f}%)")
    return merged


# ════════════════════════════════════════════════════════════
# § 5  MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "─"*60)
    print("  STEP 1: Rebuilding MERRA2 (preserving extra stations)")
    print("─"*60)
    rebuild_merra2(DATA_DIR, START_YEAR, END_YEAR)

    print("\n" + "─"*60)
    print("  STEP 2: Loading all product extraction CSVs")
    print("─"*60)
    grid_df = load_extraction_csvs(DATA_DIR)

    print("\n" + "─"*60)
    print("  STEP 3: Loading observations")
    print("─"*60)
    obs_df = load_observations(
        use_real = USE_REAL_OBS,
        obs_csv  = GPCC_OBS_CSV,
    )

    print("\n" + "─"*60)
    print("  STEP 4: Building merged_obs_grid.csv")
    print("─"*60)
    out_path = DATA_DIR / "merged_obs_grid.csv"
    merged   = build_merged(grid_df, obs_df, out_path)

    print("\n" + "="*60)
    print("  MERGE COMPLETE")
    print("="*60)
    print(f"  Observations: {'GPCC real' if USE_REAL_OBS else 'Synthetic'}")
    print("  NEXT: python validation_metrics.py")
