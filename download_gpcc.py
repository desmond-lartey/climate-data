"""
============================================================
GPCC Full Data Daily v2022 — Download & Extract
============================================================
Downloads GPCC daily precipitation NetCDF files (1.0° res)
for 2001-2020, extracts monthly mean mm/day at the 15 WA
gauge station locations, and saves: 

  DATA_DIR/gpcc_obs_2001_2020.csv
    columns: station_id, year, month, obs_mm_day

This CSV then replaces the synthetic demo observations in
merge_extractions.py — just uncomment the obs_csv line.

REQUIREMENTS
─────────────
  pip install requests xarray netCDF4 numpy pandas

HOW TO RUN
───────────
  python download_gpcc.py

Files are downloaded to DATA_DIR/gpcc_raw/ (~440 MB total).
Already-downloaded files are skipped automatically.

AFTER COMPLETION
─────────────────
In merge_extractions.py, change load_observations() call to:
  obs_df = load_observations(
      obs_csv = str(DATA_DIR / "gpcc_obs_2001_2020.csv")
  )
============================================================
"""

import requests
import gzip
import shutil
import calendar
import numpy as np
import pandas as pd
import xarray as xr 
from pathlib import Path

# ── Config ────────────────────────────────────────────────
DATA_DIR = Path(
    r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1"
    r"\precipitation_assessment\DATA_DIR"
)
RAW_DIR    = DATA_DIR / "gpcc_raw"
BASE_URL   = ("https://opendata.dwd.de/climate_environment/"
              "GPCC/full_data_daily_v2022/")
START_YEAR = 2001
END_YEAR   = 2020

# ── Station coordinates ───────────────────────────────────
STATIONS = {
    "WA001": (-17.47,  14.73),  # Dakar
    "WA002": ( -7.95,  12.65),  # Bamako
    "WA003": ( -1.52,  12.36),  # Ouagadougou
    "WA004": (  2.17,  13.51),  # Niamey
    "WA005": (  7.33,   9.07),  # Abuja
    "WA006": ( -0.17,   5.56),  # Accra
    "WA007": ( -3.93,   5.35),  # Abidjan
    "WA008": (-13.67,   9.53),  # Conakry
    "WA009": (-13.23,   8.49),  # Freetown
    "WA010": (-10.80,   6.30),  # Monrovia
    "WA011": (  1.22,   6.13),  # Lomé
    "WA012": (  2.42,   6.37),  # Cotonou
    "WA013": (  8.52,  12.05),  # Kano
    "WA014": ( -1.62,   6.69),  # Kumasi
    "WA015": (-16.68,  13.45),  # Banjul 
    "WA016": (-15.97,  18.07),  # Nouakchott
    
}


# ════════════════════════════════════════════════════════════
# § 1  DOWNLOAD AND DECOMPRESS GPCC DAILY NETCDF FILES
# ════════════════════════════════════════════════════════════

def download_year(yr: int, raw_dir: Path) -> Path:
    """
    Download and decompress one yearly GPCC NetCDF file.
    Returns path to the decompressed .nc file.
    Skips download if file already exists.
    """
    fname_gz = f"full_data_daily_v2022_10_{yr}.nc.gz"
    fname_nc = fname_gz.replace(".gz", "")
    gz_path  = raw_dir / fname_gz
    nc_path  = raw_dir / fname_nc

    # Already decompressed — skip
    if nc_path.exists():
        print(f"  ✓  {fname_nc} already exists — skipping")
        return nc_path

    # Already downloaded but not decompressed
    if not gz_path.exists():
        url = BASE_URL + fname_gz
        print(f"  ↓  Downloading {fname_gz} ...", end=" ", flush=True)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(gz_path, "wb") as f:
            shutil.copyfileobj(resp.raw, f)
        size_mb = gz_path.stat().st_size / 1e6
        print(f"done ({size_mb:.1f} MB)")

    # Decompress
    print(f"  📦 Decompressing {fname_gz} ...", end=" ", flush=True)
    with gzip.open(gz_path, "rb") as f_in:
        with open(nc_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    gz_path.unlink()   # delete .gz to save space
    print("done")
    return nc_path


# ════════════════════════════════════════════════════════════
# § 2  EXTRACT MONTHLY MEANS AT STATION LOCATIONS
# ════════════════════════════════════════════════════════════

def extract_monthly_means(nc_path: Path) -> pd.DataFrame:
    """
    Open a GPCC daily NetCDF file, resample to monthly mean mm/day,
    and extract values at each station location using nearest-neighbour.

    GPCC variable: 'p' (mm/day at 1.0° resolution)
    Returns DataFrame: station_id, year, month, obs_mm_day
    """
    ds = xr.open_dataset(nc_path)

    # Find the precipitation variable
    # GPCC v2022 uses 'p' or 'precip'
    precip_var = None
    for v in ["p", "precip", "precipitation", "rain"]:
        if v in ds:
            precip_var = v
            break
    if precip_var is None:
        raise ValueError(
            f"Cannot find precip variable in {nc_path.name}.\n"
            f"Variables: {list(ds.data_vars)}"
        )

    da = ds[precip_var]   # shape: (time, lat, lon)

    # Resample daily → monthly mean (mm/day)
    da_monthly = da.resample(time="ME").mean(dim="time")

    rows = []
    for sid, (lon, lat) in STATIONS.items():
        # Nearest-neighbour extraction at station coordinates
        val = da_monthly.sel(
            lon=lon, lat=lat, method="nearest"
        )
        for t in val.time.values:
            ts = pd.Timestamp(t)
            v  = float(val.sel(time=t).values)
            rows.append({
                "station_id": sid,
                "year"      : ts.year,
                "month"     : ts.month,
                "obs_mm_day": round(max(0.0, v), 4),
            })

    ds.close()
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════
# § 3  MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("=" * 60)
    print("  GPCC DOWNLOAD & EXTRACTION")
    print("=" * 60)
    print(f"  DATA_DIR : {DATA_DIR}")
    print(f"  RAW_DIR  : {RAW_DIR}")
    print(f"  Years    : {START_YEAR}–{END_YEAR}")
    print(f"  Stations : {len(STATIONS)}")
    print()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for yr in range(START_YEAR, END_YEAR + 1):
        print(f"\n  ── Year {yr} ──────────────────────────")

        # Download
        try:
            nc_path = download_year(yr, RAW_DIR)
        except Exception as e:
            print(f"   Download failed for {yr}: {e}")
            continue

        # Extract
        try:
            print(f"  📊 Extracting monthly means ...", end=" ", flush=True)
            df_yr = extract_monthly_means(nc_path)

            # Filter to this year only
            df_yr = df_yr[df_yr["year"] == yr]
            all_rows.append(df_yr)

            n = len(df_yr)
            expected = len(STATIONS) * 12
            flag = "" if n >= expected * 0.9 else "⚠"
            print(f"{flag} {n} rows (expected {expected})")

            # Optional: delete NC after extraction to save space
            # nc_path.unlink()

        except Exception as e:
            print(f"   Extraction failed for {yr}: {e}")
            import traceback
            traceback.print_exc()
            continue

    if not all_rows:
        print("\n No data extracted!")
    else:
        combined = pd.concat(all_rows, ignore_index=True)
        combined = combined.sort_values(
            ["station_id", "year", "month"]
        ).reset_index(drop=True)

        out_path = DATA_DIR / "gpcc_obs_2001_2020.csv"
        combined.to_csv(out_path, index=False)

        print("\n" + "=" * 60)
        print("  GPCC EXTRACTION COMPLETE")
        print("=" * 60)
        print(f"  Output   : {out_path.name}")
        print(f"  Rows     : {len(combined):,}  "
              f"(expected {len(STATIONS)*20*12:,})")
        print(f"  Stations : {sorted(combined['station_id'].unique())}")
        print(f"  Years    : {combined['year'].min()}–"
              f"{combined['year'].max()}")
        print(f"  NaN      : {combined['obs_mm_day'].isna().sum()}")
        print(f"\n  Mean obs_mm_day per station:")
        print(combined.groupby("station_id")["obs_mm_day"]
              .mean().round(3).to_string())

        print(f"""
  ════════════════════════════════════════════════════
  NEXT STEP — use real GPCC obs in merge_extractions.py
  ════════════════════════════════════════════════════
  In merge_extractions.py, update load_observations():

    obs_df = load_observations(
        obs_csv = str(DATA_DIR / "gpcc_obs_2001_2020.csv")
    )

  Then re-run the full pipeline:
    python merge_extractions.py
    python validation_metrics.py
    python visualisation.py
  ════════════════════════════════════════════════════
        """)
