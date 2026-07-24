# Pipeline

The analysis runs in a fixed order. The first steps require Google Earth
Engine access — they submit extraction tasks and download the results
from Google Drive. The remaining steps run entirely locally.

!!! tip "Prefer the package for new work"
    This pipeline reproduces the published study exactly. If you want to
    run the *same method* on a different region, gauge network, or set of
    products, use the [`savana.rainfall`](package.md) package instead —
    it wraps every step below behind a single call and makes all the
    defaults overridable.

## Environment

```bash
pip install requests xarray netCDF4 geopandas shapely \
            pandas numpy scipy matplotlib seaborn earthengine-api openpyxl
earthengine authenticate
```

Python 3.9+ recommended.

## Run order

### Earth Engine steps (submit tasks, download from Drive)

```
Step 1   python data_ingestion.py
         Submit GEE export tasks for all 6 products at all stations,
         harmonised to monthly mm/day. Download the resulting CSVs.

Step 2   python gauge_extraction.py
         Point-extract each product at the 16 station locations
         (station FeatureCollection + sampleRegions).

Step 3   MERRA-2 climatology extraction
         Extract MERRA-2 from pre-exported yearly monthly-climatology
         assets (avoids the hourly-collection timeout).
```

### Local steps (no Earth Engine required)

```
Step 4   python download_gpcc.py
         Download GPCC Full Data Daily v2022 NetCDF files and extract
         monthly obs_mm_day at the 16 stations.
         → gpcc_obs_2001_2020.csv

Step 5   python merge_extractions.py
         Join all six products with the GPCC observations into one
         master grid.
         → merged_obs_grid.csv

Step 6   python add_zones_to_merged.py
         Add zone_name / zone_id columns via the climatological zone
         assignment.
         → merged_obs_grid_zoned.csv

Step 7   python validation_metrics.py
         Compute continuous and categorical metrics per station,
         season, zone, and pooled.
         → validation_*.csv

Step 8   python threshold_sensitivity.py
         Sweep the wet/dry threshold (0.1–5.0 mm/day) and record how
         categorical metrics respond.

Step 9   python visualisation.py
         Generate the publication figures.
         → figures/

Step 10  python generate_decision_tool.py
         Build the application-weighted decision workbook.
         → outputs/WA_Precipitation_Decision_Tool.xlsx
```

`06_run_pipeline.py` chains the local steps once the Earth Engine
exports are in place.

## Key data products

| File | Contents |
|---|---|
| `gpcc_obs_2001_2020.csv` | GPCC monthly observations at 16 stations |
| `precip_extraction_<PRODUCT>.csv` | Each product's monthly values at the stations |
| `merged_obs_grid.csv` | Master obs-vs-products table (16 stations × 20 yr × 12 mo) |
| `merged_obs_grid_zoned.csv` | Same, with ecological-zone columns |
| `validation_overall.csv` / `_by_zone.csv` / `_by_season.csv` / `_per_station.csv` | Metrics at each aggregation level |
| `product_ranking.csv` / `product_ranking_by_zone.csv` | Composite score rankings |
| `WA_Precipitation_Decision_Tool.xlsx` | Interactive application-weighted decision matrix |
