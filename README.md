# Precipitation Product Assessment

**Comparative evaluation and optimal selection of rainfall datasets for natural resource management applications.**

<p align="center">
  <a href="https://github.com/desmond-lartey/climate-data" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/status-research-blue" alt="Status"></a>
  <a href="https://github.com/desmond-lartey/climate-data/blob/main/LICENSE" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <img src="https://img.shields.io/badge/period-2001–2020-lightgrey" alt="Period">
  <img src="https://img.shields.io/badge/products-6-orange" alt="Products">
  <img src="https://img.shields.io/badge/zones-5%20ecological-brightgreen" alt="Zones">
</p>

Reliable precipitation data underpin conservation planning, hydrological
modelling, and natural resource management, yet validated guidance on
*which* global precipitation product best serves a *specific* application
in a *specific* ecological zone has been largely missing for West Africa.
This project provides that guidance through a zone-stratified comparative
validation of six global precipitation products against GPCC gauge
observations, and translates the results into an application-weighted
decision matrix for practitioners.

The methodology developed here is the basis of the `savana.rainfall`
module in the [savana package](https://github.com/desmond-lartey/savana),
which generalises this workflow so it can be applied to any region,
gauge network, or set of products.

## What this study does

- **Validates six products**, CHIRPS, ERA5-Land, GPM IMERG, MERRA-2,
  PERSIANN-CDR, and TerraClimate, against **GPCC Full Data Daily v2022**
  gauge observations at **16 stations** across **five ecological zones**,
  over **2001–2020**.
- **Applies a dual-class evaluation framework**: continuous performance
  metrics (bias, PBIAS, MAE, RMSE, r, r², NSE, KGE) alongside categorical
  wet/dry detection statistics (POD, FAR, CSI, ETS, frequency bias).
- **Introduces a threshold-sensitivity analysis** showing that
  categorical detection metrics are structurally unstable in near-zero
  rainfall environments, a caution for validation practice in drylands.
- **Produces an application-weighted decision matrix** ranking products
  across seven conservation and water-management applications, per zone.

## Headline findings

- **GPM IMERG and CHIRPS consistently outperform** the other products
  across most zones and metrics.
- **Domain-wide statistics hide zone-specific failures**, for example
  ERA5-Land's Sahelian dry bias and TerraClimate's Soudanian
  overestimation, which is precisely why zone-stratified evaluation
  matters.
- **Optimal product choice is both zone- and application-dependent.**
  There is no single best product; the decision matrix makes the
  trade-offs explicit.

Specific per-zone values, rankings, and the full decision matrix are in
the manuscript and the reproducible outputs in this repository.

## Study design at a glance

| Item | Detail |
|---|---|
| Study period | 2001–2020 (20 years) |
| Spatial domain | West Africa (≈ 18°W–15°E, 4°N–18°N) |
| Harmonisation | Monthly mean mm/day, each product on its native grid |
| Observation source | GPCC Full Data Daily v2022, at 16 gauge stations |
| Rain/dry threshold | 1.0 mm/day (WMO convention), swept 0.1–5.0 mm/day |
| Ecological zones | Saharian · Sahelian · Soudanian · Guinean · Guineo-Congolean |

## Repository layout

```
climate-data/
├── pipeline/            the clean, ordered analysis pipeline (run these)
├── gee-full-script/     the companion Google Earth Engine dashboard (JavaScript)
├── ecological_zones_5class/   ecological zone boundaries (SHP + GeoJSON)
├── figures/             publication figures produced by the pipeline
├── outputs/             the decision-tool workbook and derived tables
├── DATA_DIR/            input/output data files (GPCC obs, extractions, merged grids)
├── notebooks/           exploratory notebooks used during the study
└── archive/             one-off scripts kept for provenance (not the entry point)
```

> **Note on scripts.** During the study a number of one-off scripts were
> written (per-station back-fills, MERRA-2 re-submissions, figure
> iterations). These are retained under `archive/` for provenance, but
> the **clean, ordered pipeline** is the entry point, see the
> [documentation](https://desmond-lartey.github.io/climate-data/)
> for the correct run order.

## Documentation

Full documentation, study design, pipeline run order, validation
metrics, the Earth Engine dashboard, and how this feeds the `savana`
package, is published at:

**https://desmond-lartey.github.io/climate-data/**

## Reproducing the study

See the [Pipeline](https://desmond-lartey.github.io/climate-data/pipeline/)
page for the exact run order. In brief: three Earth-Engine steps submit
extraction tasks and download results, then the remaining steps run
locally to download GPCC observations, merge everything into a master
grid, assign zones, compute validation metrics, run the threshold
sensitivity analysis, and generate figures and the decision workbook.

```bash
pip install requests xarray netCDF4 geopandas shapely \
            pandas numpy scipy matplotlib seaborn earthengine-api openpyxl
earthengine authenticate
```

## Related work

This study is the empirical foundation of the **`savana.rainfall`**
module, which packages the whole workflow so it can be pointed at any
region, gauge network, product set, zone scheme, and application
weighting:

- Package: https://github.com/desmond-lartey/savana
- Package docs: (see the savana documentation site)

## Citation

If you use this work, please cite the associated manuscript.

## Source Data

- **GPCC Full Data Daily v2022**, Ziese et al. (2022),
  DOI: 10.5676/DWD_GPCC/FD_D_V2022_100
- **Google Earth Engine**, Gorelick et al. (2017),
  *Remote Sensing of Environment*, 202, 18–27.

## License

MIT, see [LICENSE](LICENSE).

## Acknowledgments

We gratefully acknowledge the support of the following organizations:

-   [Ministerio de Ciencia, Innovación y Universidades (Spain)](https://www.aei.gob.es/convocatorias/buscador-convocatorias/proyectos-generacion-conocimiento-2024/convocatoria): This research is supported by the Agencia Estatal de Investigación (AEI) through Agreement No.: PID2024-158042OB-I00, awarded under [Knowledge Generation Projects and Actions](https://www.urv.cat/es/investigacion/proyectos-financiados-externamente/2025/00282/001/understanding-climate-dynamics-in-western-africa-using-a-new-observational-data-set).
-   [UNderstanding CLImate Dynamics in Western AFRica using a new Observational Data Set](https://uncliafro.eu/): This work is also  Co-funded by the European Union.