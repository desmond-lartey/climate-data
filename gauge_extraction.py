"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 2: Gauge Station Data Ingestion & Point Extraction
============================================================
Extracts gridded product values at gauge station locations
and merges them with observed precipitation for validation.

Observation sources supported
──────────────────────────────
A. Demo synthetic data       — always available (from data_ingestion.py)
B. User CSV files            — call load_stations_from_csv()
C. GPCC .nc files            — call load_gpcc_from_nc() once files
                               are downloaded from gpcc.dwd.de

Unit convention (must match data_ingestion.py throughout)
──────────────────────────────────────────────────────────
ALL precipitation values — both observations AND extracted
gridded product values — are in mm/day (mean daily rate).

Column name : obs_mm_day   ← observed gauge value
Column name : precip_mm_day ← extracted gridded value
Column name : <PRODUCT_NAME> after pivot (e.g. CHIRPS, GPM_IMERG)

FIXES vs original gauge_extraction.py
──────────────────────────────────────
1.  Imports corrected — ROI and TARGET_SCALE_M come from
    data_ingestion, not setup_config (they are not in setup_config)
2.  load_gauge_stations() removed — use STATIONS_DF / STATION_FC
    from data_ingestion.py directly (avoids duplication and the
    wrong demo station list covering non-West-Africa cities)
3.  Observations now use "obs_mm_day" not "precip_mm_month"
4.  extract_all_products() selects "precip_mm_day" band (not mm_month)
5.  Point sampling uses ee.Reducer.first() on point geometry
    (5 km buffer was sub-pixel at 0.25° and added geometry overhead)
6.  year/month read from image properties set by aggregate_to_monthly()
7.  Extracted features tagged "precip_mm_day" not "precip_mm_month"
8.  FC merging fixed — used ee.FeatureCollection(list_of_FCs).flatten()
    which is invalid; now uses sequential .merge() across products
9.  merge_obs_and_grid() aligned to "obs_mm_day" column name
10. GPCC .nc placeholder loader added (§ 2)
============================================================
"""

import ee
import pandas as pd
import numpy as np
import xarray as xr
import geopandas as gpd
from pathlib import Path

from setup_config import CONFIG, PRODUCTS
from data_ingestion import (
    ROI,
    TARGET_SCALE_M,
    COLLECTIONS,
    STATIONS_DF,
    OBS_DF,
    STATION_FC,
    load_stations_from_csv,
    stations_to_ee_fc,
)

DATA_DIR    = Path(CONFIG["data_dir"])
START_YEAR  = int(CONFIG["start_date"][:4])
END_YEAR    = int(CONFIG["end_date"][:4])


# ════════════════════════════════════════════════════════════
# § 1  STATION & OBSERVATION ACCESS
#
#  The primary sources (STATIONS_DF, OBS_DF, STATION_FC) are
#  defined and built in data_ingestion.py.  Import them above.
#
#  To swap in real data, call:
#      from data_ingestion import load_stations_from_csv
#      STATIONS_DF, OBS_DF = load_stations_from_csv(
#          "path/to/stations.csv",
#          "path/to/observations.csv"
#      )
#      STATION_FC = stations_to_ee_fc(STATIONS_DF)
#
#  Required CSV columns:
#    stations  : station_id, station_name, lon, lat, elevation_m, source
#    obs       : station_id, year, month, obs_mm_day
# ════════════════════════════════════════════════════════════

def get_stations_and_obs(stations_csv: str = None,
                          obs_csv:      str = None):
    """
    Return (stations_df, obs_df, station_fc).

    If CSV paths are supplied and exist, loads real data.
    Otherwise falls back to the demo data from data_ingestion.py.
    This is the single entry-point for all downstream steps so
    that swapping in real data requires changing only this call.
    """
    if stations_csv and obs_csv:
        s_df, o_df = load_stations_from_csv(stations_csv, obs_csv)
        fc         = stations_to_ee_fc(s_df)
        return s_df, o_df, fc

    # Demo fallback
    print("ℹ  Using demo station data from data_ingestion.py")
    print("   Replace with real data via load_stations_from_csv()")
    return STATIONS_DF, OBS_DF, STATION_FC


# ════════════════════════════════════════════════════════════
# § 2  GPCC .nc FILE LOADER  (placeholder — real data path)
#
#  Download from: https://opendata.dwd.de/climate_environment/
#                 GPCC/html/fulldata_v2022_doi_download.html
#
#  Files needed (monthly, 0.25°):
#    full_data_monthly_v2022_025_YYYY.nc  (one per year, or merged)
#
#  Variables:
#    precip   : mm/month accumulated total
#    numgauge : number of gauges used per cell
# ════════════════════════════════════════════════════════════

def load_gpcc_from_nc(nc_path: str,
                       stations_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract GPCC monthly precipitation at station locations from
    a downloaded GPCC NetCDF file and return in the standard
    obs_mm_day format used by the rest of the pipeline.

    Parameters
    ──────────
    nc_path     : path to GPCC .nc file (single file or merged)
    stations_df : DataFrame with columns station_id, lon, lat

    Returns
    ───────
    DataFrame with columns: station_id, year, month, obs_mm_day
    (obs_mm_day = GPCC mm/month ÷ days_in_month)

    Usage (once files are downloaded)
    ──────────────────────────────────
        obs_df = load_gpcc_from_nc(
            "data/gpcc_full_v2022_025.nc",
            STATIONS_DF
        )
        STATIONS_DF, obs_df, STATION_FC = get_stations_and_obs()
        # or directly:
        # obs_df replaces OBS_DF in all downstream calls
    """
    import calendar

    ds = xr.open_dataset(nc_path)

    # GPCC uses "precip" variable; some versions use "p"
    precip_var = "precip" if "precip" in ds else "p"

    records = []
    for _, stn in stations_df.iterrows():
        # Nearest-neighbour extraction at station coordinates
        pt = ds[precip_var].sel(
            lon=stn.lon, lat=stn.lat, method="nearest"
        )
        for t in pt.time.values:
            ts  = pd.Timestamp(t)
            yr  = ts.year
            mo  = ts.month
            dim = calendar.monthrange(yr, mo)[1]   # days in month
            # Convert mm/month → mm/day
            val = float(pt.sel(time=t).values) / dim
            records.append({
                "station_id" : stn.station_id,
                "year"       : yr,
                "month"      : mo,
                "obs_mm_day" : round(max(0.0, val), 3),
            })

    df = pd.DataFrame(records)
    print(f"✅ GPCC extracted: {len(df):,} records "
          f"for {len(stations_df)} stations")
    return df


# ════════════════════════════════════════════════════════════
# § 3  EXTRACT GRIDDED PRODUCT VALUES AT STATION LOCATIONS
# ════════════════════════════════════════════════════════════

def extract_product(station_fc:   ee.FeatureCollection,
                     product_name:  str,
                     drive_folder:  str = None) -> ee.batch.Task:
    """
    Sample ONE product's monthly ImageCollection at every station
    point and export as a single CSV to Google Drive.

    WHY ONE TASK PER PRODUCT
    ────────────────────────
    The previous single-task approach merged all 7 products into
    one FeatureCollection before export:
      7 products × 240 months × 15 stations = 25,200 features
    This consumed 58,677 EECU-seconds and timed out at 12h.

    Splitting by product means each task handles only:
      1 product × 240 months × 15 stations = 3,600 features
    Expected runtime: 30–90 min per product (7 tasks run in parallel).

    Output CSV: precip_extraction_<PRODUCT_NAME>.csv
    Columns   : station_id, product, year, month, precip_mm_day
    """
    folder = drive_folder or CONFIG["drive_folder"]
    ic     = COLLECTIONS[product_name]

    # Capture product_name in closure explicitly — avoids the common
    # Python loop-closure bug where all lambdas capture the final value
    pname = product_name

    def sample_image(img):
        yr  = img.get("year")
        mo  = img.get("month")
        samples = img.select("precip_mm_day").reduceRegions(
            collection = station_fc,
            reducer    = ee.Reducer.first(),
            scale      = TARGET_SCALE_M,
        )
        return samples.map(
            lambda f: f.set({
                "product"      : pname,
                "year"         : yr,
                "month"        : mo,
                "precip_mm_day": f.get("first"),
            }).select(
                ["station_id", "product", "year", "month", "precip_mm_day"]
            )
        )

    product_fc = ic.map(sample_image).flatten()

    task = ee.batch.Export.table.toDrive(
        collection  = product_fc,
        description = f"precip_extraction_{pname}",
        folder      = folder,
        fileFormat  = "CSV",
    )
    task.start()
    print(f"  ↗  Extraction started: precip_extraction_{pname}.csv")
    return task


def extract_all_products(station_fc:       ee.FeatureCollection,
                          products:         list = None,
                          drive_folder:     str  = None,
                          completed:        list = None) -> dict:
    """
    Submit one extraction task per product — runs in parallel on GEE.

    Parameters
    ──────────
    station_fc   : ee.FeatureCollection of station points
    products     : list of product keys (default: all in COLLECTIONS)
    drive_folder : Google Drive folder name (default from CONFIG)
    completed    : list of product names already extracted — skipped

    Returns
    ───────
    dict of {product_name: ee.batch.Task}

    Usage
    ─────
        # First run — submit all products
        tasks = extract_all_products(station_fc)

        # Re-run — skip products whose CSV already downloaded
        tasks = extract_all_products(
            station_fc,
            completed=["CHIRPS", "GPM_IMERG"]
        )
    """
    if products is None:
        products = list(COLLECTIONS.keys())
    if completed is None:
        completed = []

    tasks = {}
    for pname in products:
        if pname in completed:
            print(f"  ✓  {pname} extraction already done — skipping")
            continue
        tasks[pname] = extract_product(station_fc, pname, drive_folder)

    print(f"\n  {len(tasks)} extraction task(s) submitted.")
    print(f"  Each exports: precip_extraction_<PRODUCT>.csv")
    print(f"  Monitor: https://code.earthengine.google.com/tasks")
    return tasks


# ════════════════════════════════════════════════════════════
# § 4  MERGE OBSERVATIONS WITH EXTRACTED GRIDDED VALUES
# ════════════════════════════════════════════════════════════

def merge_obs_and_grid(obs_df:           pd.DataFrame,
                        extraction_csvs:  object) -> pd.DataFrame:
    """
    Join observed gauge precipitation (obs_df) with extracted
    gridded product values downloaded from Google Drive.

    Accepts EITHER:
      • A single CSV path (str/Path) — legacy single-file export
      • A list of CSV paths         — one per product (new default)
      • A directory path            — auto-discovers all
                                      precip_extraction_*.csv files

    All CSV files must contain:
        station_id, product, year, month, precip_mm_day

    Returns
    ───────
    Wide-format DataFrame:
      station_id | year | month | obs_mm_day | CHIRPS | GPM_IMERG | …
    All value columns are in mm/day.
    """
    # ── Resolve input to a list of file paths ────────────────
    if isinstance(extraction_csvs, (str, Path)):
        p = Path(extraction_csvs)
        if p.is_dir():
            csv_list = sorted(p.glob("precip_extraction_*.csv"))
            if not csv_list:
                csv_list = sorted(p.glob("precip_station_extraction*.csv"))
            print(f"  Found {len(csv_list)} extraction CSV(s) in {p}")
        else:
            csv_list = [p]
    else:
        csv_list = [Path(c) for c in extraction_csvs]

    if not csv_list:
        raise FileNotFoundError(
            "No extraction CSV files found. "
            "Download from Google Drive and place in DATA_DIR."
        )

    # ── Load and concatenate all product CSVs ────────────────
    dfs = []
    for csv_path in csv_list:
        df = pd.read_csv(csv_path)
        required = {"station_id", "product", "year", "month", "precip_mm_day"}
        missing  = required - set(df.columns)
        if missing:
            raise ValueError(
                f"{csv_path.name} missing columns: {missing}\n"
                f"  Found: {list(df.columns)}"
            )
        dfs.append(df)
        print(f"  Loaded: {csv_path.name}  "
              f"({df.product.unique().tolist()}, {len(df):,} rows)")

    grid_df = pd.concat(dfs, ignore_index=True)
    print(f"  Total rows: {len(grid_df):,}  "
          f"Products: {sorted(grid_df.product.unique().tolist())}")

    # ── Pivot: one column per product ────────────────────────
    grid_wide = grid_df.pivot_table(
        index   = ["station_id", "year", "month"],
        columns = "product",
        values  = "precip_mm_day",
    ).reset_index()
    grid_wide.columns.name = None

    # ── Merge observations with gridded values ───────────────
    merged = obs_df.merge(
        grid_wide,
        on  = ["station_id", "year", "month"],
        how = "inner",
    )

    out_path = DATA_DIR / "merged_obs_grid.csv"
    merged.to_csv(out_path, index=False)
    print(f"\n  Merged dataset saved → {out_path}  shape={merged.shape}")
    print(f"  Columns: {list(merged.columns)}")
    return merged


# ════════════════════════════════════════════════════════════
# § 5  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═" * 60)
    print("  GAUGE EXTRACTION — Step 2")
    print("═" * 60)

    # ── Load stations and observations ───────────────────────
    # Option A: demo data (default)
    stations_df, obs_df, station_fc = get_stations_and_obs()

    # Option B: real gauge CSV — uncomment when available
    # stations_df, obs_df, station_fc = get_stations_and_obs(
    #     stations_csv = "data/wa_gauge_stations.csv",
    #     obs_csv      = "data/wa_gauge_obs_2001_2020.csv",
    # )

    # Option C: GPCC .nc file — uncomment when downloaded
    # obs_df = load_gpcc_from_nc(
    #     "data/gpcc_full_v2022_025.nc",
    #     stations_df
    # )

    # Save station locations as GeoJSON for inspection
    gdf = gpd.GeoDataFrame(
        stations_df,
        geometry=gpd.points_from_xy(stations_df.lon, stations_df.lat),
        crs="EPSG:4326",
    )
    gdf.to_file(DATA_DIR / "stations.geojson", driver="GeoJSON")
    print(f"  Station GeoJSON saved → {DATA_DIR}/stations.geojson")

    # ── Per-product extraction tracking ──────────────────────
    # Add product names here once their CSV has been downloaded
    # from Google Drive into DATA_DIR.
    # File naming: precip_extraction_<PRODUCT_NAME>.csv
    #
    # Update this list after each successful download:
    COMPLETED_EXTRACTION = []
    # e.g. COMPLETED_EXTRACTION = ["CHIRPS", "GPM_IMERG", "ERA5_LAND"]

    # ── Check which per-product CSVs already exist locally ───
    existing_csvs = sorted(DATA_DIR.glob("precip_extraction_*.csv"))
    existing_products = [
        f.stem.replace("precip_extraction_", "")
        for f in existing_csvs
    ]
    if existing_products:
        print(f"  Found local CSVs for: {existing_products}")

    # ── Decide: submit missing tasks or run merge ─────────────
    all_products     = list(COLLECTIONS.keys())
    done_products    = list(set(COMPLETED_EXTRACTION + existing_products))
    missing_products = [p for p in all_products if p not in done_products]

    if missing_products:
        print(f"\n  Missing extractions: {missing_products}")
        print(f"  Submitting GEE tasks …")
        tasks = extract_all_products(
            station_fc,
            products  = missing_products,
            completed = done_products,
        )
        print("\n  ⚠  Wait for tasks to complete, then:")
        print("     1. Download each precip_extraction_<PRODUCT>.csv")
        print(f"     2. Place files in: {DATA_DIR}")
        print("     3. Re-run this script to auto-merge")
    else:
        print("\n  All product CSVs present — running merge ....")

    # ── Merge all available CSVs with observations ────────────
    # Runs automatically as soon as any CSVs are present locally.
    # Partial merge is fine — more products can be added later.
    if existing_csvs:
        print(f"\n  Merging {len(existing_csvs)} product CSV(s) …")
        merged = merge_obs_and_grid(obs_df, DATA_DIR)
        print("\n  First 5 rows of merged dataset:")
        print(merged.head())
        if missing_products:
            print(f"\n  ⚠  Note: {missing_products} not yet included.")
            print(f"     Re-run after downloading remaining CSVs.")
    else:
        print("\n  No local CSVs yet — tasks submitted above, please wait.")