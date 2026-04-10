"""
Fix MERRA2 merge — run this ONCE to rebuild precip_extraction_MERRA2.csv
then re-run merge_extractions.py to rebuild merged_obs_grid.csv
"""
import pandas as pd
from pathlib import Path 

DATA_DIR = Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR")

START_YEAR = 2001
END_YEAR   = 2020

print("=" * 60)
print("  MERRA2 MERGE FIX")
print("=" * 60)

yearly_csvs = sorted(DATA_DIR.glob("precip_extraction_MERRA2_????.csv"))
print(f"  Found {len(yearly_csvs)} yearly CSVs")

dfs = []
for csv_path in yearly_csvs:
    yr = int(csv_path.stem.split("_")[-1])
    
    df = pd.read_csv(csv_path)
    
    # Drop rows where precip_mm_day is NaN — each file has data
    # only for its own year, NaN for all others
    df = df.dropna(subset=["precip_mm_day"])
    
    # Keep only the year that matches the filename
    if "year" in df.columns:
        df = df[df["year"] == yr]
    
    # Filter to study period
    if yr < START_YEAR or yr > END_YEAR:
        print(f"  ⊘  {csv_path.name}  outside study period, skipping")
        continue
    
    print(f"  ✓  {csv_path.name}  → {len(df)} valid rows  (year={yr})")
    dfs.append(df)

if not dfs:
    print("❌ No data loaded!")
else:
    combined = pd.concat(dfs, ignore_index=True)
    
    # Remove any duplicates (same station+year+month)
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["station_id", "year", "month"]
    )
    after = len(combined)
    if before != after:
        print(f"  Removed {before-after} duplicate rows")
    
    # Sort nicely
    combined = combined.sort_values(
        ["year", "month", "station_id"]
    ).reset_index(drop=True)
    
    out = DATA_DIR / "precip_extraction_MERRA2.csv"
    combined.to_csv(out, index=False)
    
    print(f"\n  ✅ Saved: {out.name}")
    print(f"     Rows    : {len(combined):,}")
    print(f"     Expected: {(END_YEAR-START_YEAR+1) * 12 * 15} "
          f"({END_YEAR-START_YEAR+1} yrs × 12 mo × 15 stations)")
    print(f"     Years   : {sorted(combined['year'].unique())}")
    print(f"     Stations: {sorted(combined['station_id'].unique())}")
    print(f"     NaN in precip_mm_day: {combined['precip_mm_day'].isna().sum()}")
    
    print("\n  Sample (first 5 rows):")
    print(combined[["station_id","year","month","precip_mm_day"]].head(5).to_string())
    
    print("\n" + "="*60)
    print("  NOW run: python merge_extractions.py")
    print("  Then   : python validation_metrics.py")
    print("  Then   : python visualisation.py")
    print("="*60)
