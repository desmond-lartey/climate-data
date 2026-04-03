"""
============================================================
APPEND WA016 TO EXISTING PRODUCT EXTRACTION CSVs
============================================================
Handles both:
  - Single-file products: wa016_<PRODUCT>_2001_2020.csv
    (CHIRPS, ERA5_LAND, GPM_IMERG, PERSIANN_CDR, TERRACLIMATE)
  - Yearly MERRA2 files: wa016_MERRA2_YYYY.csv (2001-2020)

Run:  python append_wa016.py
Then: python merge_extractions.py
============================================================
"""

import pandas as pd
from pathlib import Path

DATA_DIR   = Path(r"C:/Users/Gebruiker/OneDrive/Spain/Paper 1/precipitation_assessment/DATA_DIR")
START_YEAR = 2001
END_YEAR   = 2020

# Products delivered as single 2001-2020 CSV
SINGLE_FILE_PRODUCTS = [
    "CHIRPS", "ERA5_LAND", "GPM_IMERG",
    "PERSIANN_CDR", "TERRACLIMATE"
]

print("=" * 60)
print("  APPEND WA016 TO ALL PRODUCT CSVs")
print("=" * 60)


def _find_precip_col(df):
    """Auto-detect the numeric precip column."""
    meta = {"system:index", ".geo", "station_id",
            "product", "year", "month"}
    candidates = [c for c in df.columns
                  if c not in meta
                  and pd.api.types.is_numeric_dtype(df[c])]
    if not candidates:
        return None
    for pref in ["precip_mm_day", "precip", "precipitation",
                 "mean", "value"]:
        for c in candidates:
            if pref in c.lower():
                return c
    return candidates[0]


def _clean_wa016(df, pname, yr_filter=None):
    """
    Standardise a WA016 dataframe:
      - rename precip column to precip_mm_day
      - drop NaN
      - filter to study period
      - filter to yr_filter year if given (for yearly files)
      - ensure station_id and product columns exist
    Returns cleaned DataFrame or None if empty.
    """
    pcol = _find_precip_col(df)
    if pcol is None:
        return None
    if pcol != "precip_mm_day":
        df = df.rename(columns={pcol: "precip_mm_day"})

    if "station_id" not in df.columns:
        df["station_id"] = "WA016"
    if "product" not in df.columns:
        df["product"] = pname

    df["year"]          = pd.to_numeric(df["year"],  errors="coerce").astype("Int64")
    df["month"]         = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["precip_mm_day"] = pd.to_numeric(df["precip_mm_day"], errors="coerce")

    df = df.dropna(subset=["precip_mm_day", "year", "month"])
    df["year"]  = df["year"].astype(int)
    df["month"] = df["month"].astype(int)

    # Filter to study period
    df = df[(df["year"] >= START_YEAR) & (df["year"] <= END_YEAR)]

    # For yearly files — keep only rows matching the file's year
    if yr_filter is not None:
        df = df[df["year"] == yr_filter]

    df = df[df["station_id"] == "WA016"]
    return df[["station_id","product","year","month","precip_mm_day"]]


def _append_to_product_csv(wa016_df, pname):
    """
    Load existing precip_extraction_<PRODUCT>.csv,
    remove old WA016 rows, append new ones, save.
    """
    prod_csv = DATA_DIR / f"precip_extraction_{pname}.csv"
    if not prod_csv.exists():
        print(f"  ⚠  {prod_csv.name} not found — skipping")
        return

    existing = pd.read_csv(prod_csv)

    # Rename legacy obs column if present
    if "obs" in existing.columns and "obs_mm_day" not in existing.columns:
        existing = existing.rename(columns={"obs": "obs_mm_day"})

    # Remove any existing WA016 rows
    existing = existing[existing["station_id"] != "WA016"]

    combined = pd.concat([existing, wa016_df], ignore_index=True)
    combined = combined.sort_values(
        ["year","month","station_id"]
    ).reset_index(drop=True)
    combined.to_csv(prod_csv, index=False)

    n_stns = combined["station_id"].nunique()
    print(f"   {prod_csv.name} → {len(combined):,} rows  "
          f"({n_stns} stations)")


# ════════════════════════════════════════════════════════════
# § 1  SINGLE-FILE PRODUCTS
# ════════════════════════════════════════════════════════════

print("\n  [1/2] Single-file products ...")
for pname in SINGLE_FILE_PRODUCTS:
    wa016_csv = DATA_DIR / f"wa016_{pname}_2001_2020.csv"
    if not wa016_csv.exists():
        print(f"  ⚠  {wa016_csv.name} not found — skipping {pname}")
        continue

    df = pd.read_csv(wa016_csv)
    wa016 = _clean_wa016(df, pname)
    if wa016 is None or wa016.empty:
        print(f"  ⚠  {wa016_csv.name}: no valid data — skipping {pname}")
        continue

    expected = (END_YEAR - START_YEAR + 1) * 12
    print(f"  {pname}: {len(wa016)} rows (expected {expected})")
    _append_to_product_csv(wa016, pname)


# ════════════════════════════════════════════════════════════
# § 2  MERRA2 — YEARLY FILES
# ════════════════════════════════════════════════════════════

print("\n  [2/2] MERRA2 — yearly files ...")

# Collect all yearly WA016 MERRA2 CSVs
yearly_dfs = []
for yr in range(START_YEAR, END_YEAR + 1):
    # Try both naming conventions
    candidates = [
        DATA_DIR / f"wa016_MERRA2_{yr}.csv",
        DATA_DIR / f"wa016_MERRA2_{yr}_{yr}.csv",
    ]
    found = None
    for p in candidates:
        if p.exists():
            found = p
            break

    if found is None:
        print(f"  ⚠  wa016_MERRA2_{yr}.csv not found — skipping year {yr}")
        continue

    df = pd.read_csv(found)
    wa016_yr = _clean_wa016(df, "MERRA2", yr_filter=yr)

    if wa016_yr is None or wa016_yr.empty:
        print(f"  ⚠  {found.name}: no valid data for {yr}")
        continue

    flag = "✓" if len(wa016_yr) == 12 else "⚠"
    print(f"  {flag}  {found.name} → {len(wa016_yr)} rows "
          f"(expected 12)")
    yearly_dfs.append(wa016_yr)

if not yearly_dfs:
    print("   No WA016 MERRA2 yearly data found")
    print("     Run extract_wa016_merra2.py and download CSVs first")
else:
    wa016_merra2 = pd.concat(yearly_dfs, ignore_index=True)
    wa016_merra2 = wa016_merra2.drop_duplicates(
        subset=["station_id","year","month"]
    )
    total = len(wa016_merra2)
    expected = (END_YEAR - START_YEAR + 1) * 12
    flag = "" if total == expected else "⚠"
    print(f"\n  {flag} MERRA2 WA016 total: {total} rows (expected {expected})")
    print(f"     Years covered: {sorted(wa016_merra2['year'].unique())}")
    _append_to_product_csv(wa016_merra2, "MERRA2")


print(f"""
  ════════════════════════════════════════════════
  DONE — all product CSVs updated with WA016
  ════════════════════════════════════════════════
  NEXT:
    python merge_extractions.py
    python validation_metrics.py
    python visualisation.py
""")
