# Global Precipitation Products — Comparative Assessment Framework
## Using `geemap` · GEE · GPCC Gauges · Reanalysis

---

## Overview

This framework provides a modular, step-by-step pipeline to:

1. Load multiple global gridded precipitation products from Google Earth Engine  
2. Ingest gauge observations (GPCC, GHCN, or custom CSV)  
3. Harmonise all data to a common grid and temporal resolution  
4. Compute continuous + categorical validation statistics  
5. Generate spatial bias/trend maps  
6. Produce publication-quality figures  

---

## Products Covered

| Product | Type | Native Res | Source |
|---|---|---|---|
| CHIRPS | Satellite-gauge merged | 0.05° | UCSB |
| PERSIANN-CDR | Satellite | 0.25° | NOAA |
| TRMM 3B42 | Satellite | 0.25° | NASA |
| GPM IMERG V06 | Satellite-gauge merged | 0.1° | NASA |
| ERA5 | Reanalysis | 0.25° | ECMWF |
| ERA5-Land | Reanalysis | 0.1° | ECMWF |
| MERRA-2 | Reanalysis | ~0.5° | NASA GSFC |
| GPCC Monthly | Gauge-based (reference) | 1.0° | DWD/WMO |

---

## File Structure

```
precipitation_assessment/
├── setup_config.py       ← Products catalogue + CONFIG dict
├── data_ingestion.py     ← GEE loading, unit harmonisation, resampling
├── 02_gauge_extraction.py   ← Gauge stations, observations, point extraction
├── 03_validation_metrics.py ← Continuous + categorical metrics, ranking
├── 04_spatial_analysis.py   ← Bias maps, correlation maps, trend analysis
├── 05_visualisation.py      ← Taylor diagram, heatmap, scatter, time series
├── 06_run_pipeline.py       ← Master runner (runs all steps in sequence)
└── README.md
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install geemap earthengine-api xarray pandas numpy scipy \
            matplotlib seaborn cartopy netCDF4 geopandas rasterio
```

### 2. Authenticate with Google Earth Engine
```bash
earthengine authenticate
```

### 3. Edit `setup_config.py`
- Set your GEE **project ID**
- Set `start_date` / `end_date`
- Set `roi_bbox` or `roi_country`
- Adjust `target_resolution_deg`

### 4. Provide gauge data (optional but recommended)
- Station metadata CSV: `station_id, station_name, lon, lat, elevation_m`
- Observation CSV: `station_id, year, month, precip_mm_day`
- Pass paths in `02_gauge_extraction.py → load_gauge_stations()` and `load_gauge_observations()`

### 5. Run the pipeline
```bash
python 06_run_pipeline.py
# OR run each step independently:
python setup_config.py
python data_ingestion.py
...
```

---

## Validation Metrics

### Continuous
| Metric | Description | Perfect |
|---|---|---|
| Bias | Mean error (mm/day) | 0 |
| PBIAS | Percent bias (%) | 0 |
| MAE | Mean absolute error | 0 |
| RMSE | Root mean square error | 0 |
| r | Pearson correlation | 1 |
| R² | Coefficient of determination | 1 |
| NSE | Nash-Sutcliffe efficiency | 1 |
| KGE | Kling-Gupta efficiency | 1 |

### Categorical (rain / no-rain at threshold 1 mm/day)
| Metric | Description | Perfect |
|---|---|---|
| POD | Probability of Detection | 1 |
| FAR | False Alarm Ratio | 0 |
| CSI | Critical Success Index | 1 |
| ETS | Equitable Threat Score | 1 |

---

## Outputs

```
outputs/precipitation_assessment/
├── data/
│   ├── stations.geojson
│   ├── gauge_observations_synthetic.csv
│   ├── extracted_grid_at_gauges.csv
│   ├── merged_obs_grid.csv
│   ├── validation_overall.csv
│   ├── validation_per_station.csv
│   ├── validation_by_season.csv
│   └── product_ranking.csv
└── figures/
    ├── fig1_taylor_diagram.png
    ├── fig2_metric_heatmap.png
    ├── fig3_scatter_plots.png
    ├── fig4_seasonal_boxplots.png
    ├── fig5_annual_cycle.png
    └── fig6_timeseries_<station_id>.png
```

GEE exports (to Google Drive):
- Long-term climatology GeoTIFFs per product
- Bias maps (product vs GPCC) per product
- Correlation maps per product
- Annual mean maps per product

---

## Key Customisation Points

| Parameter | Location | Purpose |
|---|---|---|
| `CONFIG["start_date"]` | `setup_config.py` | Study period start |
| `CONFIG["roi_country"]` | `setup_config.py` | Country subset |
| `CONFIG["target_resolution_deg"]` | `setup_config.py` | Common grid size |
| `RAIN_THRESHOLD` | `setup_config.py` | Rain/no-rain split |
| `PRODUCTS` dict | `setup_config.py` | Add/remove products |
| `csv_path=` | `02_gauge_extraction.py` | Real station metadata |
| `obs_csv=` | `02_gauge_extraction.py` | Real observations CSV |
| `reference=` | `04_spatial_analysis.py` | Reference product |

---

## Notes

- GEE export tasks can take minutes–hours for global extents; monitor at https://code.earthengine.google.com/tasks  
- For sub-daily products (GPM, TRMM, MERRA-2) the pipeline aggregates to monthly mean daily rate before any comparison  
- GPCC is used as the default gridded reference; substitute any other product via `reference=` parameter  
- All scripts are designed to be run independently or as a pipeline via `06_run_pipeline.py`
