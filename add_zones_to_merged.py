"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 2b: Add Ecological Zone Columns to merged_obs_grid.csv
============================================================
Reads  : merged_obs_grid.csv
Writes : merged_obs_grid_zoned.csv  (adds zone_name, zone_id)

HOW TO RUN
───────────
  python add_zones_to_merged.py
============================================================
"""

import pandas as pd
from pathlib import Path

import sys, types
sys.path.insert(0, str(Path(__file__).parent))

def _load_config():
    src_path = Path(__file__).parent / "setup_config.py"
    if not src_path.exists():
        return None
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    lines = []
    for line in src.splitlines():
        if any(x in line for x in [
            "import ee","import geemap","ee.Initialize","ee.Authenticate"
        ]):
            lines.append("pass")
        else:
            lines.append(line)
    mod = types.ModuleType("setup_config_local")
    try:
        exec(compile("\n".join(lines), "setup_config.py", "exec"),
             mod.__dict__)
        return mod
    except Exception:
        return None

_cfg = _load_config()
if _cfg and hasattr(_cfg, "CONFIG"):
    CONFIG = _cfg.CONFIG
else:
    CONFIG = {
        "data_dir": r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR",
    }

DATA_DIR = Path(CONFIG["data_dir"])

# ════════════════════════════════════════════════════════════
# ZONE DEFINITIONS
# ════════════════════════════════════════════════════════════

ZONE_ORDER = [
    "Saharian",
    "Sahelian",
    "Soudanian",
    "Guinean",
    "Guineo-Congolean",
]

ZONE_ID_MAP = {z: i+1 for i, z in enumerate(ZONE_ORDER)}

# ── Expert climatological zone assignment ─────────────────
# The source shapefile does not extend far enough west to cover
# Atlantic coast stations — geopandas assigns them to the wrong
# zone. This lookup is based on Köppen-Geiger classification
# and cross-checked against the FAO Ecological Zones map.
# Saharian (zone 1) has no stations — none of the 15 WA gauge
# stations are located in the Sahara desert.
STATION_ZONE = {
    "WA001": "Sahelian",         # Dakar        14.73°N ~600  mm/yr
    "WA002": "Sahelian",         # Bamako        12.65°N ~1000 mm/yr
    "WA003": "Sahelian",         # Ouagadougou  12.36°N ~800  mm/yr
    "WA004": "Sahelian",         # Niamey        13.51°N ~560  mm/yr
    "WA005": "Soudanian",        # Abuja          9.07°N ~1200 mm/yr
    "WA006": "Guineo-Congolean", # Accra          5.56°N ~730  mm/yr
    "WA007": "Guineo-Congolean", # Abidjan        5.35°N ~1800 mm/yr
    "WA008": "Soudanian",        # Conakry        9.53°N ~4300 mm/yr
    "WA009": "Guinean",          # Freetown       8.49°N ~3000 mm/yr
    "WA010": "Guinean",          # Monrovia       6.30°N ~4500 mm/yr
    "WA011": "Guineo-Congolean", # Lomé           6.13°N ~900  mm/yr
    "WA012": "Guineo-Congolean", # Cotonou        6.37°N ~1300 mm/yr
    "WA013": "Soudanian",        # Kano          12.05°N ~860  mm/yr
    "WA014": "Guinean",          # Kumasi         6.69°N ~1500 mm/yr
    "WA015": "Sahelian",         # Banjul        13.45°N ~1000 mm/yr
    "WA016": "Saharian",        # 18.07°N — just above 18° threshold
}


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("=" * 60)
    print("  ADD ZONES TO MERGED DATASET")
    print("=" * 60)

    in_path  = DATA_DIR / "merged_obs_grid.csv"
    out_path = DATA_DIR / "merged_obs_grid_zoned.csv"

    if not in_path.exists():
        raise FileNotFoundError(
            f"merged_obs_grid.csv not found at {in_path}\n"
            "Run merge_extractions.py first."
        )

    df = pd.read_csv(in_path)
    print(f"  Loaded: {in_path.name}  shape={df.shape}")
    print(f"  Stations: {sorted(df['station_id'].unique())}")

    # Add zone columns
    df["zone_name"] = df["station_id"].map(STATION_ZONE)
    df["zone_id"]   = df["zone_name"].map(ZONE_ID_MAP)

    # Check for unmapped stations
    unmapped = df[df["zone_name"].isna()]["station_id"].unique()
    if len(unmapped) > 0:
        print(f"  ⚠  Unmapped stations: {unmapped}")
        print("     Add them to STATION_ZONE dict above")
    else:
        print("   All stations mapped to zones")

    # Summary
    print("\n  Zone assignment summary:")
    summary = (df.groupby(["zone_name","zone_id"])["station_id"]
               .nunique().reset_index()
               .rename(columns={"station_id":"n_stations"}))
    # Sort by zone_id
    summary = summary.sort_values("zone_id").reset_index(drop=True)
    for _, row in summary.iterrows():
        print(f"    Zone {int(row.zone_id)}: {row.zone_name:<22} "
              f"{int(row.n_stations)} station(s)")

    # Verify all 5 zones are represented in the lookup
    print("\n  Zone coverage check:")
    for z in ZONE_ORDER:
        stns = [s for s,v in STATION_ZONE.items() if v == z]
        rows = len(df[df["zone_name"] == z])
        if stns:
            print(f"     {z:<22} {len(stns)} station(s): {stns}  "
                  f"({rows} rows)")
        else:
            print(f"    ℹ  {z:<22} no stations assigned "
                  f"(zone exists in shapefile but no gauge data)")

    # Save
    df.to_csv(out_path, index=False)
    print(f"\n   Saved: {out_path.name}  shape={df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print("\n  NEXT: python validation_metrics.py")
