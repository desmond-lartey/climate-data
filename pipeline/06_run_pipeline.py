"""
============================================================
GLOBAL PRECIPITATION PRODUCTS - COMPARATIVE ASSESSMENT
============================================================
Step 6: Master Runner — Execute Full Pipeline
============================================================
Run this script to execute all steps in sequence.
Alternatively, run each numbered script independently.
"""

import subprocess, sys, time

STEPS = [
    ("setup_config.py",    "Environment setup & configuration"),
    ("data_ingestion.py",  "GEE data ingestion & harmonisation"),
    ("02_gauge_extraction.py","Gauge station extraction"),
    ("03_validation_metrics.py","Statistical validation"),
    ("04_spatial_analysis.py","Spatial bias & trend mapping"),
    ("05_visualisation.py",   "Figure generation"),
]

def run_step(script: str, label: str):
    print(f"\n{'='*60}")
    print(f"  STEP: {label}")
    print(f"  FILE: {script}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run([sys.executable, script],
                            capture_output=False, text=True)
    elapsed = time.time() - t0
    status = " OK" if result.returncode == 0 else " FAILED"
    print(f"\n  {status}  ({elapsed:.1f}s)")
    return result.returncode == 0


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  GLOBAL PRECIPITATION ASSESSMENT PIPELINE")
    print("="*60)

    results = {}
    for script, label in STEPS:
        ok = run_step(script, label)
        results[script] = ok
        if not ok:
            print(f"\n⚠  Pipeline halted at {script}. Fix errors and rerun.")
            break

    print("\n" + "="*60)
    print("  PIPELINE SUMMARY")
    print("="*60)
    for script, ok in results.items():
        mark = "" if ok else ""
        print(f"  {mark}  {script}")

    all_ok = all(results.values())
    if all_ok:
        print("\n🎉 All steps completed successfully!")
        print("   Outputs: outputs/precipitation_assessment/")
        print("            ├── data/     (CSV metrics, extracted values)")
        print("            └── figures/  (PNG publication figures)")
