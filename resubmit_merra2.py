"""
============================================================
RE-SUBMIT MERRA2 EXTRACTION FROM YEARLY ASSETS
============================================================
Run this to re-extract MERRA2 2001-2020 from the pre-exported
climatology assets in GEE.

HOW TO RUN
───────────
  python resubmit_merra2.py

This submits 20 small tasks (one per year).
Each task reads 1 asset image × 15 stations × 12 months = 180 rows.
Should complete in ~5-10 minutes per task.

AFTER ALL 20 TASKS COMPLETE
─────────────────────────────
Download all precip_extraction_MERRA2_YYYY.csv from Drive to DATA_DIR
then run: python merge_extractions.py
============================================================
"""

import ee
from setup_config import CONFIG

ee.Initialize(project="ee-desmond")

DATA_DIR    = CONFIG["data_dir"]
ASSET_BASE  = CONFIG.get("asset_folder", "projects/ee-desmond/assets/")
DRIVE_FOLDER = CONFIG.get("drive_folder", "GEE_Exports")
START_YEAR  = 2001
END_YEAR    = 2020

# Station coordinates (lon, lat) — same as used throughout pipeline
STATIONS = {
    "WA001": (-17.47,  14.73),
    "WA002": ( -7.95,  12.65),
    "WA003": ( -1.52,  12.36),
    "WA004": (  2.17,  13.51),
    "WA005": (  7.33,   9.07),
    "WA006": ( -0.17,   5.56),
    "WA007": ( -3.93,   5.35),
    "WA008": (-13.67,   9.53),
    "WA009": (-13.23,   8.49),
    "WA010": (-10.80,   6.30),
    "WA011": (  1.22,   6.13),
    "WA012": (  2.42,   6.37),
    "WA013": (  8.52,  12.05),
    "WA014": ( -1.62,   6.69),
    "WA015": (-16.68,  13.45),
}

# Build station FeatureCollection
station_features = [
    ee.Feature(
        ee.Geometry.Point([lon, lat]),
        {"station_id": sid}
    )
    for sid, (lon, lat) in STATIONS.items()
]
station_fc = ee.FeatureCollection(station_features)

TARGET_SCALE_M = 27830  # 0.25 degrees in metres

print("=" * 60)
print("  MERRA2 ASSET-BASED RE-EXTRACTION")
print("=" * 60)
print(f"  Asset base : {ASSET_BASE}")
print(f"  Drive folder: {DRIVE_FOLDER}")
print(f"  Years      : {START_YEAR}–{END_YEAR}")
print(f"  Stations   : {len(STATIONS)}")
print()

# ── Submit one task per year ──────────────────────────────
tasks = {}
for yr in range(START_YEAR, END_YEAR + 1):
    asset_id = f"{ASSET_BASE}climatology_MERRA2_{yr}"

    try:
        clim_img = ee.Image(asset_id)
        # Test the asset exists by getting info
        # (comment out if it slows down submission)
        # info = clim_img.getInfo()

        # Build FC: one feature per month per station
        # Use a simpler approach: sample each band separately
        # Band names in the asset: month_01, month_02, ..., month_12
        month_fcs = []
        for mo in range(1, 13):
            band_name = f"month_{str(mo).zfill(2)}"

            # Sample this month's band at all stations
            # Use mean reducer with rename to get a clean column name
            sampled = clim_img.select([band_name]).rename(["precip_mm_day"]) \
                .reduceRegions(
                    collection = station_fc,
                    reducer    = ee.Reducer.mean(),   # mean of single pixel
                    scale      = TARGET_SCALE_M,
                )

            # Tag each feature with year/month/product
            def tag_feature(f):
                return f.set({
                    "product"      : "MERRA2",
                    "year"         : yr,
                    "month"        : mo,
                    "precip_mm_day": f.get("mean"),
                }).select(
                    ["station_id", "product", "year",
                     "month", "precip_mm_day"]
                )

            month_fcs.append(sampled.map(tag_feature))

        # Merge all 12 months
        year_fc = month_fcs[0]
        for mfc in month_fcs[1:]:
            year_fc = year_fc.merge(mfc)

        task = ee.batch.Export.table.toDrive(
            collection   = year_fc,
            description  = f"precip_extraction_MERRA2_{yr}",
            folder       = DRIVE_FOLDER,
            fileFormat   = "CSV",
        )
        task.start()
        tasks[yr] = task
        print(f"  ↗  Submitted: precip_extraction_MERRA2_{yr}.csv  "
              f"(asset: climatology_MERRA2_{yr})")

    except Exception as e:
        print(f"  ❌  Year {yr} failed: {e}")

print(f"\n  {len(tasks)} tasks submitted successfully.")
print(f"  Monitor: https://code.earthengine.google.com/tasks")
print(f"""
  AFTER ALL TASKS COMPLETE:
  ─────────────────────────────────────────────────────
  1. Download all precip_extraction_MERRA2_YYYY.csv from
     Google Drive folder '{DRIVE_FOLDER}' to:
     {DATA_DIR}

  2. Run: python merge_extractions.py
     (handles MERRA2 rebuild + full merge automatically)

  3. Run: python validation_metrics.py
  4. Run: python visualisation.py
  ─────────────────────────────────────────────────────
""")
