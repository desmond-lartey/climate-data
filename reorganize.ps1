# ============================================================
# Reorganize the climate-data study repo (PowerShell version).
#   pipeline/   - complete, self-sufficient 16-station reproduction
#   notebooks/  - exploratory notebooks
#   archive/    - one-time build/repair scripts (provenance only)
#
# Run from the repo root:
#   cd "C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment"
#   powershell -ExecutionPolicy Bypass -File reorganize.ps1
# Uses `git mv` so history is preserved.
# ============================================================

$ErrorActionPreference = "Stop"

# Fail early if this isn't a git repo root.
if (-not (Test-Path ".git")) {
    Write-Host "ERROR: run this from the repository root (no .git folder found here)." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path pipeline, notebooks, archive | Out-Null

$pipeline = @(
    "setup_config.py","data_ingestion.py","gauge_extraction.py","download_gpcc.py",
    "merge_extractions.py","add_zones_to_merged.py","validation_metrics.py",
    "threshold_sensitivity.py","visualisation.py","spatial_analysis.py",
    "generate_decision_tool.py","fig_application_rankings_v4.py","06_run_pipeline.py"
)
$notebooks = @(
    "WA_spatial_maps.ipynb","check.ipynb","data.ipynb","eco_zones.ipynb",
    "heatmap_grid_figures.ipynb","rainfall_product_performance.ipynb"
)
$archive = @(
    "append_wa016.py","append_wa016_merra2.py","extract_wa016.py",
    "extract_wa016_merra2.py","fix_merra2_merge.py","resubmit_merra2.py",
    "run_merra2_merge.py","diagnose_zones.py","fig_application_rankings.py"
)

function Move-Group($files, $dest) {
    foreach ($f in $files) {
        if (Test-Path $f) {
            git mv $f "$dest/$f"
            Write-Host "  moved $f -> $dest/" -ForegroundColor Green
        } else {
            Write-Host "  SKIP (not found): $f" -ForegroundColor Yellow
        }
    }
}

Write-Host "`nMoving pipeline scripts..." -ForegroundColor Cyan
Move-Group $pipeline "pipeline"

Write-Host "`nMoving notebooks..." -ForegroundColor Cyan
Move-Group $notebooks "notebooks"

Write-Host "`nMoving archive scripts..." -ForegroundColor Cyan
Move-Group $archive "archive"

Write-Host "`nDone. Review with:  git status" -ForegroundColor Cyan
Write-Host "Then commit:        git commit -m `"Reorganize into pipeline/ notebooks/ archive/`"" -ForegroundColor Cyan
