"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 2: Gauge Station Data Ingestion & Point Extraction
============================================================
Sources supported:
  A. GPCC First Guess / Full Data (already in GEE → Step 1)
  B. GHCN-Daily station CSV  (downloaded locally)
  C. User-supplied gauge CSV
Then extracts gridded product values at each gauge location.
"""

import ee
import geemap
import pandas as pd
import numpy as np
import geopandas as gpd
from pathlib import Path
from setup_config import CONFIG, PRODUCTS, ROI, TARGET_SCALE_M
from data_ingestion import COLLECTIONS

DATA_DIR = Path(CONFIG["data_dir"])

# ══════════════════════════════════════════════════════════
# 2.1  Load gauge station metadata
# ══════════════════════════════════════════════════════════

def load_gauge_stations(csv_path: str = None) -> pd.DataFrame:
    """
    Load gauge station list.
    Expected CSV columns: station_id, station_name, lon, lat, elevation_m
    If csv_path is None, a synthetic demo set is created.
    """
    if csv_path and Path(csv_path).exists():
        df = pd.read_csv(csv_path)
        print(f" Loaded {len(df)} gauge stations from {csv_path}")
    else:
        # ── Demo stations (replace with your real data) ───
        df = pd.DataFrame({
            "station_id":   ["G001","G002","G003","G004","G005",
                             "G006","G007","G008","G009","G010"],
            "station_name": ["Nairobi","Lagos","Cairo","Johannesburg",
                             "Dakar","Addis Ababa","Accra","Khartoum",
                             "Lusaka","Dar es Salaam"],
            "lon": [36.82, 3.39, 31.24, 28.04, -17.44,
                    38.74, -0.19, 32.56, 28.28, 39.27],
            "lat": [-1.29, 6.45, 30.06, -26.20, 14.69,
                     9.03,  5.55, 15.55, -15.41, -6.79],
            "elevation_m": [1661, 41, 23, 1753, 22,
                            2355,  61, 381, 1279,  55],
        })
        print(f"⚠  No CSV provided – using {len(df)} demo stations.")

    # Convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.lon, df.lat),
        crs="EPSG:4326"
    )
    return gdf


# ══════════════════════════════════════════════════════════
# 2.2  Load observed gauge precipitation (monthly)
# ══════════════════════════════════════════════════════════

def load_gauge_observations(obs_csv: str = None,
                             stations_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Load monthly observed precipitation for each station.
    Expected CSV columns:
        station_id, year, month, precip_mm_month
    If obs_csv is None, synthetic random data is generated.
    """

    if obs_csv and Path(obs_csv).exists():
        df = pd.read_csv(obs_csv)
        print(f" Loaded observations from {obs_csv}  shape={df.shape}")
        return df

    print("⚠ No observation CSV – generating synthetic gauge data.")

    records = []

    years  = range(int(CONFIG["start_date"][:4]),
                   int(CONFIG["end_date"][:4]) + 1)

    months = range(1, 13)

    rng = np.random.default_rng(42)

    for _, row in stations_df.iterrows():

        for yr in years:
            for mo in months:

                seasonal = 3 + 4 * np.sin(
                    np.pi * (mo - 3) / 6 +
                    np.pi * abs(row.lat) / 45
                )

                obs_daily = max(0, seasonal + rng.normal(0, 1.2))

                records.append({
                    "station_id": row.station_id,
                    "year": yr,
                    "month": mo,
                    "precip_mm_month": round(obs_daily * 30, 2)
                })

    df = pd.DataFrame(records)

    df.to_csv(DATA_DIR / "gauge_observations_synthetic.csv", index=False)

    return df


# ══════════════════════════════════════════════════════════
# 2.3  Extract gridded product values at gauge locations
# ══════════════════════════════════════════════════════════

def extract_all_products(stations_gdf, products=None):

    if products is None:
        products = list(PRODUCTS.keys())

    # Convert stations to Earth Engine FeatureCollection
    features = [
        ee.Feature(
            ee.Geometry.Point([row.lon, row.lat]).buffer(5000),   # 5 km buffer
            {"station_id": row.station_id}
        )
        for _, row in stations_gdf.iterrows()
    ]

    stations_fc = ee.FeatureCollection(features)

    all_samples = []

    for pname in products:

        ic = COLLECTIONS[pname]

        def sample_image(img):

            date  = ee.Date(img.get("system:time_start"))

            year  = date.get("year")
            month = date.get("month")

            samples = img.select("precip_mm_month").reduceRegions(
                collection = stations_fc,
                reducer    = ee.Reducer.mean(),
                scale      = TARGET_SCALE_M
            )

            return samples.map(
                lambda f: f.set({
                    "product": pname,
                    "year": year,
                    "month": month,
                    "precip_mm_month": f.get("mean")
                })
            )

        sampled = ic.map(sample_image).flatten()

        all_samples.append(sampled)

    merged_fc = ee.FeatureCollection(all_samples).flatten()

    print("Exporting extraction results to Google Drive...")

    task = ee.batch.Export.table.toDrive(
        collection = merged_fc,
        description = "precip_station_extraction",
        folder = "Precip_Assessment",
        fileFormat = "CSV"
    )

    task.start()

    print(" Export task started.")


# ══════════════════════════════════════════════════════════
# 2.4  Merge gauge observations with extracted grid values
# ══════════════════════════════════════════════════════════

def merge_obs_and_grid(obs_df: pd.DataFrame,
                       extraction_csv: str) -> pd.DataFrame:
    """
    Join observed gauge precipitation with extracted gridded values.

    extraction_csv must contain:
    station_id, product, year, month, precip_mm_month
    """

    grid_df = pd.read_csv(extraction_csv)

    # Pivot products into columns
    grid_df = grid_df.pivot_table(
        index=["station_id", "year", "month"],
        columns="product",
        values="precip_mm_month"
    ).reset_index()

    grid_df.columns.name = None

    # Rename observation column
    obs_df = obs_df.rename(columns={"precip_mm_month": "obs"})

    merged = obs_df.merge(
        grid_df,
        on=["station_id", "year", "month"],
        how="inner"
    )

    out_path = DATA_DIR / "merged_obs_grid.csv"

    merged.to_csv(out_path, index=False)

    print(f" Merged dataset saved → {out_path}  shape={merged.shape}")

    return merged


# ══════════════════════════════════════════════════════════
# 2.5  Run
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":

    # Load stations
    stations = load_gauge_stations()

    stations.to_file(DATA_DIR / "stations.geojson", driver="GeoJSON")

    # Load observations
    obs = load_gauge_observations(stations_df=stations)

    # Run Earth Engine extraction export
    extract_all_products(stations)

    print("\n⚠ Wait for the Earth Engine export to finish.")
    print("Download the CSV from Google Drive → Precip_Assessment")
    print("Place it inside the data directory.\n")

    extraction_csv = DATA_DIR / "precip_station_extraction.csv"

    if extraction_csv.exists():

        merged = merge_obs_and_grid(obs, extraction_csv)

        print(merged.head())

    else:

        print("Extraction CSV not found yet.")
        print("Run merge step after download.")
