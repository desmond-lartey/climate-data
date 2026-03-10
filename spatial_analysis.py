"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 4: Spatial Analysis & Bias Mapping (GEE + geemap)
============================================================
Computes pixel-wise differences, correlations, and trend maps
between precipitation products over the study domain.
"""

import ee
import geemap
import numpy as np
from pathlib import Path
from setup_config import CONFIG, PRODUCTS, TARGET_SCALE_M
from data_ingestion import COLLECTIONS, ROI

DATA_DIR    = Path(CONFIG["data_dir"])
FIGURES_DIR = Path(CONFIG["figures_dir"])


# ══════════════════════════════════════════════════════════
# 4.1  Long-term mean annual precipitation maps
# ══════════════════════════════════════════════════════════

def compute_annual_mean(product_name: str) -> ee.Image:
    """Long-term mean annual precipitation (mm/year) for the full record."""
    ic   = COLLECTIONS[product_name]
    # mm/day × 30.44 days/month × 12 months = mm/year
    mean = ic.select("precip_mm_day").mean().multiply(365.25)
    return mean.rename(f"map_precip_{product_name}")


# ══════════════════════════════════════════════════════════
# 4.2  Pixel-wise bias relative to GPCC (reference)
# ══════════════════════════════════════════════════════════

def compute_bias_map(product_name: str,
                     reference: str = "GPCC_MONTHLY") -> ee.Image:
    """
    Pixel-wise mean bias = product_mean - reference_mean  (mm/day).
    Also computes percent bias.
    """
    prod_mean = COLLECTIONS[product_name].select("precip_mm_day").mean()
    ref_mean  = COLLECTIONS[reference].select("precip_mm_day").mean()

    bias  = prod_mean.subtract(ref_mean).rename("bias_mm_day")
    pbias = (prod_mean.subtract(ref_mean)
                      .divide(ref_mean.add(1e-6))
                      .multiply(100)
                      .rename("pbias_pct"))
    return bias.addBands(pbias)


# ══════════════════════════════════════════════════════════
# 4.3  Pixel-wise Pearson correlation map (product vs reference)
# ══════════════════════════════════════════════════════════

def compute_correlation_map(product_name: str,
                             reference: str = "GPCC_MONTHLY") -> ee.Image:
    """
    Monthly time-series correlation at each pixel.
    Uses ee.Reducer.pearsonsCorrelation on band pairs.
    """
    prod_ic = COLLECTIONS[product_name].select("precip_mm_day")
    ref_ic  = COLLECTIONS[reference].select("precip_mm_day")

    # Join on system:time_start
    joined = prod_ic.map(lambda img: (
        img.addBands(
            ref_ic.filterDate(
                img.date(),
                img.date().advance(1, "month")
            ).first().rename("ref")
        )
    ))

    corr = joined.select(["precip_mm_day", "ref"]).reduce(
        ee.Reducer.pearsonsCorrelation()
    )
    return corr.rename(["r", "p_value"])


# ══════════════════════════════════════════════════════════
# 4.4  Trend analysis (Mann-Kendall via linear regression proxy)
# ══════════════════════════════════════════════════════════

def compute_trend_map(product_name: str) -> ee.Image:
    """
    Pixel-wise linear trend slope (mm/day per year) using
    ee.Reducer.linearFit on the monthly time series.
    """
    ic = COLLECTIONS[product_name].select("precip_mm_day")

    # Add time band (years from start)
    start_millis = ee.Date(CONFIG["start_date"]).millis()
    ms_per_year  = 1000 * 60 * 60 * 24 * 365.25

    def add_time(img):
        t = (img.date().millis().subtract(start_millis)
                .divide(ms_per_year).float())
        return img.addBands(ee.Image.constant(t).rename("time"))

    ic_t = ic.map(add_time)
    fit  = ic_t.select(["time", "precip_mm_day"]).reduce(
        ee.Reducer.linearFit()
    )
    return fit.select("scale").rename(f"trend_{product_name}")   # slope


# ══════════════════════════════════════════════════════════
# 4.5  Interactive geemap visualisation
# ══════════════════════════════════════════════════════════

VIS_PRECIP  = {"min": 0,    "max": 3000,
               "palette": ["white","#c6dbef","#6baed6",
                            "#2171b5","#08306b"]}
VIS_BIAS    = {"min": -3,   "max": 3,
               "palette": ["red","white","blue"]}
VIS_CORR    = {"min": 0,    "max": 1,
               "palette": ["white","yellow","green","darkgreen"]}
VIS_TREND   = {"min": -0.01,"max": 0.01,
               "palette": ["brown","white","darkblue"]}


def build_comparison_map(products_to_show: list = None,
                          reference: str = "GPCC_MONTHLY") -> geemap.Map:
    """
    Interactive map with toggleable layers:
      – Annual precipitation per product
      – Bias vs reference
      – Correlation vs reference
    """
    if products_to_show is None:
        products_to_show = [k for k in PRODUCTS if k != reference]

    m = geemap.Map(center=[0, 20], zoom=2)
    m.addLayer(compute_annual_mean(reference).clip(ROI),
               VIS_PRECIP, f"Mean Precip – {reference} (mm/yr)", True)

    for pname in products_to_show:
        ann  = compute_annual_mean(pname).clip(ROI)
        bias = compute_bias_map(pname, reference).select("bias_mm_day").clip(ROI)
        corr = compute_correlation_map(pname, reference).select("r").clip(ROI)

        m.addLayer(ann,  VIS_PRECIP, f"Mean Precip – {pname}",     False)
        m.addLayer(bias, VIS_BIAS,   f"Bias – {pname} vs {reference}", False)
        m.addLayer(corr, VIS_CORR,   f"Correlation – {pname}",     False)

    m.addLayerControl()
    return m


def build_trend_map(products_to_show: list = None) -> geemap.Map:
    """Interactive trend magnitude map for each product."""
    if products_to_show is None:
        products_to_show = list(PRODUCTS.keys())

    m = geemap.Map(center=[0, 20], zoom=2)
    for pname in products_to_show:
        trend = compute_trend_map(pname).clip(ROI)
        m.addLayer(trend, VIS_TREND, f"Trend – {pname} (mm/day/yr)", False)

    m.addLayerControl()
    return m


# ══════════════════════════════════════════════════════════
# 4.6  Export bias and correlation maps to Drive
# ══════════════════════════════════════════════════════════

def export_spatial_metrics(product_name: str,
                            reference:    str = "GPCC_MONTHLY",
                            drive_folder: str = "Precip_Assessment"):
    bias_img = compute_bias_map(product_name, reference).clip(ROI)
    corr_img = compute_correlation_map(product_name, reference).clip(ROI)
    ann_img  = compute_annual_mean(product_name).clip(ROI)

    for img, label in [(bias_img, "bias"),
                       (corr_img, "correlation"),
                       (ann_img,  "annual_mean")]:
        task = ee.batch.Export.image.toDrive(
            image          = img,
            description    = f"{label}_{product_name}",
            folder         = drive_folder,
            fileNamePrefix = f"{label}_{product_name}",
            region         = ROI,
            scale          = TARGET_SCALE_M,
            crs            = "EPSG:4326",
            maxPixels      = 1e13,
        )
        task.start()
        print(f"  ↗ Export: {label}_{product_name}")


# ══════════════════════════════════════════════════════════
# 4.7  Run
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Interactive maps (run in Jupyter)
    map_compare = build_comparison_map()
    map_trend   = build_trend_map()
    # map_compare   # display in notebook cell
    # map_trend     # display in notebook cell

    # Export spatial metrics for all products
    for pname in [k for k in PRODUCTS if k != "GPCC_MONTHLY"]:
        export_spatial_metrics(pname)

    print(" Spatial analysis complete. Export tasks submitted.")
