"""
============================================================
EXTRACT WA016 MERRA2 — FROM YEARLY CLIMATOLOGY ASSETS
============================================================
Uses pre-exported climatology_MERRA2_YYYY assets with
sampleRegions — same approach as resubmit_merra2_v2.py
which successfully completed in minutes per year.

Submits 20 small tasks (one per year).
Each reads 1 asset × 12 months × 1 station = 12 rows.
Should complete in <5 minutes per task.

Run:  python extract_wa016_merra2.py

AFTER ALL 20 TASKS COMPLETE:
  Download wa016_MERRA2_YYYY.csv files from Drive to DATA_DIR
  Then run: python append_wa016_merra2.py
============================================================
"""

import ee
from setup_config import CONFIG

ee.Initialize(project="ee-desmond")

ASSET_BASE   = CONFIG.get("asset_folder", "projects/ee-desmond/assets/")
DRIVE_FOLDER = CONFIG.get("drive_folder", "GEE_Exports")
START_YEAR   = 2001
END_YEAR     = 2020
TARGET_SCALE = 27830

# Nouakchott only
WA016_FC = ee.FeatureCollection([
    ee.Feature(
        ee.Geometry.Point([-15.97, 18.07]),
        {"station_id": "WA016"}
    )
])

print("=" * 60)
print("  WA016 MERRA2 EXTRACTION (asset-based, sampleRegions)")
print("=" * 60)
print(f"  Station : WA016 Nouakchott (-15.97, 18.07)")
print(f"  Asset   : {ASSET_BASE}climatology_MERRA2_YYYY")
print(f"  Years   : {START_YEAR}–{END_YEAR}")
print()

tasks = {}
for yr in range(START_YEAR, END_YEAR + 1):
    asset_id = f"{ASSET_BASE}climatology_MERRA2_{yr}"
    clim_img = ee.Image(asset_id)

    month_fcs = []
    for mo in range(1, 13):
        band_name = f"month_{str(mo).zfill(2)}"

        # sampleRegions on single-band image — reliable point extraction
        sampled = clim_img.select([band_name]).sampleRegions(
            collection = WA016_FC,
            properties = ["station_id"],
            scale      = TARGET_SCALE,
            geometries = False,
        )

        def tag(f, mo=mo, yr=yr, band_name=band_name):
            return f.set({
                "product"      : "MERRA2",
                "year"         : yr,
                "month"        : mo,
                "precip_mm_day": f.get(band_name),
            }).select(["station_id","product","year",
                       "month","precip_mm_day"])

        month_fcs.append(sampled.map(tag))

    # Merge 12 months into one FC for this year
    year_fc = month_fcs[0]
    for mfc in month_fcs[1:]:
        year_fc = year_fc.merge(mfc)

    task = ee.batch.Export.table.toDrive(
        collection  = year_fc,
        description = f"wa016_MERRA2_{yr}",
        folder      = DRIVE_FOLDER,
        fileFormat  = "CSV",
    )
    task.start()
    tasks[yr] = task
    print(f"  ↗  Submitted: wa016_MERRA2_{yr}.csv")

print(f"""
   {len(tasks)} tasks submitted. 
  Monitor: https://code.earthengine.google.com/tasks

  Each task reads from pre-built asset — no hourly reprocessing.
  Expected runtime: <5 min per task.

  AFTER ALL COMPLETE:
    1. Download wa016_MERRA2_YYYY.csv to DATA_DIR
    2. python append_wa016_merra2.py
    3. python merge_extractions.py
    4. python validation_metrics.py
""")
