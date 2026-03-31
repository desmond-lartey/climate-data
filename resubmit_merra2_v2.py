"""
============================================================
RE-SUBMIT MERRA2 EXTRACTION v2 — uses sampleRegions
============================================================
Run:  python resubmit_merra2_v2.py
============================================================
"""

import ee
from setup_config import CONFIG

ee.Initialize(project="ee-desmond")

DATA_DIR     = CONFIG["data_dir"]
ASSET_BASE   = CONFIG.get("asset_folder", "projects/ee-desmond/assets/")
DRIVE_FOLDER = CONFIG.get("drive_folder", "GEE_Exports")
START_YEAR   = 2001
END_YEAR     = 2020
TARGET_SCALE = 27830

STATIONS = {
    "WA001": (-17.47,  14.73), "WA002": ( -7.95,  12.65),
    "WA003": ( -1.52,  12.36), "WA004": (  2.17,  13.51),
    "WA005": (  7.33,   9.07), "WA006": ( -0.17,   5.56),
    "WA007": ( -3.93,   5.35), "WA008": (-13.67,   9.53),
    "WA009": (-13.23,   8.49), "WA010": (-10.80,   6.30),
    "WA011": (  1.22,   6.13), "WA012": (  2.42,   6.37),
    "WA013": (  8.52,  12.05), "WA014": ( -1.62,   6.69),
    "WA015": (-16.68,  13.45),
}

station_features = [
    ee.Feature(ee.Geometry.Point([lon, lat]), {"station_id": sid})
    for sid, (lon, lat) in STATIONS.items()
]
station_fc = ee.FeatureCollection(station_features)

print("=" * 60)
print("  MERRA2 RE-EXTRACTION v2 (sampleRegions)")
print("=" * 60)
print(f"  Asset base  : {ASSET_BASE}")
print(f"  Drive folder: {DRIVE_FOLDER}")
print(f"  Years       : {START_YEAR}–{END_YEAR}")
print()

tasks = {}
for yr in range(START_YEAR, END_YEAR + 1):
    asset_id = f"{ASSET_BASE}climatology_MERRA2_{yr}"
    clim_img = ee.Image(asset_id)

    month_fcs = []
    for mo in range(1, 13):
        band_name = f"month_{str(mo).zfill(2)}"

        # Use sampleRegions — designed for point extraction
        # Returns one feature per station with band value as property
        sampled = clim_img.select([band_name]).sampleRegions(
            collection = station_fc,
            properties = ["station_id"],
            scale      = TARGET_SCALE,
            geometries = False,
        )

        # Rename band value → precip_mm_day, add metadata
        def tag(f, mo=mo, yr=yr):
            return f.set({
                "product"      : "MERRA2",
                "year"         : yr,
                "month"        : mo,
                "precip_mm_day": f.get(band_name),
            }).select(["station_id","product","year",
                       "month","precip_mm_day"])

        month_fcs.append(sampled.map(tag))

    # Merge all 12 months into one FC for this year
    year_fc = month_fcs[0]
    for mfc in month_fcs[1:]:
        year_fc = year_fc.merge(mfc)

    task = ee.batch.Export.table.toDrive(
        collection  = year_fc,
        description = f"precip_extraction_MERRA2_{yr}",
        folder      = DRIVE_FOLDER,
        fileFormat  = "CSV",
    )
    task.start()
    tasks[yr] = task
    print(f"  ↗  {yr} submitted")

print(f"\n  ✅ {len(tasks)} tasks submitted")
print(f"  Monitor: https://code.earthengine.google.com/tasks")
print(f"""
  WHEN ALL COMPLETE:
    1. Download precip_extraction_MERRA2_YYYY.csv to DATA_DIR
    2. python merge_extractions.py
    3. python validation_metrics.py
    4. python visualisation.py
""")
