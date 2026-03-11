"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 0: Environment Setup & Configuration
============================================================
Install dependencies (run once in terminal):
    conda install -c conda-forge -y geemap earthengine-api xarray pandas numpy scipy matplotlib seaborn cartopy netCDF4 geopandas rasterio

Then authenticate:
    earthengine authenticate
"""

import ee
import geemap
import os
import subprocess



# ── Authenticate & Initialize ──────────────────────────────
try:
    ee.Initialize(project='ee-desmond')   # <-- replace
    print(" Earth Engine initialized successfully")
except Exception:
    ee.Authenticate()
    ee.Initialize(project='ee-desmond')   # <-- replace

# ══════════════════════════════════════════════════════════
# GLOBAL CONFIGURATION  –  edit this block to customise
# ══════════════════════════════════════════════════════════
CONFIG = {

    # ── Study period ──────────────────────────────────────
    "start_date": "2000-01-01",
    "end_date":   "2021-01-01",

    # ── Region of interest ───────────────────────────────
    # Earth Engine asset containing the West Africa boundary
    "roi_asset": "projects/ee-desmond/assets/west_africa_boundary0",

    # ── Temporal aggregation ─────────────────────────────
    "temporal_scale": "monthly",               # "daily" | "monthly" | "annual"

    # ── Spatial resolution for comparison (degrees) ──────
    "target_resolution_deg": 0.25,

    # ── Output directories ───────────────────────────────
    "output_dir":  "outputs/precipitation_assessment",
    "figures_dir": "outputs/precipitation_assessment/figures",
    "data_dir":    "outputs/precipitation_assessment/data",
}

# ── Precipitation products catalogue ──────────────────────
PRODUCTS = {

    # ── Satellite-based ───────────────────────────────────
    "CHIRPS": {
        "collection": "UCSB-CHG/CHIRPS/DAILY",
        "band":       "precipitation",
        "scale_factor": 1.0,
        "units":      "mm/day",
        "type":       "satellite_gauge_merged",
        "temporal":   "daily",
        "native_res_deg": 0.05,
    },

    "PERSIANN_CDR": {
        "collection": "NOAA/PERSIANN-CDR",
        "band":       "precipitation",
        "scale_factor": 1.0,
        "units":      "mm/day",
        "type":       "satellite",
        "temporal":   "daily",
        "native_res_deg": 0.25,
    },

    # TRMM monthly product (already monthly)
    "TRMM_3B43": {
        "collection": "TRMM/3B43V7",
        "band":       "precipitation",
        "scale_factor": 24.0,      # mm/hr → mm/day (handled before monthly conversion)
        "units":      "mm/hr",
        "type":       "satellite_gauge_corrected",
        "temporal":   "monthly",
        "native_res_deg": 0.25,
    },

    # GPM IMERG monthly product
    "GPM_IMERG": {
        "collection": "NASA/GPM_L3/IMERG_MONTHLY_V07",
        "band":       "precipitation",
        "scale_factor": 24.0,      # mm/hr → mm/day
        "units":      "mm/hr",
        "type":       "satellite_gauge_merged",
        "temporal":   "monthly",
        "native_res_deg": 0.1,
    },

    # ── Reanalysis ────────────────────────────────────────
    "ERA5_LAND": {
        "collection": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "band":       "total_precipitation_sum",
        "scale_factor": 1000.0,    # meters → mm
        "units":      "mm/month",
        "type":       "reanalysis",
        "temporal":   "monthly",
        "native_res_deg": 0.1,
    },



    # MERRA-2 precipitation
    "MERRA2": {
        "collection": "NASA/GSFC/MERRA/flx/2",
        "band":       "PRECTOTCORR",
        "scale_factor": 86400.0,   # kg/m²/s → mm/day
        "units":      "mm/day",
        "type":       "reanalysis",
        "temporal":   "hourly",
        "native_res_deg": 0.5,
    },

    # ── Gauge-based reference ─────────────────────────────


}



# ── Validation metrics to compute ────────────────────────
METRICS = [
    "bias",           # mean bias
    "pbias",          # percent bias
    "mae",            # mean absolute error
    "rmse",           # root mean squared error
    "r",              # Pearson correlation
    "r2",             # coefficient of determination
    "nse",            # Nash-Sutcliffe efficiency
    "kge",            # Kling-Gupta efficiency
    "pod",            # probability of detection  (categorical)
    "far",            # false alarm ratio          (categorical)
    "csi",            # critical success index     (categorical)
    "ets",            # equitable threat score     (categorical)
]

# ── Rain/no-rain threshold (mm/day) ──────────────────────
RAIN_THRESHOLD = None  # set to None to skip categorical metrics

# ── Create output folders ─────────────────────────────────
for d in [CONFIG["output_dir"], CONFIG["figures_dir"], CONFIG["data_dir"]]:
    os.makedirs(d, exist_ok=True)

print(" Configuration loaded. Output dirs created.")
print(f"   Products configured : {list(PRODUCTS.keys())}")
print(f"   Metrics configured  : {METRICS}")
