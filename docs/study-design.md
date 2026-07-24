# Study Design

## Objective

Provide West African practitioners with evidence-based, operationally
structured guidance on which global precipitation product to use for a
given application in a given ecological zone — and to do so with a
methodology that transfers to other regions.

## Domain and period

| Item | Detail |
|---|---|
| Study period | 2001–2020 (20 years) |
| Spatial domain | West Africa, approximately 4–18°N and 18°W–15°E |
| Temporal resolution | Monthly mean, mm/day |
| Harmonisation | Each product reduced to a common monthly mm/day basis on its own native grid |
| Rain/dry threshold | 1.0 mm/day (WMO convention); swept across 0.1, 0.5, 1.0, 2.0, 5.0 mm/day for the sensitivity analysis |

## Ecological zones

Evaluation is stratified across five West African ecological zones,
spanning the strong north–south rainfall gradient:

| Zone | Character |
|---|---|
| **Saharian** | Hyper-arid north; near-zero rainfall for much of the year. |
| **Sahelian** | Semi-arid; short single wet season; high inter-annual variability. |
| **Soudanian** | Single wet season, longer than the Sahel; transitional. |
| **Guinean** | Wetter; bimodal rainfall in parts; agriculturally important. |
| **Guineo-Congolean** | High-rainfall equatorial south. |

Zone stratification is central to the study: domain-wide averages mask
zone-specific product failures, and the whole point of the exercise is to
surface *where* a product succeeds or fails rather than only *whether* it
does on average.

!!! note "Zone assignment"
    Zone boundaries are defined by the `ecological_zones_5class`
    shapefile. Because the source polygons do not always extend far
    enough to cover some coastal gauge locations, station-to-zone
    assignment uses an expert climatological override consistent with
    the Köppen-Geiger and FAO ecological-zone classifications, applied
    consistently across the merge, validation, and figure steps.

## Products evaluated

| Product | Type | Native resolution | GEE collection |
|---|---|---|---|
| CHIRPS | Satellite-gauge | 0.05° | `UCSB-CHG/CHIRPS/DAILY` |
| ERA5-Land | Reanalysis | 0.1° | `ECMWF/ERA5_LAND/MONTHLY_AGGR` |
| GPM IMERG v07 | Satellite-gauge | 0.1° | `NASA/GPM_L3/IMERG_MONTHLY_V07` |
| MERRA-2 | Reanalysis | ~0.5° | `NASA/GSFC/MERRA/flx/2` |
| PERSIANN-CDR | Satellite | 0.25° | `NOAA/PERSIANN-CDR` |
| TerraClimate | Reanalysis-interp | ~0.04° | `IDAHO_EPSCOR/TERRACLIMATE` |

## Reference observations

The validation reference is **GPCC Full Data Daily v2022** gauge data,
extracted as monthly mean mm/day at 16 station locations across the five
zones. GPCC is used strictly as **point gauge observations** — it is the
ground truth that every gridded product is compared against, and it is
never itself gridded or interpolated into a competing surface.

!!! info "MERRA-2 extraction"
    MERRA-2 is stored as hourly imagery (~175,000 images over 2001–2020),
    and direct point extraction from the raw collection times out even
    for a single location. The study extracts MERRA-2 from pre-computed
    yearly monthly-climatology assets instead, reducing extraction from
    hours to seconds. This same workaround is carried into the
    `savana.rainfall` package's ingestion step.
