# Findings

The full quantitative results — per-zone metric tables, rankings, and the
complete decision matrix — are in the manuscript and the reproducible
outputs in this repository. This page summarises the headline results and
the operational guidance that follows from them.

## Headline results

- **GPM IMERG and CHIRPS consistently outperform** the other products
  across most zones and metrics.
- **Domain-wide statistics mask critical zone-specific failures.** Two
  clear examples from the study: ERA5-Land's dry bias in the Sahel, and
  TerraClimate's overestimation in the Soudanian zone. Either would be
  hidden by a West-Africa-wide average.
- **Optimal product selection is both zone- and application-dependent.**
  No single product wins everywhere, for every use.

## Zone-by-zone guidance

The following operational notes are what the study's decision tool
attaches to each zone:

| Zone | Guidance |
|---|---|
| **Saharian** | Hyper-arid. Categorical detection (FAR) is unstable at any threshold. Do not rely on absolute PBIAS alone. |
| **Sahelian** | Unimodal wet season (Jul–Sep). GPM IMERG leads on KGE. Threshold sensitivity should be reported in publications. |
| **Soudanian** | Reliable rainfall. CHIRPS and GPM IMERG are consistently strong — safe for hydrological modelling. |
| **Guinean** | Bimodal (Jun + Oct). Most products overestimate magnitude; prioritise correlation (r) over KGE. Use caution with TerraClimate for absolute values. |
| **Guineo-Congolean** | High-rainfall equatorial. GPM IMERG has the best KGE. TerraClimate severely overestimates — avoid for water balance. |
| **All West Africa (pooled)** | GPM IMERG leads overall — but zone-specific selection is always preferable to a pooled choice. |

## Why threshold sensitivity matters

A single-threshold categorical evaluation (the common practice) can give
a misleadingly confident picture in dry environments. The study shows
that in near-zero-rainfall zones, categorical metrics swing sharply with
the chosen threshold for *every* product — so a validation that reports
POD/FAR/CSI at just one threshold in a dryland context is fragile. The
recommendation is to report categorical metrics across a threshold sweep,
not a single value.

## The decision matrix

The study's central deliverable is an application-weighted decision
matrix: for each of seven conservation and water-management applications,
and for each ecological zone, it identifies the best-scoring product by
weighting the validation metrics according to what that application
actually needs. This is delivered as an interactive workbook
(`WA_Precipitation_Decision_Tool.xlsx`) with selector and scorecard
sheets, so a practitioner can pick an application and zone and read off
the recommended product together with the metrics behind that
recommendation.
