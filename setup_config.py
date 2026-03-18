"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 0: Environment Setup & Configuration
============================================================
Install dependencies (run once in terminal):
    conda install -c conda-forge -y \
        geemap earthengine-api xarray pandas numpy scipy \
        matplotlib seaborn cartopy netCDF4 geopandas rasterio

Then authenticate once:
    earthengine authenticate

METHODOLOGICAL NOTES
─────────────────────────────────────────────────────────
TARGET UNIT : mm/day  (mean daily rate)
  All products are harmonised to mm/day BEFORE any monthly
  aggregation or comparison.  This is the scientifically
  correct common unit because:
    • It is independent of month length (28/29/30/31 days)
    • It allows direct comparison across all temporal scales
    • It matches WMO convention for precipitation reporting

TEMPORAL SCALE : monthly mean (mm/day)
  Even though source collections have different native
  temporal resolutions (daily, monthly, hourly), all are
  reduced to a monthly mean mm/day value before export,
  comparison, or validation.

AGGREGATION RULES per product type
  daily  → monthly mean of daily mm/day values
             (.mean() NOT .sum())
  monthly→ already one value per month; apply unit
             conversion then store directly
  hourly → monthly mean of hourly mm/day values
             (.mean() NOT .sum())

CONVERSIONS
  Product         Raw unit         → Target mm/day
  ─────────────────────────────────────────────────
  CHIRPS          mm/day           → ×1.0  (no change)
  PERSIANN-CDR    mm/day           → ×1.0  (no change)
  TRMM 3B43       mm/hr (monthly)  → ×24.0
  GPM IMERG       mm/hr (monthly)  → ×24.0
  ERA5-Land       m/month          → ×1000 ÷ days_in_month
                  *** CANNOT use a fixed scale_factor ***
                  *** must be computed per-image in    ***
                  *** data_ingestion.py                ***
  MERRA-2         kg/m²/s (hourly) → ×86400
  TerraClimate    mm/month         → ÷ days_in_month
                  *** CANNOT use a fixed scale_factor ***

STUDY PERIOD ALIGNMENT
  Start : 2001-01-01  (TRMM 3B43 available from 1998;
                        GPM IMERG from 2000-06)
  End   : 2020-12-31  (TRMM 3B43 ends 2019-12, so for
                        full overlap use 2001–2019 when
                        including TRMM)
  Overlap window (all products): 2001-06 to 2019-12
============================================================
"""

import ee
import geemap
import os


# ── Authenticate & Initialize ─────────────────────────────
try:
    ee.Initialize(project='ee-desmond')
    print(" Earth Engine initialized successfully")
except Exception:
    ee.Authenticate()
    ee.Initialize(project='ee-desmond')


# ════════════════════════════════════════════════════════════
# § 0  GLOBAL CONFIGURATION
# ════════════════════════════════════════════════════════════

CONFIG = {

    # ── Study period ─────────────────────────────────────────
    # Aligned to full overlap of all products including TRMM.
    # Extend end_date to "2021-01-01" if excluding TRMM.
    "start_date" : "2000-01-01",
    "end_date"   : "2021-01-01",

    # ── Region of interest ───────────────────────────────────
    "roi_asset"  : "projects/ee-desmond/assets/west_africa_boundary0",

    # ── Target unit (all products harmonised to this) ────────
    # mm/day = mean daily rate; month-length independent
    "target_unit": "mm/day",

    # ── Temporal scale of analysis ───────────────────────────
    # "monthly" = monthly mean mm/day  ← recommended
    # "annual"  = annual  mean mm/day  (derived from monthly)
    "temporal_scale": "monthly",

    # ── Spatial resolution for inter-comparison ──────────────
    # 0.25° ≈ 25 km — matches the coarsest product (TRMM/MERRA-2)
    # All products are resampled to this grid before comparison.
    "target_resolution_deg" : 0.25,
    "target_resolution_m"   : 27830,   # metres (for ee.reproject)
    "resample_method"        : "bilinear",

    # ── Rain / no-rain threshold for categorical metrics ──────
    # Must match GEE JS version (1.0 mm/day)
    "rain_threshold_mm_day"  : 1.0,

    # ── Output directories ───────────────────────────────────
    "output_dir" : "outputs/precipitation_assessment",
    "figures_dir": "outputs/precipitation_assessment/figures",
    "data_dir"   : "outputs/precipitation_assessment/data",

    # ── GEE Asset folder for intermediate exports ─────────────
    "asset_folder": "projects/ee-desmond/assets/",

    # ── Google Drive folder for final GeoTIFF exports ─────────
    "drive_folder": "WA_Precip_Assessment",
}


# ════════════════════════════════════════════════════════════
# § 1  PRECIPITATION PRODUCTS CATALOGUE
#
#  Fields
#  ──────
#  collection     : GEE ImageCollection ID
#  band           : band name to select
#  native_temporal: "daily" | "monthly" | "hourly"
#                   Controls how data_ingestion.py aggregates
#  conversion     : "none" | "scale" | "era5_monthly" | "terra_monthly"
#                   Tells data_ingestion.py which conversion path to use
#  scale_factor   : multiplier applied BEFORE monthly aggregation
#                   For era5_monthly and terra_monthly this is None —
#                   the per-image conversion is done in data_ingestion.py
#  units_raw      : physical unit of the raw band values
#  units_out      : always "mm/day" after harmonisation
#  type           : product category (for grouping in plots/tables)
#  native_res_deg : native spatial resolution (for documentation)
#  notes          : any caveats or known issues
# ════════════════════════════════════════════════════════════

PRODUCTS = {

    # ── Satellite / Satellite-gauge merged ───────────────────

    "CHIRPS": {
        "collection"      : "UCSB-CHG/CHIRPS/DAILY",
        "band"            : "precipitation",
        "native_temporal" : "daily",
        # Daily values already in mm/day — just take monthly mean
        "conversion"      : "none",
        "scale_factor"    : 1.0,
        "units_raw"       : "mm/day",
        "units_out"       : "mm/day",
        "type"            : "satellite_gauge_merged",
        "native_res_deg"  : 0.05,
        "notes"           : "Aggregation: monthly mean of daily mm/day",
    },

    "PERSIANN_CDR": {
        "collection"      : "NOAA/PERSIANN-CDR",
        "band"            : "precipitation",
        "native_temporal" : "daily",
        # Daily values already in mm/day — just take monthly mean
        "conversion"      : "none",
        "scale_factor"    : 1.0,
        "units_raw"       : "mm/day",
        "units_out"       : "mm/day",
        "type"            : "satellite",
        "native_res_deg"  : 0.25,
        "notes"           : "Aggregation: monthly mean of daily mm/day",
    },

    # "TRMM_3B43": {
    #     "collection"      : "TRMM/3B43V7",
    #     "band"            : "precipitation",
    #     "native_temporal" : "monthly",
    #     # Raw: mm/hr  →  mm/day = raw × 24
    #     # Already one image per month; multiply then store directly.
    #     "conversion"      : "scale",
    #     "scale_factor"    : 24.0,
    #     "units_raw"       : "mm/hr",
    #     "units_out"       : "mm/day",
    #     "type"            : "satellite_gauge_corrected",
    #     "native_res_deg"  : 0.25,
    #     "notes"           : (
    #         "Available 1998-01 to 2019-12. "
    #         "Use 2001-2019 for full product overlap."
    #     ),
    # },

    "GPM_IMERG": {
        "collection"      : "NASA/GPM_L3/IMERG_MONTHLY_V07",
        "band"            : "precipitation",
        "native_temporal" : "monthly",
        # Raw: mm/hr  →  mm/day = raw × 24
        "conversion"      : "scale",
        "scale_factor"    : 24.0,
        "units_raw"       : "mm/hr",
        "units_out"       : "mm/day",
        "type"            : "satellite_gauge_merged",
        "native_res_deg"  : 0.1,
        "notes"           : "Available 2000-06 onwards.",
    },

    # ── Reanalysis ────────────────────────────────────────────

    "ERA5_LAND": {
        "collection"      : "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "band"            : "total_precipitation_sum",
        "native_temporal" : "monthly",
        # Raw: metres/month accumulated total
        # mm/day = raw × 1000 ÷ days_in_month
        # CANNOT use a fixed scale_factor — conversion is per-image.
        # data_ingestion.py must use the "era5_monthly" conversion path.
        "conversion"      : "era5_monthly",
        "scale_factor"    : None,
        "units_raw"       : "m/month",
        "units_out"       : "mm/day",
        "type"            : "reanalysis",
        "native_res_deg"  : 0.1,
        "notes"           : (
            "Conversion: img × 1000 ÷ ee.Date(img).advance(1,'month')"
            ".difference(ee.Date(img),'day'). "
            "Fixed scale_factor=1000 gives mm/month NOT mm/day — "
            "this was the root cause of the 'Image has no bands' error."
        ),
    },

    "MERRA2": {
        "collection"      : "NASA/GSFC/MERRA/flx/2",
        "band"            : "PRECTOTCORR",
        "native_temporal" : "hourly",
        # Raw: kg/m²/s  →  mm/day = raw × 86400
        # One image per hour; multiply then take monthly mean.
        "conversion"      : "scale",
        "scale_factor"    : 86400.0,
        "units_raw"       : "kg/m²/s",
        "units_out"       : "mm/day",
        "type"            : "reanalysis",
        "native_res_deg"  : 0.5,
        "notes"           : (
            "Hourly images. Aggregation: multiply × 86400 then "
            "take monthly mean (NOT sum) of the resulting mm/day values."
        ),
    },

    "TERRACLIMATE": {
        "collection"      : "IDAHO_EPSCOR/TERRACLIMATE",
        "band"            : "pr",
        "native_temporal" : "monthly",
        # Raw: mm/month accumulated total
        # mm/day = raw ÷ days_in_month
        # CANNOT use a fixed scale_factor — conversion is per-image.
        # data_ingestion.py must use the "terra_monthly" conversion path.
        "conversion"      : "terra_monthly",
        "scale_factor"    : None,
        "units_raw"       : "mm/month",
        "units_out"       : "mm/day",
        "type"            : "reanalysis_interpolated",
        "native_res_deg"  : 0.04,
        "notes"           : (
            "Conversion: img ÷ days_in_month. "
            "GEE catalogue scale=1 (no offset needed). "
            "Available 1958-01 onwards."
        ),
    },
}


# ════════════════════════════════════════════════════════════
# § 2  CONVERSION DISPATCH TABLE
#
#  Used by data_ingestion.py to select the correct
#  harmonisation function for each product.
#
#  "none"          → monthly mean of already-mm/day values
#  "scale"         → multiply by scale_factor first,
#                    then monthly mean
#  "era5_monthly"  → per-image: × 1000 ÷ days_in_month
#  "terra_monthly" → per-image: ÷ days_in_month
# ════════════════════════════════════════════════════════════

CONVERSION_TYPES = {
    "none"          : "Monthly mean of values already in mm/day",
    "scale"         : "Multiply by fixed scale_factor → mm/day, then monthly mean",
    "era5_monthly"  : "Per-image: metres × 1000 ÷ days_in_month → mm/day",
    "terra_monthly" : "Per-image: mm/month ÷ days_in_month → mm/day",
}


# ════════════════════════════════════════════════════════════
# § 3  VALIDATION METRICS
# ════════════════════════════════════════════════════════════

METRICS = {

    # ── Continuous metrics ───────────────────────────────────
    "continuous": [
        "bias",    # Mean Bias = mean(sim) − mean(obs)             [mm/day]
        "pbias",   # Percent Bias = bias / mean(obs) × 100         [%]
        "mae",     # Mean Absolute Error                           [mm/day]
        "rmse",    # Root Mean Squared Error                       [mm/day]
        "r",       # Pearson correlation coefficient               [−1, 1]
        "r2",      # Coefficient of determination                  [0, 1]
        "nse",     # Nash-Sutcliffe Efficiency                     [−∞, 1]
        "kge",     # Kling-Gupta Efficiency                        [−∞, 1]
    ],

    # ── Categorical metrics (require rain_threshold) ──────────
    # Applied at monthly scale: wet month = mean mm/day ≥ threshold
    "categorical": [
        "pod",     # Probability of Detection = H/(H+M)            [0, 1]
        "far",     # False Alarm Ratio        = FA/(H+FA)          [0, 1]
        "csi",     # Critical Success Index   = H/(H+M+FA)         [0, 1]
        "ets",     # Equitable Threat Score   (bias-corrected CSI) [0, 1]
        "freq_bias",# Frequency Bias          = (H+FA)/(H+M)      [>0]
    ],
}

# Flat list for legacy compatibility
METRICS_FLAT = METRICS["continuous"] + METRICS["categorical"]

# Rain threshold — must be consistent with GEE JS version
RAIN_THRESHOLD_MM_DAY = CONFIG["rain_threshold_mm_day"]   # 1.0 mm/day


# ════════════════════════════════════════════════════════════
# § 4  PRODUCT OVERLAP WINDOWS
#
#  Defines the safe date range for each product.
#  data_ingestion.py clips filterDate() to these windows
#  so no product is loaded outside its availability.
# ════════════════════════════════════════════════════════════

PRODUCT_DATE_RANGES = {
    "CHIRPS"       : ("1981-01-01", "2024-12-31"),
    "PERSIANN_CDR" : ("1983-01-01", "2024-12-31"),
    # "TRMM_3B43"    : ("1998-01-01", "2019-12-31"),   # ends Dec 2019...
    "GPM_IMERG"    : ("2000-06-01", "2024-12-31"),
    "ERA5_LAND"    : ("1950-01-01", "2024-12-31"),
    "MERRA2"       : ("1980-01-01", "2024-12-31"),
    "TERRACLIMATE" : ("1958-01-01", "2023-12-31"),
}

# Effective study window clipped to CONFIG dates AND product availability
def get_product_window(key):
    """Return (start, end) strings clipped to product availability."""
    p_start, p_end = PRODUCT_DATE_RANGES[key]
    c_start = CONFIG["start_date"]
    c_end   = CONFIG["end_date"]
    eff_start = max(p_start, c_start)
    eff_end   = min(p_end,   c_end)
    return eff_start, eff_end


# ════════════════════════════════════════════════════════════
# § 5  OUTPUT DIRECTORIES
# ════════════════════════════════════════════════════════════

for d in [CONFIG["output_dir"], CONFIG["figures_dir"], CONFIG["data_dir"]]:
    os.makedirs(d, exist_ok=True)


# ════════════════════════════════════════════════════════════
# § 6  STARTUP SUMMARY
# ════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print("  PRECIPITATION ASSESSMENT — Configuration Summary")
print("═" * 60)
print(f"  Study period  : {CONFIG['start_date']} → {CONFIG['end_date']}")
print(f"  Target unit   : {CONFIG['target_unit']}")
print(f"  Temporal scale: {CONFIG['temporal_scale']}")
print(f"  Target res    : {CONFIG['target_resolution_deg']}° ({CONFIG['target_resolution_m']} m)")
print(f"  Rain threshold: {RAIN_THRESHOLD_MM_DAY} mm/day")
print(f"\n  {'Product':<16} {'Conv type':<16} {'Raw unit':<14} {'Out unit'}")
print(f"  {'─'*16} {'─'*16} {'─'*14} {'─'*8}")
for k, p in PRODUCTS.items():
    print(f"  {k:<16} {p['conversion']:<16} {p['units_raw']:<14} {p['units_out']}")
print()
print(f"  Effective study windows (clipped to product availability):")
for k in PRODUCTS:
    s, e = get_product_window(k)
    print(f"  {k:<16} {s}  →  {e}")
print()
print(f"  Continuous metrics : {METRICS['continuous']}")
print(f"  Categorical metrics: {METRICS['categorical']}")
print("═" * 60 + "\n")