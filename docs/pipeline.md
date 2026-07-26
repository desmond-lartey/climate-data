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

All pipeline scripts live in the `pipeline/` folder and run from the
repository root. The first steps require Google Earth Engine (they submit
extraction tasks and download results); the rest run locally.

!!! success "Complete for all 16 stations"
    A fresh run reproduces the full 16-station study from the start.
    `pipeline/gauge_extraction.py` reads the canonical station list
    (all 16 WA stations, including WA016), so no back-fill step is
    needed. The one-time WA016 and MERRA-2 scripts in `archive/` are
    provenance only — you do not run them.

### Earth Engine steps (submit tasks, download from Drive)

```
Step 1   python pipeline/data_ingestion.py
         Harmonise all 6 products to monthly mm/day; export the
         per-product (and MERRA-2 yearly climatology) assets.

Step 2   python pipeline/gauge_extraction.py
         Point-extract every product at all 16 station locations
         (station FeatureCollection + sampleRegions).
```

### Local steps (no Earth Engine required)

```
Step 3   python pipeline/download_gpcc.py
         Download GPCC Full Data Daily v2022 and extract monthly
         obs_mm_day at the 16 stations.
         → gpcc_obs_2001_2020.csv

Step 4   python pipeline/merge_extractions.py
         Join all six products with the GPCC observations.
         → merged_obs_grid.csv

Step 5   python pipeline/add_zones_to_merged.py
         Add ecological-zone columns.
         → merged_obs_grid_zoned.csv

Step 6   python pipeline/validation_metrics.py
         Continuous + categorical metrics per station, season, zone,
         and pooled.
         → validation_*.csv

Step 7   python pipeline/threshold_sensitivity.py
         Sweep the wet/dry threshold (0.1–5.0 mm/day).

Step 8   python pipeline/visualisation.py
         Generate the publication figures.
         → figures/

Step 9   python pipeline/generate_decision_tool.py
         Build the application-weighted decision workbook.
         → outputs/WA_Precipitation_Decision_Tool.xlsx

Step 10  python pipeline/fig_application_rankings_v4.py
         Application-ranking figure from the decision-tool output.
```

`pipeline/06_run_pipeline.py` chains the local steps (3–10) once the
Earth Engine exports from steps 1–2 are in place.

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
