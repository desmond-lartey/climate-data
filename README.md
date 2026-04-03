# West Africa Precipitation Products — Comparative Assessment
**2001–2020 | Python Pipeline | Google Earth Engine Dashboard**

---

## Why this work matters

Accurate precipitation data is a foundation of almost every environmental decision in West Africa — from drought early warning and crop yield forecasting to flood risk mapping, water resource management, and biodiversity conservation planning. Yet the region remains one of the most data-sparse on Earth. Rain gauge networks are thin and unevenly distributed, and the gridded satellite and reanalysis products that fill the gap vary substantially in accuracy depending on location, season, and ecological context.

This framework systematically evaluates six widely used global precipitation products against real gauge-based observations across five ecological zones — from the hyperarid Saharian north to the equatorial Guineo-Congolean south. The goal is not simply to rank products but to characterise *where*, *when*, and *why* they succeed or fail, providing actionable guidance for researchers, hydrologists, and conservation practitioners choosing datasets for applications in the region.

For conservation management specifically, the findings help answer questions such as: Which product should underpin a drought monitoring system for the Sahelian zone? Which best captures the bimodal rainfall signal critical for agricultural calendars in the Guinean zone? Where is product uncertainty high enough to warrant caution in habitat suitability modelling?

---

## Study design

| Item | Detail |
|---|---|
| Study period | 2001–2020 (20 years) |
| Spatial domain | West Africa (approx. 20°W–15°E, 4°N–21°N) |
| Target resolution | 0.25° (~27 km), monthly mean mm/day |
| Observation source | GPCC Full Data Daily v2022, extracted at 16 stations |
| Rain/dry threshold | 1.0 mm/day (WMO convention) |
| Ecological zones | Saharian · Sahelian · Soudanian · Guinean · Guineo-Congolean |

### Gauge stations

| ID | City | Country | Zone |
|---|---|---|---|
| WA001 | Dakar | Senegal | Sahelian |
| WA002 | Bamako | Mali | Sahelian |
| WA003 | Ouagadougou | Burkina Faso | Sahelian |
| WA004 | Niamey | Niger | Sahelian |
| WA005 | Abuja | Nigeria | Soudanian |
| WA006 | Accra | Ghana | Guineo-Congolean |
| WA007 | Abidjan | Côte d'Ivoire | Guineo-Congolean |
| WA008 | Conakry | Guinea | Soudanian |
| WA009 | Freetown | Sierra Leone | Guinean |
| WA010 | Monrovia | Liberia | Guinean |
| WA011 | Lomé | Togo | Guineo-Congolean |
| WA012 | Cotonou | Benin | Guineo-Congolean |
| WA013 | Kano | Nigeria | Soudanian |
| WA014 | Kumasi | Ghana | Guinean |
| WA015 | Banjul | Gambia | Sahelian |
| WA016 | Nouakchott | Mauritania | Saharian |

### Products evaluated

| Product | Type | Native resolution | GEE collection |
|---|---|---|---|
| CHIRPS | Satellite-gauge | 0.05° | `UCSB-CHG/CHIRPS/DAILY` |
| ERA5-Land | Reanalysis | 0.1° | `ECMWF/ERA5_LAND/MONTHLY_AGGR` |
| GPM IMERG v07 | Satellite-gauge | 0.1° | `NASA/GPM_L3/IMERG_MONTHLY_V07` |
| MERRA-2 | Reanalysis | ~0.5° | `NASA/GSFC/MERRA/flx/2` |
| PERSIANN-CDR | Satellite | 0.25° | `NOAA/PERSIANN-CDR` |
| TerraClimate | Reanalysis-interp | ~0.04° | `IDAHO_EPSCOR/TERRACLIMATE` |

---

## Repository structure

```
precipitation_assessment/
│
├── setup_config.py             ← CONFIG dict, product catalogue, paths,
│                                  rain threshold, study period
│
├── data_ingestion.py           ← GEE ImageCollection loading, unit
│                                  harmonisation (all products → mm/day),
│                                  monthly aggregation, export to Drive
│
├── gauge_extraction.py         ← GEE point extraction at station locations,
│                                  station FeatureCollection, obs loading
│
├── download_gpcc.py            ← Downloads GPCC Full Data Daily v2022 (.nc)
│                                  from DWD server, extracts monthly means
│                                  at 16 station coordinates
│
├── extract_wa016.py            ← GEE extraction of all 6 products at WA016
│                                  (Nouakchott) using sampleRegions
│
├── extract_wa016_merra2.py     ← GEE extraction of MERRA-2 at WA016 from
│                                  pre-exported yearly climatology assets
│                                  (avoids 175,000-image hourly timeout)
│
├── append_wa016.py             ← Appends WA016 rows to all 6 product CSVs.
│                                  Handles yearly MERRA-2 files separately.
│                                  MUST run before merge_extractions.py
│
├── merge_extractions.py        ← Rebuilds MERRA-2 from yearly splits
│                                  (preserving extra stations), loads all
│                                  products, joins with GPCC obs →
│                                  merged_obs_grid.csv
│
├── add_zones_to_merged.py      ← Adds zone_name and zone_id columns to
│                                  merged_obs_grid.csv using expert
│                                  climatological zone assignment →
│                                  merged_obs_grid_zoned.csv
│
├── validation_metrics.py       ← Computes 13 continuous + categorical
│                                  metrics per station / season / zone /
│                                  product. Outputs 6 validation CSVs.
│
├── visualisation.py            ← Produces 8 publication-quality figures
│                                  (Taylor diagram, heatmap, scatter,
│                                  boxplots, annual cycle, time series,
│                                  zonal heatmaps, zonal annual cycle)
│
├── spatial_analysis.py         ← GEE spatial operations: bias maps,
│                                  correlation maps, trend analysis
│
├── 06_run_pipeline.py          ← Master runner (executes all local steps
│                                  in sequence after GEE exports are done)
│
├── DATA_DIR/                   ← All input/output data files (see below)
├── ecological_zones_5class/    ← Zone shapefile (SHP + GeoJSON)
├── outputs/                    ← Additional outputs
└── README.md
```

---

## Data directory (`DATA_DIR/`)

```
DATA_DIR/
├── gpcc_raw/                         ← GPCC yearly .nc files (downloaded by download_gpcc.py)
│   ├── full_data_daily_v2022_10_2001.nc
│   └── ...
│
├── gpcc_obs_2001_2020.csv            ← GPCC monthly obs at 16 stations (output of download_gpcc.py)
│
├── precip_extraction_CHIRPS.csv      ← GEE-extracted monthly values at 16 stations
├── precip_extraction_ERA5_LAND.csv
├── precip_extraction_GPM_IMERG.csv
├── precip_extraction_MERRA2.csv      ← Rebuilt from yearly splits by merge_extractions.py
├── precip_extraction_MERRA2_2001.csv ← Yearly MERRA-2 splits from GEE exports
├── precip_extraction_MERRA2_...csv
├── precip_extraction_PERSIANN_CDR.csv
├── precip_extraction_TERRACLIMATE.csv
│
├── merged_obs_grid.csv               ← Master dataset: 3840 rows × 10 cols
│                                        (16 stations × 20 yrs × 12 months)
├── merged_obs_grid_zoned.csv         ← Same + zone_name, zone_id columns
│
├── validation_per_station.csv        ← 13 metrics per station × product
├── validation_overall.csv            ← Pooled metrics per product
├── validation_by_season.csv          ← Metrics per season × product
├── validation_by_zone.csv            ← Metrics per ecological zone × product
├── product_ranking.csv               ← Composite score ranking overall
└── product_ranking_by_zone.csv       ← Composite score ranking per zone
```

---

## Pipeline: correct run order

This is the order that must be followed. Steps 1–3 require GEE access and produce files that are downloaded from Google Drive. Steps 4–8 run entirely locally.

```
─── REQUIRES GEE (submit tasks, download from Drive) ───────────────────

  Step 1   python data_ingestion.py
           Submit GEE export tasks for all 6 products (all stations).
           Download resulting CSVs to DATA_DIR.

  Step 2   python extract_wa016.py
           Submit 6 GEE tasks for WA016 (non-MERRA products).
           Download wa016_PRODUCT_2001_2020.csv to DATA_DIR.

  Step 3   python extract_wa016_merra2.py
           Submit 20 GEE tasks (one per year) for WA016 MERRA-2,
           reading from pre-exported climatology assets.
           Download wa016_MERRA2_YYYY.csv to DATA_DIR.

─── RUNS LOCALLY (no GEE required) ────────────────────────────────────

  Step 4   python download_gpcc.py
           Download GPCC Full Data Daily v2022 NetCDF files.
           Extract monthly obs_mm_day at 16 stations.
           Output: gpcc_obs_2001_2020.csv

  Step 5   python append_wa016.py
           Append WA016 rows to all 6 product extraction CSVs.
           Handles MERRA-2 yearly files separately.
           ⚠  Must run BEFORE merge_extractions.py

  Step 6   python merge_extractions.py
           Rebuild MERRA-2 from yearly splits (preserving WA016).
           Join all products with GPCC observations.
           Output: merged_obs_grid.csv

  Step 7   python add_zones_to_merged.py
           Add zone_name and zone_id columns.
           Output: merged_obs_grid_zoned.csv

  Step 8   python validation_metrics.py
           Compute all validation metrics.
           Output: 6 validation CSV files.

  Step 9   python visualisation.py
           Generate all 8 figures.
           Output: figures/ directory
```

---

## Validation metrics

### Continuous performance

| Metric | Full name | Perfect value | Detects |
|---|---|---|---|
| Bias | Mean error | 0 mm/day | Systematic over/under-estimation |
| PBIAS | Percent bias | 0% | Relative bias normalised by observed total |
| MAE | Mean absolute error | 0 | Average error magnitude |
| RMSE | Root mean squared error | 0 | Error magnitude, penalises extremes |
| r | Pearson correlation | 1 | Timing and seasonal pattern agreement |
| r² | Coefficient of determination | 1 | Variance explained |
| NSE | Nash-Sutcliffe efficiency | 1 | Skill vs using observed mean as predictor |
| KGE | Kling-Gupta efficiency | 1 | Combined correlation, variability, bias |

### Categorical (wet/dry detection at 1.0 mm/day threshold)

| Metric | Full name | Perfect value | Detects |
|---|---|---|---|
| POD | Probability of detection | 1 | Fraction of wet months correctly identified |
| FAR | False alarm ratio | 0 | Fraction of wet predictions that were actually dry |
| CSI | Critical success index | 1 | Combined detection skill |
| ETS | Equitable threat score | 1 | Detection skill adjusted for chance |
| Freq. bias | Frequency bias | 1 | Over/under-prediction of wet frequency |

---

## Output figures

| Figure | Description |
|---|---|
| Fig 1 — Taylor diagram | Correlation, standard deviation ratio, and centred RMSE for all products vs observations. Products close to the reference star perform best overall. |
| Fig 2 — Metric heatmap | Normalised heatmap of all 10 metrics across products. Green = better. |
| Fig 3 — Scatter plots | Observed vs gridded mm/day for each product. Red regression line shows systematic offset. |
| Fig 4 — Seasonal boxplots | Precipitation distribution per season (DJF/MAM/JJA/SON) for obs vs all products. |
| Fig 5 — Annual cycle | Monthly mean pooled across all 16 stations — all products vs observations. |
| Fig 6 — Station time series | 2001–2020 monthly time series at each station. One figure per station. |
| Fig 7 — Zonal metric heatmap | KGE, r, NSE, PBIAS per ecological zone × product. |
| Fig 8 — Zonal annual cycle | Monthly climatology per zone — all products vs observations. 5 panels (one per zone). |

---

## Zone assignment

Ecological zone boundaries are defined by the `ecological_zones_5class` shapefile. Because the Sahelian polygon in the source file does not extend far enough west to cover Atlantic coast stations (Dakar, Banjul, Bamako), zone assignment uses an expert climatological override dictionary (`STATION_ZONE_OVERRIDE` in `validation_metrics.py`) rather than a geometric point-in-polygon test. This override is consistent with the Köppen-Geiger climate classification and the FAO Ecological Zones map. The same dictionary is used in `add_zones_to_merged.py` and `visualisation.py` so all outputs are consistent.

Zone 1 (Saharian) has no station data prior to the addition of WA016 (Nouakchott). GPCC gauge coverage at Nouakchott is verified at a mean of 0.99 gauges/day — sufficient for scientifically valid inclusion.

---

## MERRA-2 extraction: important note

MERRA-2 is stored as hourly images (~175,000 images over 2001–2020). Direct extraction using the raw GEE collection causes task timeouts even for a single point. The solution is to read from pre-exported yearly climatology assets (`climatology_MERRA2_YYYY` in `projects/ee-desmond/assets/`) using `sampleRegions` — each asset is a 12-band image (one band per month) with the monthly mean already computed. This approach extracts 12 values per station per year in seconds rather than hours.

If the climatology assets have not yet been exported, run `exportClimatologyAsAsset('MERRA2')` from the GEE JavaScript dashboard (§ 7 — Asset Export Utilities) for each year first.

---

## GEE JavaScript dashboard

A companion interactive dashboard (`WA_Precipitation_Assessment_GEE.js`) runs in the Google Earth Engine Code Editor and provides spatial analysis capabilities that complement the Python pipeline:

- Spatial bias maps, correlation maps, and trend maps per product
- Zone-filtered analysis using the ecological zones FeatureCollection
- Annual cycle charts and time series for any region or country
- Station-level validation against GPCC observations (§ 19)
- Categorical metrics (POD/FAR/CSI) as spatial maps
- Inter-product agreement map (pixel-wise standard deviation)
- Asset export utilities for climatology and bias images

The dashboard uses the same station coordinates and ecological zone definitions as the Python pipeline. Station validation in the dashboard reads from `projects/ee-desmond/assets/gpcc_obs_2001_2020` — the GPCC observations uploaded as a GEE Table asset.

---

## Dependencies

```bash
pip install requests xarray netCDF4 geopandas shapely \
            pandas numpy scipy matplotlib seaborn earthengine-api
```

Python 3.9+ recommended. GEE authentication required for Steps 1–3:

```bash
earthengine authenticate --project ee-desmond
```

---

## Status

This is an active research project. Script names, file structures, and pipeline steps may evolve as the work progresses. The run order documented above reflects the current stable state of the pipeline. Figures and validation outputs will be updated as MERRA-2 extraction completes for all 16 stations.

---

## Citation / acknowledgements

GPCC Full Data Daily Version 2022: Ziese et al. (2022), DOI: 10.5676/DWD_GPCC/FD_D_V2022_100
Google Earth Engine: Gorelick et al. (2017), Remote Sensing of Environment, 162, 18–27.