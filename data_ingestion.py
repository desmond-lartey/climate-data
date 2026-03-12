"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 1: Data Ingestion & Pre-processing
============================================================
Loads each product, harmonises ALL units → mm/day (mean daily
rate), tags year/month properties, resamples to common grid,
and exports monthly climatologies as GEE Assets + Drive files.

Run AFTER setup_config.py in the same Python session, or
import this module from a notebook / pipeline runner.

FIXES APPLIED vs original data_ingestion.py
────────────────────────────────────────────
1.  GPM_IMERG double-multiply removed (was ×576, now ×24)
2.  Per-product conversion dispatch (ERA5/Terra need per-image
    division by days-in-month — cannot use fixed scale_factor)
3.  Daily/hourly aggregation changed from .sum() → .mean()
    (.sum gives mm/month; .mean gives mm/day — our target unit)
4.  Band name standardised to "precip_mm_day" throughout
5.  year/month properties tagged on ALL products including
    those that are already monthly (TRMM, GPM, ERA5, Terra)
6.  Empty-month guard changed: returns masked image with the
    correct band "precip_mm_day" instead of a band-less Image(0)
7.  Product date windows clipped via get_product_window() so
    TRMM/GPM don't request dates outside availability
8.  TARGET_SCALE_M read from CONFIG["target_resolution_m"]
9.  Imports updated for new setup_config structure
10. Station / GPCC observation containers added — replace
    demo data with real CSVs when available (§ 5)
============================================================
"""

import ee
import os
import pandas as pd

from setup_config import (
    CONFIG,
    PRODUCTS,
    PRODUCT_DATE_RANGES,
    get_product_window,
    RAIN_THRESHOLD_MM_DAY,
)


# ════════════════════════════════════════════════════════════
# § 1  CONSTANTS
# ════════════════════════════════════════════════════════════

TARGET_SCALE_M = CONFIG["target_resolution_m"]   # 27 830 m ≈ 0.25°
START          = CONFIG["start_date"]
END            = CONFIG["end_date"]
START_YEAR     = int(START[:4])
END_YEAR       = int(END[:4])


# ════════════════════════════════════════════════════════════
# § 2  REGION OF INTEREST
# ════════════════════════════════════════════════════════════

def build_roi() -> ee.Geometry:
    """Load ROI from GEE asset and dissolve to single geometry."""
    fc  = ee.FeatureCollection(CONFIG["roi_asset"])
    roi = fc.geometry().dissolve(maxError=1)
    print(f" ROI loaded: {CONFIG['roi_asset']}")
    return roi

ROI = build_roi()


# ════════════════════════════════════════════════════════════
# § 3  HARMONISATION HELPERS
#
#  All functions return an ee.Image with:
#    • band name : "precip_mm_day"
#    • units     : mm/day  (mean daily rate)
#    • metadata  : system:time_start, year, month, product
# ════════════════════════════════════════════════════════════

def _tag_ym(img: ee.Image) -> ee.Image:
    """Tag year and month integer properties onto an image."""
    d = ee.Date(img.get("system:time_start"))
    return img.set("year", d.get("year")).set("month", d.get("month"))


def _harmonise_scale(img: ee.Image, scale_factor: float,
                     product_name: str) -> ee.Image:
    """
    Simple fixed-scalar conversion.
    mm/day = raw × scale_factor
    Used for: CHIRPS, PERSIANN (×1), TRMM, GPM (×24), MERRA-2 (×86400)
    """
    out = (img.multiply(scale_factor)
              .rename("precip_mm_day")
              .toFloat())
    return out.updateMask(out.gte(0))


def _harmonise_era5_monthly(img: ee.Image) -> ee.Image:
    """
    ERA5-Land MONTHLY_AGGR: total_precipitation_sum is in metres/month.
    mm/day = value_m × 1000 ÷ days_in_month

    CANNOT use a fixed scale_factor — days_in_month varies (28/29/30/31).
    This per-image function is called inside a .map() so ee.Date is lazy.
    """
    d   = ee.Date(img.get("system:time_start"))
    dim = d.advance(1, "month").difference(d, "day")   # days in this month
    out = (img.multiply(1000)
              .divide(ee.Image.constant(dim))
              .rename("precip_mm_day")
              .toFloat())
    return out.updateMask(out.gte(0))


def _harmonise_terra_monthly(img: ee.Image) -> ee.Image:
    """
    TerraClimate 'pr' band: monthly precipitation accumulation in mm/month.
    mm/day = value_mm_month ÷ days_in_month

    GEE catalogue lists scale=1, offset=0, so no additional scaling needed.
    """
    d   = ee.Date(img.get("system:time_start"))
    dim = d.advance(1, "month").difference(d, "day")
    out = (img.divide(ee.Image.constant(dim))
              .rename("precip_mm_day")
              .toFloat())
    return out.updateMask(out.gte(0))


# Dispatch: conversion field → harmonisation function
def _harmonise(img: ee.Image, name: str) -> ee.Image:
    """Select and apply the correct unit conversion for a product."""
    p    = PRODUCTS[name]
    conv = p["conversion"]
    if conv == "era5_monthly":
        return _harmonise_era5_monthly(img)
    if conv == "terra_monthly":
        return _harmonise_terra_monthly(img)
    # "none" (×1) or "scale" (×factor)
    return _harmonise_scale(img, p["scale_factor"], name)


# ════════════════════════════════════════════════════════════
# § 4  CORE PIPELINE FUNCTIONS
# ════════════════════════════════════════════════════════════

def load_product(name: str, roi: ee.Geometry,
                 start: str, end: str) -> ee.ImageCollection:
    """
    Load raw collection, clip to ROI, convert to mm/day.

    Returns ee.ImageCollection with band "precip_mm_day".
    year/month properties are NOT set here for daily/hourly
    products — they are set after monthly aggregation.
    For already-monthly products they are set here.
    """
    p = PRODUCTS[name]

    # Clip date range to product availability
    eff_start, eff_end = get_product_window(name)
    # Further clip to requested window
    req_start = max(start, eff_start)
    req_end   = min(end,   eff_end)

    if req_start >= req_end:
        print(f"  ⚠  {name}: no overlap between requested "
              f"[{start}, {end}] and available [{eff_start}, {eff_end}]")
        return ee.ImageCollection([])

    raw = (ee.ImageCollection(p["collection"])
             .filterDate(req_start, req_end)
             .filterBounds(roi)
             .select([p["band"]]))

    def harmonise_and_clip(img):
        img = ee.Image(img).clip(roi)
        out = _harmonise(img, name)
        return (out
                .copyProperties(img,
                    ["system:time_start", "system:time_end"])
                .set("product", name)
                .set("source_type", p["type"]))

    harmonised = raw.map(harmonise_and_clip)
    return harmonised


def aggregate_to_monthly(ic: ee.ImageCollection,
                          product_name: str) -> ee.ImageCollection:
    """
    Aggregate an ImageCollection to monthly mean mm/day and tag
    year/month properties on every output image.

    Rules
    ─────
    daily  → monthly mean of daily mm/day values (.mean())
    hourly → monthly mean of hourly mm/day values (.mean())
    monthly→ already one image per month; just tag year/month

    WHY .mean() NOT .sum()
    ──────────────────────
    Our target unit is mm/day (mean daily rate).
    .sum() would give mm/month (total accumulation) which varies
    with month length — making cross-product comparison wrong.
    .mean() preserves the mm/day unit regardless of month length.
    """
    p = PRODUCTS[product_name]

    if p["native_temporal"] == "monthly":
        # Already monthly — just tag year/month and return
        def tag_monthly(img):
            img = ee.Image(img)
            d   = ee.Date(img.get("system:time_start"))
            return img.set(
                "year",  d.get("year"),
                "month", d.get("month"),
            )
        return ic.map(tag_monthly)

    # Daily or hourly — aggregate to monthly mean
    # Build a list of (year, month) pairs covering the study period
    years  = ee.List.sequence(START_YEAR, END_YEAR)
    months = ee.List.sequence(1, 12)

    # Build a flat sequence of month offsets 0, 1, 2 … (n_years×12 − 1).
    # Using a single offset avoids the Cartesian-product + flatten approach
    # which causes GEE to pass each element as a Float (not a List), making
    # ee.List(ym).get(0) fail with "Expected List<Object>, got Float".
    n_months = (END_YEAR - START_YEAR + 1) * 12
    offsets  = ee.List.sequence(0, n_months - 1)

    def make_month_img(offset):
        offset = ee.Number(offset).toInt()
        s      = ee.Date.fromYMD(START_YEAR, 1, 1).advance(offset, "month")
        e      = s.advance(1, "month")
        yr     = s.get("year")
        mo     = s.get("month")

        slice_ic = ic.filterDate(s, e)

        # Guard: if no images exist for this month, return a fully
        # masked image with the correct band — NOT a band-less Image(0).
        # A band-less image is what caused "Image has no bands" errors.
        empty_img = (ee.Image.constant(0)
                       .rename("precip_mm_day")
                       .toFloat()
                       .updateMask(ee.Image.constant(0))   # fully masked
                       .set("system:time_start", s.millis(),
                            "year", yr, "month", mo,
                            "product", product_name))

        month_img = ee.Image(
            ee.Algorithms.If(
                slice_ic.size().gt(0),
                (slice_ic
                    .mean()                         # ← .mean() NOT .sum()
                    .rename("precip_mm_day")
                    .toFloat()
                    .set("system:time_start", s.millis(),
                         "year", yr, "month", mo,
                         "product", product_name)),
                empty_img,
            )
        )
        return month_img

    return ee.ImageCollection(offsets.map(make_month_img))


def resample_to_common(ic: ee.ImageCollection) -> ee.ImageCollection:
    """
    Bilinear resample every image to the common 0.25° grid.
    Applied AFTER monthly aggregation to save computation.
    """
    def _resample(img):
        return (ee.Image(img)
                  .resample("bilinear")
                  .reproject(crs="EPSG:4326", scale=TARGET_SCALE_M)
                  .copyProperties(img,
                      ["system:time_start", "year", "month",
                       "product", "source_type"]))
    return ic.map(_resample)


# ════════════════════════════════════════════════════════════
# § 5  STATION / GAUGE OBSERVATION CONTAINERS
#
#  Replace the demo data below with real station records
#  when GPCC or gauge CSV files become available.
#
#  Two loading paths are provided:
#  A) Inline Python list  → always works, no file needed
#  B) CSV file loader     → call load_stations_from_csv()
#                           with your real files
#
#  Required fields (must match for real data too)
#  ───────────────────────────────────────────────
#  STATION metadata CSV columns:
#    station_id, station_name, lon, lat, elevation_m, source
#
#  OBSERVATIONS CSV columns:
#    station_id, year, month, obs_mm_day
#  (obs_mm_day = monthly mean daily rate in mm/day)
# ════════════════════════════════════════════════════════════

# ── Demo station metadata (15 West African cities) ──────────
# Replace with real GPCC / SYNOP / GSOD station list
STATIONS_META = [
    # id,      name,           lon,     lat,    elev_m, source
    ("WA001", "Dakar",        -17.47,  14.73,   27,   "demo"),
    ("WA002", "Bamako",        -7.95,  12.65,  381,   "demo"),
    ("WA003", "Ouagadougou",   -1.52,  12.36,  306,   "demo"),
    ("WA004", "Niamey",         2.17,  13.51,  222,   "demo"),
    ("WA005", "Abuja",          7.33,   9.07,  476,   "demo"),
    ("WA006", "Accra",         -0.17,   5.56,   61,   "demo"),
    ("WA007", "Abidjan",       -3.93,   5.35,    7,   "demo"),
    ("WA008", "Conakry",      -13.67,   9.53,   27,   "demo"),
    ("WA009", "Freetown",     -13.23,   8.49,   27,   "demo"),
    ("WA010", "Monrovia",     -10.80,   6.30,   23,   "demo"),
    ("WA011", "Lomé",           1.22,   6.13,   25,   "demo"),
    ("WA012", "Cotonou",        2.42,   6.37,    9,   "demo"),
    ("WA013", "Kano",           8.52,  12.05,  481,   "demo"),
    ("WA014", "Kumasi",        -1.62,   6.69,  287,   "demo"),
    ("WA015", "Banjul",       -16.68,  13.45,   28,   "demo"),
]

# Convert to pandas DataFrame (same structure as real CSV)
STATIONS_DF = pd.DataFrame(
    STATIONS_META,
    columns=["station_id", "station_name", "lon", "lat",
             "elevation_m", "source"]
)

# ── Demo observations (synthetic, Sahel seasonal pattern) ───
# Replace obs_mm_day column values with real gauge readings.
# Structure must remain: station_id, year, month, obs_mm_day
import numpy as np

def _generate_demo_obs(stations_df: pd.DataFrame,
                        start_yr: int, end_yr: int) -> pd.DataFrame:
    """
    Generate synthetic monthly obs for demonstration.
    Uses a simple cosine seasonal cycle — NOT real data.
    Replace this entirely with real CSV data when available.
    """
    rng  = np.random.default_rng(seed=42)
    rows = []
    for _, s in stations_df.iterrows():
        for yr in range(start_yr, end_yr + 1):
            for mo in range(1, 13):
                # Sahel: peak Aug; Guinea: peak Jun
                phase = (mo - 8) if s.lat > 10 else (mo - 6)
                amp   = 4.0     if s.lat > 10 else 7.0
                obs   = max(0.0,
                    0.5 + amp * max(0.0, np.cos(phase * np.pi / 3))
                        + rng.normal(0, 1.25))
                rows.append({
                    "station_id" : s.station_id,
                    "year"       : yr,
                    "month"      : mo,
                    "obs_mm_day" : round(float(obs), 2),
                })
    return pd.DataFrame(rows)

OBS_DF = _generate_demo_obs(STATIONS_DF, START_YEAR, END_YEAR)

print(f" Stations loaded  : {len(STATIONS_DF)} "
      f"({'demo' if STATIONS_DF.source.eq('demo').all() else 'real'})")
print(f"📋 Observations     : {len(OBS_DF):,} rows  "
      f"({START_YEAR}–{END_YEAR})")


def load_stations_from_csv(stations_csv: str,
                            obs_csv: str) -> tuple:
    """
    Load real station metadata and observations from CSV files.

    Parameters
    ──────────
    stations_csv : path to CSV with columns:
        station_id, station_name, lon, lat, elevation_m, source
    obs_csv      : path to CSV with columns:
        station_id, year, month, obs_mm_day

    Returns
    ───────
    (stations_df, obs_df) — same structure as STATIONS_DF / OBS_DF
    so all downstream code works without modification.

    Usage (when real data is ready)
    ────────────────────────────────
        from data_ingestion import load_stations_from_csv
        STATIONS_DF, OBS_DF = load_stations_from_csv(
            "data/gpcc_stations_wa.csv",
            "data/gpcc_obs_wa_2001_2020.csv"
        )
    """
    stations_df = pd.read_csv(stations_csv)
    obs_df      = pd.read_csv(obs_csv)

    # Validate required columns
    req_stn = {"station_id", "station_name", "lon", "lat",
               "elevation_m", "source"}
    req_obs = {"station_id", "year", "month", "obs_mm_day"}
    missing_stn = req_stn - set(stations_df.columns)
    missing_obs = req_obs - set(obs_df.columns)
    if missing_stn:
        raise ValueError(f"stations CSV missing columns: {missing_stn}")
    if missing_obs:
        raise ValueError(f"obs CSV missing columns: {missing_obs}")

    # Enforce types
    obs_df["year"]       = obs_df["year"].astype(int)
    obs_df["month"]      = obs_df["month"].astype(int)
    obs_df["obs_mm_day"] = obs_df["obs_mm_day"].astype(float)

    print(f" Real stations loaded : {len(stations_df)}")
    print(f" Real obs loaded      : {len(obs_df):,} rows")
    return stations_df, obs_df


def stations_to_ee_fc(stations_df: pd.DataFrame) -> ee.FeatureCollection:
    """
    Convert the stations DataFrame to a GEE FeatureCollection.
    Used by validation steps that need to sample gridded products
    at point locations.
    """
    features = []
    for _, row in stations_df.iterrows():
        feat = ee.Feature(
            ee.Geometry.Point([row.lon, row.lat]),
            {
                "station_id"  : row.station_id,
                "station_name": row.station_name,
                "lon"         : row.lon,
                "lat"         : row.lat,
                "elevation_m" : row.elevation_m,
                "source"      : row.source,
            }
        )
        features.append(feat)
    return ee.FeatureCollection(features)

STATION_FC = stations_to_ee_fc(STATIONS_DF)


# ════════════════════════════════════════════════════════════
# § 6  BUILD ALL PRODUCT COLLECTIONS
# ════════════════════════════════════════════════════════════

print("\n⟳  Loading and harmonising products …")
print(f"   Period  : {START} → {END}")
print(f"   Unit    : mm/day (mean daily rate)")
print(f"   Grid    : {CONFIG['target_resolution_deg']}° "
      f"({TARGET_SCALE_M} m)\n")

COLLECTIONS = {}   # {product_name: ee.ImageCollection of monthly mm/day}

for pname in PRODUCTS:
    eff_start, eff_end = get_product_window(pname)
    print(f"  • {pname:<16}  [{eff_start} → {eff_end}]  "
          f"conv={PRODUCTS[pname]['conversion']}")
    try:
        raw_ic      = load_product(pname, ROI, START, END)
        monthly_ic  = aggregate_to_monthly(raw_ic, pname)
        resampled   = resample_to_common(monthly_ic)
        COLLECTIONS[pname] = resampled
    except Exception as exc:
        print(f"    ❌ Failed to build {pname}: {exc}")

print(f"\n Collections built: {list(COLLECTIONS.keys())}")


# ════════════════════════════════════════════════════════════
# § 7  EXPORT UTILITIES
# ════════════════════════════════════════════════════════════

def export_climatology_to_drive(product_name: str,
                                 drive_folder: str = None) -> ee.batch.Task:
    """
    Compute long-term monthly climatology (12 mean images) and
    export as a 12-band GeoTIFF to Google Drive.

    The 12 bands are named month_1 … month_12 where each pixel
    value is the long-term mean mm/day for that calendar month.

    This function is the corrected replacement for the original
    export_climatology() which produced "Image has no bands"
    because:
      a) The "month" property was not set on monthly products
      b) aggregate_monthly() renamed bands to "precip_mm_month"
      c) Empty months returned band-less Image(0)
    All three are fixed in the current pipeline.
    """
    # ── Build climatology ENTIRELY server-side — no .getInfo() calls ──────
    # Calling ic.size().getInfo() forces GEE to materialise the full
    # collection graph client-side just to count images. For large daily
    # collections (CHIRPS ~7,600 images, MERRA-2 ~180,000 hourly images)
    # this immediately hits "User memory limit exceeded" before the export
    # task is even submitted.  Build the 12-band image lazily using
    # calendarRange filters — GEE evaluates this on its export servers.
    folder = drive_folder or CONFIG["drive_folder"]
    ic     = COLLECTIONS[product_name]

    def month_clim(m):
        m   = ee.Number(m).toInt()
        img = (ic.filter(ee.Filter.calendarRange(m, m, "month"))
                 .select("precip_mm_day")
                 .mean()
                 .rename(ee.String("month_").cat(m.format())))
        return img

    clim_12band = (ee.ImageCollection(ee.List.sequence(1, 12).map(month_clim))
                     .toBands()
                     .toFloat()
                     .clip(ROI))

    task = ee.batch.Export.image.toDrive(
        image          = clim_12band,
        description    = f"Climatology_{product_name}",
        folder         = folder,
        fileNamePrefix = f"climatology_{product_name}",
        region         = ROI,
        scale          = TARGET_SCALE_M,
        crs            = "EPSG:4326",
        maxPixels      = 1e13,
    )
    task.start()
    print(f"  ↗  Export started (Drive): Climatology_{product_name}")
    return task


def export_climatology_to_asset(product_name: str) -> ee.batch.Task:
    """
    Export long-term climatology as a GEE Image Asset.
    Re-loading from an asset is instant — no recompute needed
    in subsequent pipeline steps.

    Asset path: CONFIG["asset_folder"] + "climatology_" + product_name
    """
    # Same approach: fully lazy, no .getInfo() to avoid memory limit.
    asset_id = CONFIG["asset_folder"] + f"climatology_{product_name}"
    ic       = COLLECTIONS[product_name]

    def month_clim(m):
        m   = ee.Number(m).toInt()
        img = (ic.filter(ee.Filter.calendarRange(m, m, "month"))
                 .select("precip_mm_day")
                 .mean()
                 .rename(ee.String("month_").cat(m.format())))
        return img

    clim_12band = (ee.ImageCollection(ee.List.sequence(1, 12).map(month_clim))
                     .toBands()
                     .toFloat()
                     .clip(ROI))

    task = ee.batch.Export.image.toAsset(
        image       = clim_12band,
        description = f"Asset_clim_{product_name}",
        assetId     = asset_id,
        region      = ROI,
        scale       = TARGET_SCALE_M,
        crs         = "EPSG:4326",
        maxPixels   = 1e13,
    )
    task.start()
    print(f"  ↗  Export started (Asset): {asset_id}")
    return task


def load_climatology_asset(product_name: str) -> ee.Image:
    """
    Load a previously exported climatology asset (12-band image).
    Returns None with a warning if the asset has not yet been exported.

    Usage pattern (recommended for downstream steps):
        clim = load_climatology_asset("CHIRPS")
        if clim is None:
            clim = compute_climatology_live("CHIRPS")  # fallback
    """
    asset_id = CONFIG["asset_folder"] + f"climatology_{product_name}"
    try:
        img = ee.Image(asset_id)
        # Trigger a lightweight server call to check existence
        img.bandNames().getInfo()
        print(f"   Asset loaded: {asset_id}")
        return img
    except Exception:
        print(f"  ⚠  Asset not found: {asset_id}")
        print(f"     Run export_climatology_to_asset('{product_name}') first.")
        return None


# ════════════════════════════════════════════════════════════
# § 8  ENTRY POINT — run exports
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═" * 60)
    print("  DATA INGESTION — Export Climatologies")
    print("═" * 60)

    # Products whose exports have already completed successfully.
    # Add product names here after verifying in the Tasks tab.
    COMPLETED = []

    # Products to skip entirely (e.g. not available in GEE)
    SKIP = []

    tasks = {}

    for pname in COLLECTIONS:

        if pname in SKIP:
            print(f"  ⊘  Skipping {pname} (in SKIP list)")
            continue

        if pname in COMPLETED:
            print(f"  ✓  {pname} already exported — skipping")
            continue

        print(f"\n  Submitting: {pname}")

        # Export to Drive (GeoTIFF for local analysis)
        t_drive = export_climatology_to_drive(pname)
        if t_drive:
            tasks[f"{pname}_drive"] = t_drive

        # Export to GEE Asset (for fast re-ingestion in steps 2–6)
        t_asset = export_climatology_to_asset(pname)
        if t_asset:
            tasks[f"{pname}_asset"] = t_asset

    print(f"\n{'═'*60}")
    print(f"  {len(tasks)} export task(s) submitted.")
    print(f"  Monitor: https://code.earthengine.google.com/tasks")
    print(f"{'═'*60}\n")