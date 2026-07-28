# Archive — one-time scripts (provenance only)

These scripts are **not part of the reproducible pipeline**. They are
kept for transparency and provenance: they document data-repair and
build-history steps that were needed *once*, during the original study,
because the dataset was assembled incrementally rather than in a single
clean run.

**You do not need to run any of these to reproduce the study.** The
scripts in [`../pipeline/`](../pipeline) perform a complete 16-station
assessment from the start. Run those.

## What's here and why

### WA016 back-fill (Nouakchott — the 16th station)

The study was first built with 15 stations. WA016 was added later, so
rather than re-extract everything, these scripts back-filled just WA016
into the already-extracted CSVs:

- `extract_wa016.py`, `extract_wa016_merra2.py` — extract WA016 alone.
- `append_wa016.py`, `append_wa016_merra2.py` — append those WA016 rows
  into the existing product extraction CSVs.

A clean run doesn't need these: `pipeline/gauge_extraction.py` reads
`STATIONS_DF`, which already contains all 16 stations including WA016, so
a fresh extraction includes every station from the start.

### MERRA-2 assembly / repair

MERRA-2's hourly collection caused Earth Engine timeouts during the
study, producing several one-time assembly and repair scripts:

- `run_merra2_merge.py` — merge the yearly MERRA-2 climatology assets
  ("run ONCE").
- `fix_merra2_merge.py` — rebuild `precip_extraction_MERRA2.csv` from the
  yearly pieces ("run ONCE").
- `resubmit_merra2.py` — re-submit the MERRA-2 extraction from the
  pre-exported yearly assets.

The clean pipeline handles MERRA-2 correctly in one pass via the
asset-based approach in `pipeline/data_ingestion.py`.

### Diagnostics and superseded figures

- `diagnose_zones.py` — a one-off diagnostic for checking station→zone
  assignment during development.
- `fig_application_rankings.py` — an earlier version of the
  application-ranking figure, **superseded by**
  `fig_application_rankings_v4.py` (which is the version referenced by the
  study).

## The maintained, reusable version

For running this method on **any** region, gauge network, or product set
— cleanly, with all 16-station logic built in and no back-fill steps —
use the `savana.rainfall` package:
<https://github.com/desmond-lartey/savana>
