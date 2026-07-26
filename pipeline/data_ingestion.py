"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 1: Data Ingestion & Pre-processing
============================================================

CURRENT STATUS SUMMARY (update after each completed task)
──────────────────────────────────────────────────────────

  Product         Drive Export    Asset Export
  ─────────────── ─────────────── ───────────────
  ERA5_LAND        DONE           DONE
  GPM_IMERG        DONE           DONE
  TERRACLIMATE     DONE           DONE
  PERSIANN_CDR     DONE           DONE  ← ingested from Drive to Asset
  CHIRPS           DONE           DONE  ← ingested from Drive to Asset
  MERRA2          ⏳ PENDING       ⏳ PENDING ← yearly assets done (2000–2021);
                                              merge step is NEXT ACTION

  NEXT ACTIONS (in order):
  1. Run merge_merra2_yearly_assets(years=list(range(2001,2021)))
     → submits Asset + Drive export of final MERRA2 climatology
  2. After MERRA2 merge completes → run gauge_extraction.py
     for CHIRPS and MERRA2 CSVs (see gauge_extraction.py § 5)

PIPELINE OVERVIEW
─────────────────
PHASE 1 : Define study area and parameters
PHASE 2 : Load and prepare reference imagery (Sentinel-2)
PHASE 3 : Load AlphaEarth Satellite Embeddings
PHASE 4 : Collect training samples (GCPs)
PHASE 5 : Train KNN classifier on embedding vectors
PHASE 6 : Classify full embedding image
PHASE 7 : Accuracy assessment
PHASE 8 : Multi-epoch loop (2017, 2019, 2021, 2024)
PHASE 9 : Change analysis and export

FIXES APPLIED vs original data_ingestion.py
────────────────────────────────────────────
1.  GPM_IMERG double-multiply removed (was ×576, now ×24)
2.  Per-product conversion dispatch (ERA5/Terra need per-image
    division by days-in-month — cannot use fixed scale_factor)
3.  Daily/hourly aggregation changed from .sum() → .mean()
4.  Band name standardised to "precip_mm_day" throughout
5.  year/month properties tagged on ALL products
6.  Empty-month guard returns masked image with correct band
7.  Product date windows clipped via get_product_window()
8.  TARGET_SCALE_M read from CONFIG["target_resolution_m"]
9.  COMPLETED_BOTH / COMPLETED_DRIVE_ONLY updated to reflect
    CHIRPS and PERSIANN_CDR Drive→Asset ingestion
10. MERRA2 merge instructions made the primary entry point
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
    Cannot use a fixed scale_factor — days_in_month varies (28/29/30/31).
    """
    d   = ee.Date(img.get("system:time_start"))
    dim = d.advance(1, "month").difference(d, "day")
    out = (img.multiply(1000)
              .divide(ee.Image.constant(dim))
              .rename("precip_mm_day")
              .toFloat())
    return out.updateMask(out.gte(0))


def _harmonise_terra_monthly(img: ee.Image) -> ee.Image:
    """
    TerraClimate 'pr' band: monthly precipitation in mm/month.
    mm/day = value_mm_month ÷ days_in_month
    """
    d   = ee.Date(img.get("system:time_start"))
    dim = d.advance(1, "month").difference(d, "day")
    out = (img.divide(ee.Image.constant(dim))
              .rename("precip_mm_day")
              .toFloat())
    return out.updateMask(out.gte(0))


def _harmonise(img: ee.Image, name: str) -> ee.Image:
    """Select and apply the correct unit conversion for a product."""
    p    = PRODUCTS[name]
    conv = p["conversion"]
    if conv == "era5_monthly":
        return _harmonise_era5_monthly(img)
    if conv == "terra_monthly":
        return _harmonise_terra_monthly(img)
    return _harmonise_scale(img, p["scale_factor"], name)


# ════════════════════════════════════════════════════════════
# § 4  CORE PIPELINE FUNCTIONS
# ════════════════════════════════════════════════════════════

def _load_merra2_daily(roi: ee.Geometry,
                       start: str, end: str) -> ee.ImageCollection:
    """
    MERRA-2 special loader — pre-aggregates 24 hourly images → 1 daily
    image BEFORE monthly aggregation to avoid memory/timeout errors.

    WHY: MERRA-2 is 1-HOURLY (~175,000 images over 20 years).
    Pre-aggregating to daily (~7,300 images) keeps the collection
    manageable and resolves "User memory limit exceeded" errors.

    NUMERICAL EQUIVALENCE:
    mean(24 hourly kg/m²/s) × 86400 = mean daily mm/day
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
             .select([p["band"]]))

    n_days  = ee.Date(req_end).difference(ee.Date(req_start), "day").round()
    offsets = ee.List.sequence(0, n_days.subtract(1))

    def make_daily(offset):
        offset   = ee.Number(offset).toInt()
        date     = ee.Date(req_start).advance(offset, "day")
        date_end = date.advance(1, "day")

        daily = (raw.filterDate(date, date_end)
                    .mean()
                    .multiply(86400)
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
    """
    if name == "MERRA2":
        return _load_merra2_daily(roi, start, end)

    p = PRODUCTS[name]
    eff_start, eff_end = get_product_window(name)
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

    return raw.map(harmonise_and_clip)


def aggregate_to_monthly(ic: ee.ImageCollection,
                          product_name: str) -> ee.ImageCollection:
    """
    Aggregate to monthly mean mm/day and tag year/month properties.

    WHY .mean() NOT .sum():
    Target unit is mm/day (mean daily rate).
    .sum() gives mm/month which varies with month length.
    .mean() preserves mm/day regardless of month length.
    """
    p = PRODUCTS[product_name]

    if p["native_temporal"] == "monthly":
        def tag_monthly(img):
            img = ee.Image(img)
            d   = ee.Date(img.get("system:time_start"))
            return img.set(
                "year",  d.get("year"),
                "month", d.get("month"),
            )
        return ic.map(tag_monthly)

    n_months = (END_YEAR - START_YEAR + 1) * 12
    offsets  = ee.List.sequence(0, n_months - 1)

    def make_month_img(offset):
        offset = ee.Number(offset).toInt()
        s      = ee.Date.fromYMD(START_YEAR, 1, 1).advance(offset, "month")
        e      = s.advance(1, "month")
        yr     = s.get("year")
        mo     = s.get("month")

        slice_ic = ic.filterDate(s, e)

        empty_img = (ee.Image.constant(0)
                       .rename("precip_mm_day")
                       .toFloat()
                       .updateMask(ee.Image.constant(0))
                       .set("system:time_start", s.millis(),
                            "year", yr, "month", mo,
                            "product", product_name))

        month_img = ee.Image(
            ee.Algorithms.If(
                slice_ic.size().gt(0),
                (slice_ic
                    .mean()
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
    """Bilinear resample every image to the common 0.25° grid."""
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
# ════════════════════════════════════════════════════════════

STATIONS_META = [
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
    ("WA016", "Nouakchott",   -15.97,  18.07,    9,   "demo"),
]

STATIONS_DF = pd.DataFrame(
    STATIONS_META,
    columns=["station_id", "station_name", "lon", "lat",
             "elevation_m", "source"]
)

import numpy as np

def _generate_demo_obs(stations_df: pd.DataFrame,
                        start_yr: int, end_yr: int) -> pd.DataFrame:
    """Synthetic monthly obs for demonstration only. Replace with real data."""
    rng  = np.random.default_rng(seed=42)
    rows = []
    for _, s in stations_df.iterrows():
        for yr in range(start_yr, end_yr + 1):
            for mo in range(1, 13):
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


def load_stations_from_csv(stations_csv: str, obs_csv: str) -> tuple:
    """Load real station metadata and observations from CSV files."""
    stations_df = pd.read_csv(stations_csv)
    obs_df      = pd.read_csv(obs_csv)

    req_stn = {"station_id", "station_name", "lon", "lat", "elevation_m", "source"}
    req_obs = {"station_id", "year", "month", "obs_mm_day"}
    missing_stn = req_stn - set(stations_df.columns)
    missing_obs = req_obs - set(obs_df.columns)
    if missing_stn:
        raise ValueError(f"stations CSV missing columns: {missing_stn}")
    if missing_obs:
        raise ValueError(f"obs CSV missing columns: {missing_obs}")

    obs_df["year"]       = obs_df["year"].astype(int)
    obs_df["month"]      = obs_df["month"].astype(int)
    obs_df["obs_mm_day"] = obs_df["obs_mm_day"].astype(float)

    print(f" Real stations loaded : {len(stations_df)}")
    print(f" Real obs loaded      : {len(obs_df):,} rows")
    return stations_df, obs_df


def stations_to_ee_fc(stations_df: pd.DataFrame) -> ee.FeatureCollection:
    """Convert stations DataFrame to GEE FeatureCollection."""
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

COLLECTIONS = {}

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
        print(f"     Failed to build {pname}: {exc}")

print(f"\n Collections built: {list(COLLECTIONS.keys())}")


# ════════════════════════════════════════════════════════════
# § 7  EXPORT UTILITIES
# ════════════════════════════════════════════════════════════

def _build_climatology_image(product_name: str) -> ee.Image:
    """
    Shared helper — builds the 12-band climatology image server-side.
    Used by both toDrive and toAsset exports to avoid code duplication.
    Returns a float image with bands month_01 … month_12 (mm/day).
    """
    ic = COLLECTIONS[product_name]

    def month_clim(m):
        m = ee.Number(m).toInt()
        return (ic.filter(ee.Filter.calendarRange(m, m, "month"))
                  .select("precip_mm_day")
                  .mean()
                  .rename(ee.String("month_").cat(m.format())))

    raw_stack   = ee.ImageCollection(
                    ee.List.sequence(1, 12).map(month_clim)).toBands()
    valid_names = ee.List.sequence(1, 12).map(
        lambda m: ee.String("month_").cat(
            ee.Algorithms.If(
                ee.Number(m).lt(10),
                ee.String("0").cat(ee.Number(m).int().format()),
                ee.Number(m).int().format()
            )
        )
    )
    return (raw_stack
            .rename(valid_names)
            .toFloat()
            .reproject(crs="EPSG:4326", scale=TARGET_SCALE_M)
            .clip(ROI))


def export_climatology_to_drive(product_name: str,
                                 drive_folder: str = None) -> ee.batch.Task:
    """Export 12-band monthly climatology to Google Drive (mm/day)."""
    folder      = drive_folder or CONFIG["drive_folder"]
    clim_12band = _build_climatology_image(product_name)

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
    """Export 12-band monthly climatology to GEE Asset (mm/day)."""
    asset_id    = CONFIG["asset_folder"] + f"climatology_{product_name}"
    clim_12band = _build_climatology_image(product_name)

    task = ee.batch.Export.image.toAsset(
        image       = clim_12band,
        description = f"Asset_clim_{product_name}",
        assetId     = asset_id,
        region      = ROI,
        scale       = TARGET_SCALE_M,
        crs         = "EPSG:4326",
        maxPixels   = 1e13,
        pyramidingPolicy = {".default": "mean"},
    )
    task.start()
    print(f"  ↗  Export started (Asset): {asset_id}")
    return task


def load_climatology_asset(product_name: str) -> ee.Image:
    """
    Load a previously exported climatology asset (12-band image).
    Returns None with a warning if the asset has not been exported yet.
    """
    asset_id = CONFIG["asset_folder"] + f"climatology_{product_name}"
    try:
        img = ee.Image(asset_id)
        img.bandNames().getInfo()
        print(f"   Asset loaded: {asset_id}")
        return img
    except Exception:
        print(f"  ⚠  Asset not found: {asset_id}")
        print(f"     Run export_climatology_to_asset('{product_name}') first.")
        return None


def export_climatology_merra2_yearly(
        years: list = None,
        completed_years: list = None) -> dict:
    """
    Export MERRA-2 climatology one year at a time to avoid 12h timeout.

    STATUS: All 22 yearly assets (2000–2021) are DONE.
    This function is kept for reference / re-runs only.
    Call merge_merra2_yearly_assets() as the next step.

    Parameters
    ──────────
    years           : list of integer years (default: 2001–2020)
    completed_years : years already exported — skipped automatically
    """
    if years is None:
        years = list(range(START_YEAR, END_YEAR + 1))
    if completed_years is None:
        completed_years = []

    p     = PRODUCTS["MERRA2"]
    tasks = {}

    for yr in years:
        if yr in completed_years:
            print(f"  ✓  MERRA2 {yr} already exported — skipping")
            continue

        yr_start = f"{yr}-01-01"
        yr_end   = f"{yr + 1}-01-01"

        daily_ic   = _load_merra2_daily(ROI, yr_start, yr_end)
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
        clim_yr  = raw_stack.rename(valid_names).toFloat().clip(ROI)
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

    return tasks


def merge_merra2_yearly_assets(
        years: list = None,
        completed_years: list = None) -> dict:
    """
    ══════════════════════════════════════════════════════════
    NEXT ACTION — Run this now to complete MERRA-2 processing
    ══════════════════════════════════════════════════════════

    Merges the 20 yearly MERRA-2 climatology assets into one
    final 12-band climatology asset + Drive file (2001–2020).

    Each yearly asset has bands month_01…month_12 (mean mm/day
    for that calendar month in that single year). This function
    averages across all 20 years to get the long-term mean —
    identical in meaning to what a single-task export would have
    produced without the 12h timeout.

    HOW TO CALL:
        from data_ingestion import merge_merra2_yearly_assets
        merge_merra2_yearly_assets(years=list(range(2001, 2021)))

    WHAT IT PRODUCES:
        Asset : CONFIG["asset_folder"] + "climatology_MERRA2"
        Drive : Kogyae_PhD/climatology_MERRA2.tif
        Bands : month_01 … month_12  (float32, mm/day)

    AFTER IT COMPLETES:
        → Go to gauge_extraction.py and run extraction for
          CHIRPS and MERRA2 (both CSVs are still pending)

    Parameters
    ──────────
    years           : years to include (default: 2001–2020)
    completed_years : subset to use if not all finished
                      (allows partial merge for inspection)
    """
    if years is None:
        years = list(range(START_YEAR, END_YEAR + 1))
    if completed_years is not None:
        years = completed_years

    print(f"  Merging MERRA2 yearly assets: {years[0]}–{years[-1]}")
    print(f"  Loading {len(years)} yearly assets …")

    yearly_imgs = []
    for yr in years:
        asset_id = CONFIG["asset_folder"] + f"climatology_MERRA2_{yr}"
        yearly_imgs.append(ee.Image(asset_id))
        print(f"    • Queued: climatology_MERRA2_{yr}")

    yearly_ic  = ee.ImageCollection(yearly_imgs)
    band_names = [f"month_{str(m).zfill(2)}" for m in range(1, 13)]

    def mean_band(band_name):
        return (yearly_ic
                  .select([band_name])
                  .mean()
                  .rename(band_name))

    final_bands = ee.ImageCollection(
        [mean_band(b) for b in band_names]
    ).toBands()

    valid_names = ee.List(band_names)
    final_clim  = final_bands.rename(valid_names).toFloat().clip(ROI)

    # ── Asset export ──────────────────────────────────────────
    asset_id = CONFIG["asset_folder"] + "climatology_MERRA2"
    asset_task = ee.batch.Export.image.toAsset(
        image            = final_clim,
        description      = "Asset_clim_MERRA2_merged",
        assetId          = asset_id,
        region           = ROI,
        scale            = TARGET_SCALE_M,
        crs              = "EPSG:4326",
        maxPixels        = 1e13,
        pyramidingPolicy = {".default": "mean"},
    )
    asset_task.start()
    print(f"\n  ↗  MERRA2 merged Asset submitted  → {asset_id}")

    # ── Drive export ──────────────────────────────────────────
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
    print(f"  ↗  MERRA2 merged Drive submitted  → "
          f"{CONFIG['drive_folder']}/climatology_MERRA2.tif")

    print(f"""
  ══════════════════════════════════════════════════════
  MERRA2 MERGE TASKS SUBMITTED ({len(years)} years → 2 tasks)
  ══════════════════════════════════════════════════════
  Monitor : https://code.earthengine.google.com/tasks
  Asset   : {asset_id}
  Drive   : {CONFIG['drive_folder']}/climatology_MERRA2.tif

  AFTER BOTH COMPLETE → next step:
    Run gauge_extraction.py for CHIRPS + MERRA2 CSVs
    (see gauge_extraction.py § 5 CURRENT STATUS block)
  ══════════════════════════════════════════════════════
    """)

    return {"asset": asset_task, "drive": drive_task}


# ════════════════════════════════════════════════════════════
# § 8  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═" * 60)
    print("  DATA INGESTION — Current Status & Next Actions")
    print("═" * 60)

    # ════════════════════════════════════════════════════════
    # CLIMATOLOGY EXPORT STATUS
    # Update this block after each completed task.
    # ════════════════════════════════════════════════════════
    #
    #  Product         Drive     Asset     Notes
    #  ─────────────── ───────── ───────── ─────────────────────
    #  ERA5_LAND        DONE    DONE
    #  GPM_IMERG        DONE    DONE
    #  TERRACLIMATE     DONE    DONE
    #  PERSIANN_CDR     DONE    DONE   Drive→Asset ingestion
    #  CHIRPS           DONE    DONE   Drive→Asset ingestion
    #  MERRA2          ⏳ NEXT   ⏳ NEXT   Yearly assets done;
    #                                      merge step below

    # Products with BOTH Drive and Asset confirmed complete — skip entirely
    COMPLETED_BOTH = [
        "ERA5_LAND",
        "GPM_IMERG",
        "TERRACLIMATE",
        "PERSIANN_CDR",   # Drive   Asset  (ingested from Drive)
        "CHIRPS",         # Drive   Asset  (ingested from Drive)
    ]

    # MERRA2 handled separately via yearly merge pathway
    SKIP = ["MERRA2"]

    tasks = {}

    for pname in COLLECTIONS:

        if pname in SKIP:
            print(f"  ⊘  {pname} — yearly assets done (2000–2021); "
                  f"merge step is the next action")
            continue

        if pname in COMPLETED_BOTH:
            print(f"  ✓  {pname} — Drive + Asset both complete, skipping")
            continue

        # Any product not yet completed — submit both exports
        print(f"\n  Submitting: {pname}")
        t_drive = export_climatology_to_drive(pname)
        if t_drive:
            tasks[f"{pname}_drive"] = t_drive
        t_asset = export_climatology_to_asset(pname)
        if t_asset:
            tasks[f"{pname}_asset"] = t_asset

    # ════════════════════════════════════════════════════════
    # ▶▶▶  PRIMARY NEXT ACTION: MERRA-2 MERGE
    # ════════════════════════════════════════════════════════
    print("\n" + "─" * 60)
    print("  MERRA-2 MERGE — run the block below NOW")
    print("─" * 60)
    print("""
  All 22 yearly MERRA-2 assets (2000–2021) are complete.
  The study period uses 2001–2020 (20 years).

  TO MERGE — uncomment and run:
  ─────────────────────────────
      from data_ingestion import merge_merra2_yearly_assets
      merge_merra2_yearly_assets(years=list(range(2001, 2021)))

  This submits 2 tasks (Asset + Drive) that run in ~30–90 min.
  Monitor: https://code.earthengine.google.com/tasks

  AFTER MERRA-2 MERGE COMPLETES:
  ───────────────────────────────
  → Open gauge_extraction.py
  → Run extraction for CHIRPS and MERRA2 (both CSVs pending)
  → See gauge_extraction.py § 5 CURRENT STATUS block
    """)

    print(f"\n{'═'*60}")
    print(f"  {len(tasks)} new export task(s) submitted.")
    print(f"  Monitor: https://code.earthengine.google.com/tasks")
    print(f"{'═'*60}\n")