"""
============================================================
EXTRACT WA016 (TAMANRASSET) — ALL 6 PRODUCTS
============================================================
Uses sampleRegions (same approach as resubmit_merra2_v2.py
which successfully returned data).

Run:  python extract_wa016.py
============================================================
"""

import ee
from setup_config import CONFIG
from data_ingestion import COLLECTIONS

ee.Initialize(project="ee-desmond")

DRIVE_FOLDER = CONFIG.get("drive_folder", "GEE_Exports")
TARGET_SCALE = 27830

# Single station FeatureCollection
WA016_FC = ee.FeatureCollection([
    ee.Feature(
        ee.Geometry.Point([-15.97, 18.07]),  # ← Nouakchott
        {"station_id": "WA016"}
    )
]) 

print("=" * 60)
print("  WA016 EXTRACTION (sampleRegions)")
print("=" * 60)

tasks = {}
for pname, ic in COLLECTIONS.items():

    # Filter to study period
    ic_filtered = ic.filter(
        ee.Filter.And(
            ee.Filter.gte("year", 2001),
            ee.Filter.lte("year", 2020)
        )
    )

    def sample_image(img):
        yr  = img.get("year")
        mo  = img.get("month")

        # sampleRegions — reliable point extraction
        # returns band value as property named after the band
        sampled = img.select(["precip_mm_day"]).sampleRegions(
            collection = WA016_FC,
            properties = ["station_id"],
            scale      = TARGET_SCALE,
            geometries = False,
        )

        return sampled.map(
            lambda f: f.set({
                "product"      : pname,
                "year"         : yr,
                "month"        : mo,
                "precip_mm_day": f.get("precip_mm_day"),
            }).select(["station_id","product","year",
                       "month","precip_mm_day"])
        )

    product_fc = ic_filtered.map(sample_image).flatten()

    task = ee.batch.Export.table.toDrive(
        collection  = product_fc,
        description = f"wa016_{pname}_2001_2020",
        folder      = DRIVE_FOLDER,
        fileFormat  = "CSV",
    )
    task.start()
    tasks[pname] = task
    print(f"  ↗  Submitted: wa016_{pname}_2001_2020.csv")

print(f"""
  {len(tasks)} tasks submitted.
  Monitor: https://code.earthengine.google.com/tasks

  AFTER ALL COMPLETE:
    1. Download wa016_<PRODUCT>_2001_2020.csv to DATA_DIR
    2. python append_wa016.py
    3. python merge_extractions.py
    4. python validation_metrics.py
    5. python visualisation.py
""")
