"""
============================================================
APPEND WA016 MERRA2 YEARLY CSVs TO MERRA2 EXTRACTION
============================================================
Run AFTER downloading wa016_MERRA2_YYYY.csv files from Drive.

What this does:
  - Reads each wa016_MERRA2_YYYY.csv (one per year)
  - Drops NaN rows and filters to correct year
  - Appends to precip_extraction_MERRA2.csv
  - Deduplicates

Run:  python append_wa016_merra2.py
Then: python merge_extractions.py
============================================================
"""

import pandas as pd
from pathlib import Path

DATA_DIR   = Path(r"C:/Users/Gebruiker/OneDrive/Spain/Paper 1/precipitation_assessment/DATA_DIR")
START_YEAR = 2001
END_YEAR   = 2020

print("=" * 60)
print("  APPEND WA016 MERRA2 YEARLY CSVs")
print("=" * 60)

merra2_csv = DATA_DIR / "precip_extraction_MERRA2.csv"
if not merra2_csv.exists():
    print(f"   {merra2_csv.name} not found")
    print("     Run merge_extractions.py first to build it")
    exit()

# Load existing MERRA2 CSV — remove any old WA016 rows
existing = pd.read_csv(merra2_csv)
existing = existing[existing["station_id"] != "WA016"]
print(f"  Existing MERRA2 rows (excl WA016): {len(existing):,}")

# Load and validate each yearly WA016 MERRA2 CSV
yearly_dfs = []
for yr in range(START_YEAR, END_YEAR + 1):
    csv_path = DATA_DIR / f"wa016_MERRA2_{yr}.csv"
    if not csv_path.exists():
        print(f"  ⚠  {csv_path.name} not found — skipping")
        continue

    df = pd.read_csv(csv_path)

    # Find precip column
    meta = {"system:index", ".geo", "station_id", "product", "year", "month"}
    num_cols = [c for c in df.columns
                if c not in meta
                and pd.api.types.is_numeric_dtype(df[c])]

    if not num_cols:
        print(f"  ⚠  {csv_path.name}: no numeric column — skipping")
        continue

    pcol = num_cols[0]
    if pcol != "precip_mm_day":
        df = df.rename(columns={pcol: "precip_mm_day"})

    # Drop NaN, filter to correct year, ensure station
    df = df.dropna(subset=["precip_mm_day"])
    if "year" in df.columns:
        df = df[df["year"].astype(int) == yr]
    if "station_id" not in df.columns:
        df["station_id"] = "WA016"
    if "product" not in df.columns:
        df["product"] = "MERRA2"

    df["year"]  = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df = df[["station_id","product","year","month","precip_mm_day"]]

    n = len(df)
    flag = "✓" if n == 12 else "⚠"
    print(f"  {flag}  wa016_MERRA2_{yr}.csv → {n} rows (expected 12)")
    yearly_dfs.append(df)

if not yearly_dfs:
    print("   No WA016 MERRA2 data loaded — check Drive downloads")
else:
    wa016_merra2 = pd.concat(yearly_dfs, ignore_index=True)
    print(f"\n  WA016 MERRA2 total: {len(wa016_merra2)} rows "
          f"(expected {(END_YEAR-START_YEAR+1)*12})")

    # Combine and save
    combined = pd.concat([existing, wa016_merra2], ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["station_id","year","month"]
    ).sort_values(["year","month","station_id"]).reset_index(drop=True)

    combined.to_csv(merra2_csv, index=False)
    print(f"   {merra2_csv.name} updated")
    print(f"     Total rows : {len(combined):,}")
    print(f"     Stations   : {sorted(combined['station_id'].unique())}")
    print(f"     NaN        : {combined['precip_mm_day'].isna().sum()}")

    print("""
  NEXT:
    python merge_extractions.py
    python validation_metrics.py
    python visualisation.py
""")
