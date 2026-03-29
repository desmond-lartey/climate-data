"""
============================================================
MERRA-2 MERGE RUNNER
West Africa Precipitation Assessment  |  2001–2020
============================================================
Run this script ONCE to merge the 22 yearly MERRA-2
climatology assets into a single final product.

Usage:
    python run_merra2_merge.py

What it does:
    1. Confirms all 20 study-period yearly assets exist
    2. Submits Asset export  → climatology_MERRA2
    3. Submits Drive export  → climatology_MERRA2.tif
    4. Prints task IDs for monitoring

After both tasks complete:
    → Run gauge_extraction.py to get CHIRPS + MERRA2 CSVs
============================================================
"""

import ee
from data_ingestion import (
    merge_merra2_yearly_assets,
    CONFIG,
)

# ── Study period years (2001–2020, 20 years) ─────────────
# Assets for 2000 and 2021 exist but are outside study period.
STUDY_YEARS = list(range(2001, 2021))

print("\n" + "═" * 60)
print("  MERRA-2 MERGE RUNNER")
print("═" * 60)
print(f"  Study years : {STUDY_YEARS[0]} – {STUDY_YEARS[-1]}")
print(f"  Total years : {len(STUDY_YEARS)}")
print(f"  Asset folder: {CONFIG['asset_folder']}")

# ── Step 1: Verify all yearly assets exist before merging ─
print("\n  Verifying yearly assets …")
missing_years = []

for yr in STUDY_YEARS:
    asset_id = CONFIG["asset_folder"] + f"climatology_MERRA2_{yr}"
    try:
        ee.Image(asset_id).bandNames().getInfo()
        print(f"     {yr}  →  {asset_id}")
    except Exception:
        print(f"    ❌ {yr}  →  MISSING: {asset_id}")
        missing_years.append(yr)

if missing_years:
    print(f"""
  ══════════════════════════════════════════════════════
  ❌  MERGE ABORTED — {len(missing_years)} yearly asset(s) missing
  ══════════════════════════════════════════════════════
  Missing years: {missing_years}

  Re-run yearly exports for missing years:
      from data_ingestion import export_climatology_merra2_yearly
      export_climatology_merra2_yearly(
          years          = {missing_years},
          completed_years = {[y for y in STUDY_YEARS if y not in missing_years]}
      )
  Then re-run this script once those tasks complete.
  ══════════════════════════════════════════════════════
    """)
    raise SystemExit(1)

print(f"\n   All {len(STUDY_YEARS)} yearly assets confirmed present.")

# ── Step 2: Submit merge tasks ────────────────────────────
print("\n  Submitting merge tasks …")
print("─" * 60)

tasks = merge_merra2_yearly_assets(years=STUDY_YEARS)

# ── Step 3: Report task IDs for monitoring ────────────────
print("\n" + "═" * 60)
print("  MERGE TASKS SUBMITTED SUCCESSFULLY")
print("═" * 60)

asset_task = tasks.get("asset")
drive_task = tasks.get("drive")

if asset_task:
    status = asset_task.status()
    print(f"  Asset task ID : {status.get('id', 'N/A')}")
    print(f"  Asset task    : {status.get('description', 'N/A')}")
    print(f"  State         : {status.get('state', 'N/A')}")

if drive_task:
    status = drive_task.status()
    print(f"\n  Drive task ID : {status.get('id', 'N/A')}")
    print(f"  Drive task    : {status.get('description', 'N/A')}")
    print(f"  State         : {status.get('state', 'N/A')}")

print(f"""
  ══════════════════════════════════════════════════════
  WHAT HAPPENS NEXT
  ══════════════════════════════════════════════════════
  Expected runtime : 30–90 minutes for both tasks

  Monitor tasks:
    https://code.earthengine.google.com/tasks

  Asset output:
    {CONFIG['asset_folder']}climatology_MERRA2
    Bands: month_01 … month_12  (float32, mm/day)

  Drive output:
    {CONFIG['drive_folder']}/climatology_MERRA2.tif

  AFTER BOTH COMPLETE → run:
    python gauge_extraction.py

  This will:
    A) Re-submit CHIRPS CSV extraction  (asset ready now)
    B) Submit MERRA2 CSV extraction     (asset will be ready)
    C) Run partial merge of available CSVs
  ══════════════════════════════════════════════════════
""")
