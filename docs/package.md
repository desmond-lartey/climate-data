# From Study to Package

This repository is the empirical study. The **method** it developed has
been generalised into the `savana.rainfall` module of the
[savana package](https://github.com/desmond-lartey/savana), so the same
workflow can be applied to any region, gauge network, product set, zone
scheme, and application weighting — not just West Africa and these 16
stations.

## What changed in the move to a package

The study's scripts are tailored to this specific dataset. The package
keeps the exact same methodology but makes every fixed choice an
overridable default:

| In the study (fixed) | In the package (default, overridable) |
|---|---|
| 16 West Africa stations | Any stations — a DataFrame, a file, or coordinates |
| 6 named products | Any subset, or your own product definitions |
| 5 West Africa ecological zones | Any zones you build, or none (pooled) |
| GPCC obs uploaded for these stations | GPCC downloaded for *any* coordinates, or your own asset |
| Seven fixed application weightings | Your own application-weight profiles |
| A run-in-order set of scripts | One call, or a step-by-step object |

## The same result, one call

What the study runs as a ten-step pipeline, the package runs as:

```python
from savana.rainfall import validate_against_gpcc

result = validate_against_gpcc(ee_project="your-gcp-project-id")
print(result.summarize())
result.export_workbook("decision_tool.xlsx")
```

That reproduces the West Africa study's configuration by default. To run
the *same method* somewhere else, pass different parameters:

```python
result = validate_against_gpcc(
    stations=[(-1.5, 12.4), (2.1, 6.5)],   # your stations
    products=["CHIRPS", "GPM_IMERG"],       # your product subset
    start_year=2015,
    end_year=2023,
    ee_project="your-gcp-project-id",
)
```

## Why keep both

- **This repository** is the citable study: the specific data, the
  figures in the manuscript, and the exact scripts that produced them.
  It is the record of *what was done*.
- **The package** is the reusable method: how to do the *same thing*
  anywhere. It is maintained, documented, and versioned independently.

If you want to reproduce or cite the West Africa results, use this
repository. If you want to run the analysis on your own region, use the
package.

## Links

- Package repository: <https://github.com/desmond-lartey/savana>
- Package module: `savana.rainfall`
