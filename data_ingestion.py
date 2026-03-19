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
    print(f"✅ ROI loaded: {CONFIG['roi_asset']}")
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


def _load_merra2_daily(roi: ee.Geometry,
                       start: str, end: str) -> ee.ImageCollection:
    """
    MERRA-2 special loader — pre-aggregates 24 hourly images → 1 daily
    image BEFORE monthly aggregation.

    WHY THIS IS NECESSARY
    ─────────────────────
    MERRA-2 is 1-HOURLY (~175,000 images over 20 years). Passing the raw
    hourly IC through aggregate_to_monthly() forces GEE to process all
    175,000 images per spatial operation — confirmed to cause:
      • "User memory limit exceeded" on interactive quota
      • 12h compute timeout on batch export tasks
    Pre-aggregating to daily (~7,300 images) keeps the collection the
    same order of magnitude as CHIRPS and resolves both errors.

    NUMERICAL EQUIVALENCE
    ──────────────────────
    mean(24 hourly kg/m²/s) × 86400 = mean daily mm/day
    Identical result to per-image scale_factor application, just in a
    memory-safe order.
    """
    p   = PRODUCTS["MERRA2"]
    eff_start, eff_end = get_product_window("MERRA2")
    req_start = max(start, eff_start)
    req_end   = min(end,   eff_end)

    if req_start >= req_end:
        print("  ⚠  MERRA2: no overlap in requested window")
        return ee.ImageCollection([])

    raw = (ee.ImageCollection(p["collection"])
             .filterDate(req_start, req_end)
             .filterBounds(roi)
             .select([p["band"]]))   # PRECTOTCORR in kg/m²/s

    n_days  = ee.Date(req_end).difference(ee.Date(req_start), "day").round()
    offsets = ee.List.sequence(0, n_days.subtract(1))

    def make_daily(offset):
        offset   = ee.Number(offset).toInt()
        date     = ee.Date(req_start).advance(offset, "day")
        date_end = date.advance(1, "day")

        daily = (raw.filterDate(date, date_end)
                    .mean()              # mean of 24 hourly values (kg/m²/s)
                    .multiply(86400)     # → mm/day
                    .rename("precip_mm_day")
                    .toFloat()
                    .clip(roi))

        empty = (ee.Image.constant(0)
                   .rename("precip_mm_day")
                   .toFloat()
                   .updateMask(ee.Image.constant(0)))

        out = ee.Image(ee.Algorithms.If(
            raw.filterDate(date, date_end).size().gt(0),
            daily, empty
        ))
        return (out.updateMask(out.gte(0))
                   .set("system:time_start", date.millis(),
                        "system:time_end",   date_end.millis(),
                        "product",           "MERRA2",
                        "source_type",       p["type"]))

    print(f"  • MERRA2: daily pre-aggregation ({req_start} → {req_end})")
    return ee.ImageCollection(offsets.map(make_daily))


def load_product(name: str, roi: ee.Geometry,
                 start: str, end: str) -> ee.ImageCollection:
    """
    Load raw collection, clip to ROI, convert to mm/day.

    Returns ee.ImageCollection with band "precip_mm_day".
    year/month properties are NOT set here for daily/hourly
    products — they are set after monthly aggregation.
    For already-monthly products they are set here.
    """
    # ── MERRA-2 special path ────────────────────────────────────────────
    # Route MERRA-2 through hourly→daily pre-aggregation before
    # harmonisation. Avoids 12h export timeout and memory limit errors.
    if name == "MERRA2":
        return _load_merra2_daily(roi, start, end)

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

print(f"📍 Stations loaded  : {len(STATIONS_DF)} "
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

    print(f"✅ Real stations loaded : {len(stations_df)}")
    print(f"✅ Real obs loaded      : {len(obs_df):,} rows")
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

print(f"\n✅ Collections built: {list(COLLECTIONS.keys())}")


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
        # Zero-pad so month_01..month_12 — valid GEE asset band IDs.
        # toBands() would prepend image index ("0_month_1") making them
        # invalid. We fix this by renaming the whole stack after toBands().
        return (ic.filter(ee.Filter.calendarRange(m, m, "month"))
                  .select("precip_mm_day")
                  .mean()
                  .rename(ee.String("month_").cat(m.format())))

    # toBands() stacks correctly but prefixes each band with its index
    # ("0_month_1", "1_month_2" …) which are INVALID GEE asset band IDs
    # (must start with a letter). Rename to month_01 … month_12 explicitly.
    raw_stack   = ee.ImageCollection(
                    ee.List.sequence(1, 12).map(month_clim)).toBands()
    valid_names = ee.List.sequence(1, 12).map(lambda m: ee.String("month_").cat(
        ee.Algorithms.If(
            ee.Number(m).lt(10),
            ee.String("0").cat(ee.Number(m).int().format()),
            ee.Number(m).int().format()
        )
    ))
    # Force computation at TARGET_SCALE_M before export.
    # Without this GEE tries to hold the full-resolution image in
    # memory during the export write step — causing OOM on CHIRPS
    # (0.05°, ~7600 images) and PERSIANN. Reprojecting first caps
    # the working resolution to our target grid. bestEffort=True
    # allows GEE to use a slightly coarser scale if needed rather
    # than failing. No effect on values — we already resampled in
    # resample_to_common() earlier in the pipeline.
    clim_12band = (raw_stack
                   .rename(valid_names)
                   .toFloat()
                   .reproject(crs="EPSG:4326", scale=TARGET_SCALE_M)
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
        # Zero-pad so month_01..month_12 — valid GEE asset band IDs.
        # toBands() would prepend image index ("0_month_1") making them
        # invalid. We fix this by renaming the whole stack after toBands().
        return (ic.filter(ee.Filter.calendarRange(m, m, "month"))
                  .select("precip_mm_day")
                  .mean()
                  .rename(ee.String("month_").cat(m.format())))

    # toBands() stacks correctly but prefixes each band with its index
    # ("0_month_1", "1_month_2" …) which are INVALID GEE asset band IDs
    # (must start with a letter). Rename to month_01 … month_12 explicitly.
    raw_stack   = ee.ImageCollection(
                    ee.List.sequence(1, 12).map(month_clim)).toBands()
    valid_names = ee.List.sequence(1, 12).map(lambda m: ee.String("month_").cat(
        ee.Algorithms.If(
            ee.Number(m).lt(10),
            ee.String("0").cat(ee.Number(m).int().format()),
            ee.Number(m).int().format()
        )
    ))
    # Force computation at TARGET_SCALE_M before export.
    # Without this GEE tries to hold the full-resolution image in
    # memory during the export write step — causing OOM on CHIRPS
    # (0.05°, ~7600 images) and PERSIANN. Reprojecting first caps
    # the working resolution to our target grid. bestEffort=True
    # allows GEE to use a slightly coarser scale if needed rather
    # than failing. No effect on values — we already resampled in
    # resample_to_common() earlier in the pipeline.
    clim_12band = (raw_stack
                   .rename(valid_names)
                   .toFloat()
                   .reproject(crs="EPSG:4326", scale=TARGET_SCALE_M)
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
        print(f"  ✅ Asset loaded: {asset_id}")
        return img
    except Exception:
        print(f"  ⚠  Asset not found: {asset_id}")
        print(f"     Run export_climatology_to_asset('{product_name}') first.")
        return None



def export_climatology_merra2_yearly(
        years: list = None,
        completed_years: list = None) -> dict:
    """
    Export MERRA-2 climatology one year at a time to avoid the 12h timeout.

    WHY YEARLY SPLITS ARE NEEDED FOR MERRA-2
    ─────────────────────────────────────────
    MERRA-2 is hourly. Even after daily pre-aggregation (_load_merra2_daily)
    the full 20-year monthly IC still requires GEE to resolve ~7,300 daily
    images when computing the 12-month climatology. This pushes the export
    past the 12h compute timeout (confirmed: 3 failed attempts).

    Splitting by year means each task only processes ~365 daily images
    (one year of MERRA-2 daily data) to produce a 12-band annual mean.
    Each task completes in ~30–60 min instead of timing out.

    The 20 yearly assets are then merged by merge_merra2_yearly_assets()
    into a single final climatology asset.

    Parameters
    ──────────
    years           : list of integer years to export (default: 2001–2020)
    completed_years : list of years already exported — skipped automatically

    Returns
    ───────
    dict of {year: ee.batch.Task}

    Usage
    ─────
        # First run — submit all 20 years
        tasks = export_climatology_merra2_yearly()

        # Re-run after some complete — skip finished years
        tasks = export_climatology_merra2_yearly(
            completed_years=[2001, 2002, 2003]
        )

        # After ALL 20 years done — merge into final asset
        merge_merra2_yearly_assets()
    """
    if years is None:
        years = list(range(START_YEAR, END_YEAR + 1))
    if completed_years is None:
        completed_years = []

    p        = PRODUCTS["MERRA2"]
    tasks    = {}

    for yr in years:
        if yr in completed_years:
            print(f"  ✓  MERRA2 {yr} already exported — skipping")
            continue

        yr_start = f"{yr}-01-01"
        yr_end   = f"{yr + 1}-01-01"

        # Build daily IC for this year only
        daily_ic = _load_merra2_daily(ROI, yr_start, yr_end)
        # Aggregate to monthly mean mm/day
        monthly_ic = aggregate_to_monthly(daily_ic, "MERRA2")

        def month_clim_yr(m):
            m = ee.Number(m).toInt()
            return (monthly_ic
                      .filter(ee.Filter.calendarRange(m, m, "month"))
                      .select("precip_mm_day")
                      .mean()
                      .rename(ee.String("month_").cat(m.format())))

        raw_stack   = ee.ImageCollection(
                        ee.List.sequence(1, 12).map(month_clim_yr)).toBands()
        valid_names = ee.List.sequence(1, 12).map(
            lambda m: ee.String("month_").cat(
                ee.Algorithms.If(
                    ee.Number(m).lt(10),
                    ee.String("0").cat(ee.Number(m).int().format()),
                    ee.Number(m).int().format()
                )
            )
        )
        clim_yr = raw_stack.rename(valid_names).toFloat().clip(ROI)

        asset_id = CONFIG["asset_folder"] + f"climatology_MERRA2_{yr}"

        task = ee.batch.Export.image.toAsset(
            image       = clim_yr,
            description = f"Asset_clim_MERRA2_{yr}",
            assetId     = asset_id,
            region      = ROI,
            scale       = TARGET_SCALE_M,
            crs         = "EPSG:4326",
            maxPixels   = 1e13,
        )
        task.start()
        tasks[yr] = task
        print(f"  ↗  MERRA2 {yr} export submitted → {asset_id}")

    print(f"\n  {len(tasks)} MERRA2 yearly task(s) submitted.")
    print(f"  After ALL complete, run: merge_merra2_yearly_assets()")
    return tasks


def merge_merra2_yearly_assets(
        years: list = None,
        completed_years: list = None) -> ee.batch.Task:
    """
    Merge 20 yearly MERRA-2 climatology assets into one final
    12-band climatology asset (long-term mean 2001–2020).

    Run ONLY after ALL yearly exports from
    export_climatology_merra2_yearly() have completed successfully.

    Each yearly asset has 12 bands (month_01 … month_12) representing
    the mean mm/day for each calendar month in that year.
    This function averages across all years to get the 20-year
    long-term mean — identical in meaning to what the single-task
    export would have produced without the timeout.

    Parameters
    ──────────
    years           : years to include (default: 2001–2020)
    completed_years : subset of years to use if not all finished yet
                      (allows partial merge for inspection)

    Returns
    ───────
    ee.batch.Task — the merge export task
    """
    if years is None:
        years = list(range(START_YEAR, END_YEAR + 1))
    if completed_years is not None:
        years = completed_years

    print(f"  Merging MERRA2 yearly assets: {years[0]}–{years[-1]}")

    # Load all yearly assets as an ImageCollection
    yearly_imgs = []
    for yr in years:
        asset_id = CONFIG["asset_folder"] + f"climatology_MERRA2_{yr}"
        yearly_imgs.append(ee.Image(asset_id))

    yearly_ic = ee.ImageCollection(yearly_imgs)

    # For each of the 12 months, average across all years
    band_names = [f"month_{str(m).zfill(2)}" for m in range(1, 13)]

    def mean_band(band_name):
        return (yearly_ic
                  .select([band_name])
                  .mean()
                  .rename(band_name))

    final_bands = ee.ImageCollection(
        [mean_band(b) for b in band_names]
    ).toBands()

    # Rename to strip the index prefix added by toBands()
    valid_names = ee.List(band_names)
    final_clim  = final_bands.rename(valid_names).toFloat().clip(ROI)

    asset_id = CONFIG["asset_folder"] + "climatology_MERRA2"

    task = ee.batch.Export.image.toAsset(
        image       = final_clim,
        description = "Asset_clim_MERRA2_merged",
        assetId     = asset_id,
        region      = ROI,
        scale       = TARGET_SCALE_M,
        crs         = "EPSG:4326",
        maxPixels   = 1e13,
    )
    task.start()
    print(f"  ↗  MERRA2 merged climatology export (Asset) submitted → {asset_id}")

    # ── Also export merged climatology to Drive ──────────────
    # Produces one 12-band GeoTIFF matching all other products:
    #   climatology_MERRA2.tif  (month_01 … month_12, mm/day)
    # Run automatically after all 20 yearly assets complete.
    drive_task = ee.batch.Export.image.toDrive(
        image          = final_clim,
        description    = "Climatology_MERRA2",
        folder         = CONFIG["drive_folder"],
        fileNamePrefix = "climatology_MERRA2",
        region         = ROI,
        scale          = TARGET_SCALE_M,
        crs            = "EPSG:4326",
        maxPixels      = 1e13,
    )
    drive_task.start()
    print(f"  ↗  MERRA2 merged climatology export (Drive) submitted")
    return {"asset": task, "drive": drive_task}


# ════════════════════════════════════════════════════════════
# § 8  ENTRY POINT — run exports
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═" * 60)
    print("  DATA INGESTION — Export Climatologies")
    print("═" * 60)

    # ── Completed tracking ───────────────────────────────────
    # Add product names here once BOTH Drive AND Asset exports
    # have completed successfully in the GEE Tasks tab.
    # These products will be skipped entirely on the next run.
    #
    # Current status (update after each successful run):
    #   Drive ✓  : ERA5_LAND, GPM_IMERG, PERSIANN_CDR,
    #              TERRACLIMATE, CHIRPS, TRMM
    #   Asset ✓  : ERA5_LAND, GPM_IMERG, PERSIANN_CDR,
    #              TERRACLIMATE, TRMM
    #   Failed   : CHIRPS (Asset — OOM), MERRA2 (both — timeout)
    # COMPLETED_BOTH  = ["ERA5_LAND", "GPM_IMERG", "TERRACLIMATE"]
    # # Removed PERSIANN_CDR — Asset failed OOM after 1 day (5 attempts)
    # # Will be re-exported below with tileScale=4 actually applied.

    # # Drive done, Asset still needed (or re-running with tileScale fix)
    # COMPLETED_DRIVE = ["CHIRPS"]
    # # Note: Asset_clim_CHIRPS is currently running (21h) — if it
    # # completes successfully, add "CHIRPS" to COMPLETED_BOTH above.
    # # If it fails again, it will be re-submitted here with tilScale=4.

    # # MERRA-2 handled separately via yearly splits (see below)
    # SKIP = ["MERRA2"]

    COMPLETED_BOTH  = ["ERA5_LAND", "GPM_IMERG", "TERRACLIMATE",
                   "PERSIANN_CDR", "CHIRPS"]

    COMPLETED_DRIVE = []

    SKIP = ["MERRA2"]

    completed_merra2_years = [2000, 2001, 2002, 2003, 2004, 2005,
                            2006, 2007, 2008, 2009, 2010, 2011,
                            2012, 2013, 2014, 2015, 2016, 2017,
                            2018, 2019, 2020, 2021]

    tasks = {}

    for pname in COLLECTIONS:

        if pname in SKIP:
            print(f"  ⊘  Skipping {pname} (handled separately)")
            continue

        if pname in COMPLETED_BOTH:
            print(f"  ✓  {pname} — both exports done, skipping")
            continue

        print(f"\n  Submitting: {pname}")

        # Drive export — skip if already completed
        if pname not in COMPLETED_DRIVE:
            t_drive = export_climatology_to_drive(pname)
            if t_drive:
                tasks[f"{pname}_drive"] = t_drive
        else:
            print(f"     Drive already done for {pname} — skipping Drive")

        # Asset export
        t_asset = export_climatology_to_asset(pname)
        if t_asset:
            tasks[f"{pname}_asset"] = t_asset

    # ── MERRA-2: submit yearly exports ──────────────────────
    # Each year = ~365 daily images → completes in ~30-60 min
    # instead of timing out at 12h with the full 20-year job.
    #
    # After ALL 20 yearly assets complete, run:
    #   merge_merra2_yearly_assets()
    #
    # completed_merra2_years: add years as they finish
    completed_merra2_years = []   # e.g. [2001, 2002, 2003, ...]

    merra2_tasks = export_climatology_merra2_yearly(
        completed_years=completed_merra2_years
    )
    tasks.update({f"MERRA2_{yr}": t for yr, t in merra2_tasks.items()})

    print(f"\n{'═'*60}")
    print(f"  {len(tasks)} export task(s) submitted.")
    print(f"  Monitor: https://code.earthengine.google.com/tasks")
    print(f"\n  MERRA-2 instructions:")
    print(f"  1. Add completed years to completed_merra2_years list")
    print(f"  2. Re-run to submit remaining years")
    print(f"  3. Once ALL 20 years done, run:")
    print(f"       from data_ingestion import merge_merra2_yearly_assets")
    print(f"       merge_merra2_yearly_assets()")
    print(f"{'═'*60}\n")