"""
============================================================
APPEND WA016 TO EXISTING PRODUCT EXTRACTION CSVs
============================================================
Run AFTER downloading wa016_<PRODUCT>_2001_2020.csv files
from Google Drive to DATA_DIR.

What this does:
  - Reads each wa016_<PRODUCT>_2001_2020.csv
  - Appends WA016 rows to precip_extraction_<PRODUCT>.csv
  - Deduplicates to avoid double-adding

Run:  python append_wa016.py
Then: python merge_extractions.py
============================================================
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(r"C:/Users/Gebruiker/OneDrive/Spain/Paper 1/precipitation_assessment/DATA_DIR")
START_YEAR = 2001
END_YEAR   = 2020

PRODUCTS = [
    "CHIRPS", "ERA5_LAND", "GPM_IMERG",
    "MERRA2", "PERSIANN_CDR", "TERRACLIMATE"
]

print("=" * 60)
print("  APPEND WA016 TO PRODUCT CSVs")
print("=" * 60)

for pname in PRODUCTS:
    wa016_csv = DATA_DIR / f"wa016_{pname}_2001_2020.csv"
    prod_csv  = DATA_DIR / f"precip_extraction_{pname}.csv"

    if not wa016_csv.exists():
        print(f"  ⚠  {wa016_csv.name} not found — skipping {pname}")
        continue

    if not prod_csv.exists():
        print(f"  ⚠  {prod_csv.name} not found — skipping {pname}")
        continue

    # Load WA016 data
    wa016 = pd.read_csv(wa016_csv)

    # Auto-detect precip column
    meta_cols = {"system:index",".geo","station_id","product","year","month"}
    num_cols  = [c for c in wa016.columns
                 if c not in meta_cols
                 and pd.api.types.is_numeric_dtype(wa016[c])]

    if not num_cols:
        print(f"  ⚠  No numeric column in {wa016_csv.name} — skipping")
        continue

    pcol = num_cols[0]
    if pcol != "precip_mm_day":
        wa016 = wa016.rename(columns={pcol: "precip_mm_day"})

    # Keep only needed columns
    for col in ["product","station_id"]:
        if col not in wa016.columns:
            wa016[col] = pname if col == "product" else "WA016"

    wa016 = wa016[["station_id","product","year","month","precip_mm_day"]]
    wa016["year"]  = wa016["year"].astype(int)
    wa016["month"] = wa016["month"].astype(int)
    wa016 = wa016[
        (wa016["year"] >= START_YEAR) &
        (wa016["year"] <= END_YEAR) &
        (wa016["station_id"] == "WA016")
    ]
    wa016 = wa016.dropna(subset=["precip_mm_day"])

    print(f"  {pname}: WA016 rows to add = {len(wa016)}"
          f" (expected {20*12})")

    # Load existing product CSV
    existing = pd.read_csv(prod_csv)

    # Remove any existing WA016 rows (avoid duplicates)
    existing = existing[existing["station_id"] != "WA016"]

    # Append and save
    combined = pd.concat([existing, wa016], ignore_index=True)
    combined = combined.sort_values(
        ["year","month","station_id"]
    ).reset_index(drop=True)
    combined.to_csv(prod_csv, index=False)

    print(f"  ✅ {prod_csv.name} updated → {len(combined):,} rows "
          f"({combined['station_id'].nunique()} stations)")

print(f"""
  ════════════════════════════════════════════
  DONE — all product CSVs updated with WA016
  ════════════════════════════════════════════
  NEXT:
    python merge_extractions.py
    python validation_metrics.py
    python visualisation.py
""")
