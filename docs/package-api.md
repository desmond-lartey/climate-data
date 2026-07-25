# Package API

The study's method is available as a proper importable API in the
**`savana.rainfall`** module of the
[savana package](https://github.com/desmond-lartey/savana). Unlike the
[pipeline scripts](script-reference.md) in this repository — which run in
a fixed order for this specific dataset — the package is a maintained,
versioned library you can call on any region.

Install:

```bash
pip install "savana[rainfall]"
```

## One-call entry point

**`validate_against_gpcc(...)`** runs the entire assessment and returns a
`RainfallAssessment` with all results attached.

```python
from savana.rainfall import validate_against_gpcc

result = validate_against_gpcc(
    stations=None,              # None = the 16 WA stations; or coords / file / DataFrame
    products=None,              # None = all 6; or a subset
    start_year=2001,
    end_year=2020,
    obs_source=None,            # "download" (any coords) or "ee_asset"
    cache_dir="savana_rainfall_data",
    zones_gdf=None,
    zones_fc=None,
    rain_threshold=1.0,
    ee_project="your-gcp-project-id",
)
print(result.summarize())
result.export_workbook("decision_tool.xlsx")
```

## The assessment object

**`RainfallAssessment(...)`** is the step-by-step, chainable form. Its
stages mirror this repository's pipeline one-to-one:

| Pipeline script | `RainfallAssessment` method |
|---|---|
| `download_gpcc.py` / gauge obs | `.get_observations(source=...)` |
| `data_ingestion.py` | `.ingest(start, end)` |
| `gauge_extraction.py` | `.extract(cache_dir=...)` |
| `add_zones_to_merged.py` | `.assign_zones(...)` |
| `merge_extractions.py` | `.merge()` |
| `validation_metrics.py` | `.validate()` |
| `threshold_sensitivity.py` | `.analyze_thresholds()` |
| decision scoring | `.score()` |
| `generate_decision_tool.py` | `.export_workbook(path)` |
| `visualisation.py` / `spatial_analysis.py` | `.preview_*()`, `.show(...)` |

```python
from savana.rainfall import RainfallAssessment

ra = RainfallAssessment(stations=(-1.5, 12.4), ee_project="your-gcp-project-id")
ra.ingest(start="2020-01-01", end="2020-12-31")
ra.get_observations(source="download")
ra.extract().merge()
ra.compare_table()          # obs vs every product, side by side
ra.validate().score()
print(ra.answer("which product is best for drought early warning?"))
```

## Full reference

The complete, auto-generated API reference (every function, class, and
parameter) lives in the savana package documentation:

- Package repository: <https://github.com/desmond-lartey/savana>
- The `savana.rainfall` module documentation on the savana docs site.

!!! note "Why the split"
    This repository is the citable study — the exact scripts that
    produced the manuscript's figures. The package is the reusable
    method. Reproduce or cite the West Africa results from here; run the
    same analysis elsewhere with the package.
