# Script Reference

This page documents the functions in each pipeline script. These scripts
are a **run-in-order study pipeline**, not an installable package — so
this is a reference for reading and adapting the study's code, not an
importable library API. For the reusable, installable version of this
method, see [Package API](package-api.md).

!!! note "Run order"
    See the [Pipeline](pipeline.md) page for the order these run in. This
    page is organised the same way.

## setup_config.py

Shared configuration: products, stations, zones, paths, and per-product
availability windows.

- **`get_product_window(key)`** — return `(start, end)` date strings
  clipped to a product's availability period.

## data_ingestion.py

Earth Engine ingestion and harmonisation of all six products to monthly
mean mm/day, plus the climatology-asset export utilities.

- **`build_roi()`** — load the study ROI from a GEE asset and dissolve to
  a single geometry.
- **`load_product(name, roi, start, end)`** — load a product's raw
  collection, clip to ROI, convert to mm/day.
- **`aggregate_to_monthly(ic, product_name)`** — aggregate to monthly
  mean mm/day, tagging year/month.
- **`resample_to_common(ic)`** — bilinear-resample every image to the
  common analysis grid.
- **`stations_to_ee_fc(stations_df)`** — convert the stations DataFrame
  to a GEE `FeatureCollection`.
- **`export_climatology_to_drive(product_name, drive_folder)`** /
  **`export_climatology_to_asset(product_name)`** — export a 12-band
  monthly climatology image.
- **`export_climatology_merra2_yearly(years, completed_years)`** — export
  MERRA-2 climatology one year at a time (avoids the 12-hour task
  timeout).
- **`merge_merra2_yearly_assets(...)`** — combine the yearly MERRA-2
  assets into one image.

Internal harmonisers (`_harmonise_scale`, `_harmonise_era5_monthly`,
`_harmonise_terra_monthly`, `_load_merra2_daily`, …) apply each product's
specific unit conversion.

!!! warning "Synthetic-observation helpers are deprecated"
    `data_ingestion.py` and `merge_extractions.py` still contain
    `_generate_demo_obs` / `_make_demo_obs` from early development, before
    real GPCC data was available. **Do not use these** — the study uses
    real GPCC observations via `download_gpcc.py`. The synthetic path was
    removed entirely from the `savana.rainfall` package for the same
    reason: fabricated ground truth makes every validation metric
    meaningless.

## gauge_extraction.py

Point-extraction of each product at the gauge stations, and the
observation/grid merge.

- **`get_stations_and_obs(stations_csv, obs_csv)`** — return
  `(stations_df, obs_df, station_fc)`.
- **`load_gpcc_from_nc(nc_path, stations_df)`** — extract GPCC monthly
  values at station locations from a NetCDF file.
- **`extract_product(station_fc, product_name, drive_folder)`** — sample
  one product's monthly collection at every station.
- **`extract_all_products(station_fc, products, drive_folder, completed)`**
  — submit one extraction task per product (runs in parallel on GEE).
- **`extract_merra2_from_assets(...)`** — extract MERRA-2 from the
  pre-exported yearly climatology assets.
- **`merge_obs_and_grid(obs_df, extraction_csvs)`** — join observed gauge
  precipitation with the extracted product values.

## download_gpcc.py

Local download and extraction of the GPCC validation reference.

- **`download_year(yr, raw_dir)`** — download and decompress one yearly
  GPCC NetCDF file.
- **`extract_monthly_means(nc_path)`** — open a GPCC daily NetCDF,
  resample to monthly mean mm/day at the stations.

## merge_extractions.py

Assemble the master obs-vs-products grid.

- **`load_extraction_csvs(data_dir)`** — load every product's extraction
  CSV.
- **`rebuild_merra2(data_dir, start, end)`** — reassemble MERRA-2 from its
  yearly pieces.
- **`load_observations(use_real, obs_csv)`** — load the GPCC observations
  (set `use_real=True`).
- **`build_merged(grid_df, obs_df, out_path)`** — write
  `merged_obs_grid.csv`.

## add_zones_to_merged.py

Add ecological-zone columns (`zone_name`, `zone_id`) to the merged grid,
producing `merged_obs_grid_zoned.csv`.

## validation_metrics.py

Continuous and categorical validation at every aggregation level.

- **`compute_continuous(obs, sim)`** — bias, PBIAS, MAE, RMSE, r, r²,
  NSE, KGE.
- **`compute_categorical(obs, sim, thresh)`** — POD, FAR, CSI, ETS,
  frequency bias.
- **`validate_per_station(df, products)`** /
  **`validate_overall(df, products)`** /
  **`validate_by_season(df, products)`** /
  **`validate_by_zone(df, station_zone, products)`** — metrics at each
  level.
- **`build_station_zone_map()`** — map each station to its ecological
  zone.
- **`rank_products(overall_df, zone_df)`** — composite product rankings.

## threshold_sensitivity.py

The wet/dry threshold sweep and its figures.

- **`categorical_metrics(obs, sim, threshold)`** — categorical metrics at
  one threshold.
- **`compute_threshold_table(df)`** — metrics across every
  product × zone × threshold combination.
- **`plot_metric_heatmaps(results)`**, **`plot_zone_lineplots(results)`**,
  **`plot_product_lines(results)`**, **`plot_west_africa_summary(results)`**,
  **`plot_zone_radar(results, threshold)`** — the sensitivity figures.

## visualisation.py

Publication figures.

- **`plot_taylor_diagram(...)`**, **`plot_metric_heatmap(...)`**,
  **`plot_scatter_grid(...)`**, **`plot_seasonal_boxplot(...)`**,
  **`plot_annual_cycle(...)`**, **`plot_station_timeseries(...)`**,
  **`plot_zonal_metric_heatmap(...)`**, **`plot_zonal_annual_cycle(...)`**.

## spatial_analysis.py

Earth Engine spatial maps (inter-product comparison — never against GPCC,
which is point data).

- **`compute_annual_mean(product_name)`** — long-term mean annual
  precipitation (mm/year).
- **`compute_bias_map(product_name, reference)`** — pixel-wise mean bias
  between two products.
- **`compute_correlation_map(product_name, reference)`** — pixel-wise
  monthly correlation.
- **`compute_trend_map(product_name)`** — pixel-wise linear trend
  (mm/day/year).
- **`build_comparison_map(...)`** / **`build_trend_map(...)`** —
  interactive layered maps.

## generate_decision_tool.py

The application-weighted decision workbook.

- **`load_data()`** — load the validation CSVs.
- **`weighted_score(row, weights)`** — composite score from a metrics row.
- **`build_scores_table(vbz_full)`** — scores for every
  app × zone × product.
- **`build_workbook(data, scores_df)`** — write the interactive
  `.xlsx` (selector + scorecard + data sheets).

## 06_run_pipeline.py

- **`run_step(script, label)`** — run one pipeline step and report
  status. Chains the local steps once the Earth Engine exports are in
  place.
