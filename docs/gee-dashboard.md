# Earth Engine Dashboard

A companion interactive dashboard runs in the Google Earth Engine Code
Editor and provides the *spatial* side of the analysis that complements
the station-based Python pipeline. Its source is in the repository's
`gee-full-script/` directory.

## What it provides

- **Spatial bias, correlation, and trend maps** for each product,
  relative to the others.
- **Zone-filtered analysis** using the ecological-zones FeatureCollection.
- **Annual-cycle charts and time series** for any region or country.
- **Station-level validation** against the GPCC observations uploaded as
  an Earth Engine table asset.
- **Categorical detection maps** (POD / FAR / CSI) as spatial layers.
- **Inter-product agreement** as a pixel-wise standard-deviation map.
- **Asset-export utilities** for climatology and bias images (including
  the MERRA-2 yearly climatology assets the pipeline depends on).

## Consistency with the Python pipeline

The dashboard uses the **same station coordinates and ecological-zone
definitions** as the Python pipeline, so the two are directly
comparable. Station validation in the dashboard reads GPCC observations
from the same table asset used to seed the study.

## Relationship to the maps in the package

The spatial-map capabilities of this dashboard are what the
[`savana.rainfall`](package.md) package reproduces — first as `geemap`
maps in notebooks, and (in progress) as native layers in the savana QGIS
plugin. Where the dashboard shows inter-product comparison maps, the
package follows the same convention: spatial map visuals compare gridded
products against each other, while formal validation against GPCC is done
at the point (gauge) level, because GPCC exists only as point
observations and is never rasterised.

## Script organisation

The `gee-full-script/` directory keeps the dashboard split into logical
modules (study area, stations, products, harmonisation, actions, UI
panels, and a main entry script) rather than one monolithic file, so it
is easier to read and adapt.
