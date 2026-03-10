"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 1: Data Ingestion & Pre-processing in Google Earth Engine
============================================================
Loads each product, harmonises units → mm/day,
resamples to a common grid, and aggregates to monthly totals (mm/month).
Run AFTER setup_config.py in the same session.
"""

import ee
import geemap
import numpy as np
from setup_config import CONFIG, PRODUCTS    # adjust import if running standalone


# ══════════════════════════════════════════════════════════
# 1.1  Region of Interest
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
# 1.1  Region of Interest
# ══════════════════════════════════════════════════════════

def build_roi():
    """Load ROI from Earth Engine asset."""
    roi_asset = CONFIG["roi_asset"]

    fc = ee.FeatureCollection(roi_asset)
    roi = fc.geometry().dissolve()

    print(f" ROI : asset loaded → {roi_asset}")
    return roi

ROI = build_roi()


# ══════════════════════════════════════════════════════════
# 1.2  Helper – load & harmonise one product
# ══════════════════════════════════════════════════════════

def load_product(name: str, roi: ee.Geometry,
                 start: str, end: str) -> ee.ImageCollection:
    """
    Load a GEE collection, select the precip band,
    apply scale factor, clip to ROI, and tag with metadata.
    Returns an ImageCollection with band 'precip_mm_day'.
    """
    p = PRODUCTS[name]
    raw = (ee.ImageCollection(p["collection"])
             .filterDate(start, end)
             .filterBounds(roi)
             .select([p["band"]]))

    def harmonise(img):
        # Convert to mm/day
        scaled = img.multiply(p["scale_factor"]).rename("precip_mm_day")
        # For GPM (30-min intervals, units mm/hr) → mm/day = value × 24
        if name == "GPM_IMERG":
            scaled = scaled.multiply(24)
        # Mask negatives
        scaled = scaled.updateMask(scaled.gte(0))
        return (scaled
                .copyProperties(img, ["system:time_start", "system:time_end"])
                .set("product", name)
                .set("type",    p["type"]))

    return raw.map(harmonise)


def aggregate_monthly(ic: ee.ImageCollection, product_name: str):

    p = PRODUCTS[product_name]

    # If already monthly dataset → skip aggregation
    if p["temporal"] == "monthly":
        return ic

    start_year = int(CONFIG["start_date"][:4])
    end_year   = int(CONFIG["end_date"][:4])

    months = ee.List.sequence(0, (end_year - start_year + 1) * 12 - 1)

    def make_month(n):

        n = ee.Number(n)

        date = ee.Date.fromYMD(start_year, 1, 1).advance(n, "month")
        start = date
        end   = date.advance(1, "month")

        img = (ic.filterDate(start, end)
                 .sum()
                 .rename("precip_mm_month")
                 .set("system:time_start", start.millis())
                 .set("year", start.get("year"))
                 .set("month", start.get("month")))

        return img

    return ee.ImageCollection(months.map(make_month))


# ══════════════════════════════════════════════════════════
# 1.3  Resample all products to common grid
# ══════════════════════════════════════════════════════════

TARGET_SCALE_M = int(CONFIG["target_resolution_deg"] * 111_320)   # approx metres

def resample_to_common(ic):

    def _resample(img):

        img = ee.Image(img)

        return img.resample("bilinear").reproject(
            crs="EPSG:4326",
            scale=TARGET_SCALE_M
        )

    return ic.map(_resample) 


# ══════════════════════════════════════════════════════════
# 1.4  Load ALL productss
# ══════════════════════════════════════════════════════════

print("Loading and harmonising products …")
START = CONFIG["start_date"]
END   = CONFIG["end_date"]

COLLECTIONS = {}        # harmonised + resampled monthly ImageCollections

for pname in PRODUCTS:
    print(f"  • {pname}")
    raw_ic      = load_product(pname, ROI, START, END)
    monthly_ic = aggregate_monthly(raw_ic, pname)
    resampled   = resample_to_common(monthly_ic)
    COLLECTIONS[pname] = resampled

print(" All products loaded and resampled.")


# ══════════════════════════════════════════════════════════
# 1.5  Quick interactive map (geemap)
# ══════════════════════════════════════════════════════════

def preview_products(year: int = 2010, month: int = 6,
                     products_to_show: list = None):
    """
    Display mean monthly precipitation for a given month/year
    for selected products side-by-side in a geemap split map.
    """
    if products_to_show is None:
        products_to_show = ["CHIRPS", "ERA5", "GPCC_MONTHLY"]

    m = geemap.Map(center=[0, 20], zoom=2)
    vis = {"min": 0, "max": 10,
           "palette": ["white", "blue", "cyan", "green",
                        "yellow", "orange", "red"]}

    for pname in products_to_show:
        img = (COLLECTIONS[pname]
               .filter(ee.Filter.And(
                   ee.Filter.eq("year",  year),
                   ee.Filter.eq("month", month)))
               .first())
        m.addLayer(img.select("precip_mm_month"), vis, pname)

    m.addLayerControl()
    return m

# preview_products(2010, 6)   # ← uncomment to display in Jupyter


# ══════════════════════════════════════════════════════════
# 1.6  Export monthly mean climatologies to Google Drive
# ══════════════════════════════════════════════════════════

def export_climatology(product_name: str,
                        drive_folder: str = "Precip_Assessment"):
    """
    Compute long-term monthly climatology (12 images × 1 mean each)
    and export to Google Drive as a multi-band GeoTIFF.
    """
    ic     = COLLECTIONS[product_name]
    months = ee.List.sequence(1, 12)

    def monthly_clim(m):
        m   = ee.Number(m).toInt()
        img = (ic.filter(ee.Filter.eq("month", m))
                 .mean()
                 .rename(ee.String("month_").cat(m.format())))
        return img

    clim_imgs = ee.ImageCollection(months.map(monthly_clim))
    clim_img  = clim_imgs.toBands().clip(ROI)

    task = ee.batch.Export.image.toDrive(
        image       = clim_img,
        description = f"Climatology_{product_name}",
        folder      = drive_folder,
        fileNamePrefix = f"climatology_{product_name}",
        region      = ROI,
        scale       = TARGET_SCALE_M,
        crs         = "EPSG:4326",
        maxPixels   = 1e13,
    )
    task.start()
    print(f"  ↗ Export started : Climatology_{product_name} → Drive/{drive_folder}/")
    return task


if __name__ == "__main__":

    # Export climatologies for all products except GPCC
    tasks = {}

    for pname in PRODUCTS:

        if pname == "GPCC_MONTHLY":
            print("Skipping GPCC export (not available in GEE)")
            continue

        print(f"Starting export for {pname}")

        tasks[pname] = export_climatology(pname)

    print(f"\n{len(tasks)} export tasks submitted.")
    print("Monitor progress at:")
    print("https://code.earthengine.google.com/tasks")
