"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Add Ecological Zone Column to merged_obs_grid.csv
============================================================
Reads merged_obs_grid.csv, assigns each station to one of
the 5 ecological zones, and saves merged_obs_grid_zoned.csv.

Runs ENTIRELY LOCALLY — no GEE, no extra files needed.

Zone assignment priority:
  1. Point-in-polygon using ecological_zones_5class.geojson
     (if found in the precipitation_assessment folder)
  2. Latitude-band fallback if GeoJSON not found

OUTPUT
───────
  merged_obs_grid_zoned.csv — same as merged_obs_grid.csv
  but with two extra columns:
    zone_name  : e.g. "Sahelian"
    zone_id    : 1–5 (north to south)

HOW TO RUN
───────────
  python add_zones_to_merged.py
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────
DATA_DIR = Path(
    r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR"
)

ECO_ZONES_SEARCH = [
    Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class.geojson"),
    Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class") / "ecological_zones_5class.shp",
    DATA_DIR / "ecological_zones_5class.geojson",
    DATA_DIR.parent / "ecological_zones_5class.geojson",
]

# ── Station coordinates (all 15 WA stations) ──────────────
STATIONS = {
    "WA001": {"name": "Dakar",        "lon": -17.47, "lat": 14.73},
    "WA002": {"name": "Bamako",       "lon":  -7.95, "lat": 12.65},
    "WA003": {"name": "Ouagadougou",  "lon":  -1.52, "lat": 12.36},
    "WA004": {"name": "Niamey",       "lon":   2.17, "lat": 13.51},
    "WA005": {"name": "Abuja",        "lon":   7.33, "lat":  9.07},
    "WA006": {"name": "Accra",        "lon":  -0.17, "lat":  5.56},
    "WA007": {"name": "Abidjan",      "lon":  -3.93, "lat":  5.35},
    "WA008": {"name": "Conakry",      "lon": -13.67, "lat":  9.53},
    "WA009": {"name": "Freetown",     "lon": -13.23, "lat":  8.49},
    "WA010": {"name": "Monrovia",     "lon": -10.80, "lat":  6.30},
    "WA011": {"name": "Lomé",         "lon":   1.22, "lat":  6.13},
    "WA012": {"name": "Cotonou",      "lon":   2.42, "lat":  6.37},
    "WA013": {"name": "Kano",         "lon":   8.52, "lat": 12.05},
    "WA014": {"name": "Kumasi",       "lon":  -1.62, "lat":  6.69},
    "WA015": {"name": "Banjul",       "lon": -16.68, "lat": 13.45},
}

# ── Zone definitions (matches GEE JS dashboard exactly) ───
ZONE_DEFS = [
    {"id": 1, "name": "Saharian",         "lat_min": 18.0, "lat_max": 90.0},
    {"id": 2, "name": "Sahelian",         "lat_min": 12.0, "lat_max": 18.0},
    {"id": 3, "name": "Soudanian",        "lat_min":  8.0, "lat_max": 12.0},
    {"id": 4, "name": "Guinean",          "lat_min":  6.5, "lat_max":  8.0},
    {"id": 5, "name": "Guineo-Congolean", "lat_min": -5.0, "lat_max":  6.5},
]


# ════════════════════════════════════════════════════════════
# § 1  ASSIGN ZONES TO STATIONS
# ════════════════════════════════════════════════════════════

def assign_zones_geojson(eco_zones_path: str) -> dict:
    """Point-in-polygon assignment using GeoJSON/SHP."""
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.read_file(eco_zones_path)
    print(f"  Zones loaded from: {Path(eco_zones_path).name}")
    print(f"  Zone names: {gdf['zone_name'].tolist()}")

    station_zone = {}
    for sid, info in STATIONS.items():
        pt    = Point(info["lon"], info["lat"])
        match = gdf[gdf.geometry.contains(pt)]
        if len(match) > 0:
            z = match.iloc[0]
            station_zone[sid] = {
                "zone_name": z["zone_name"],
                "zone_id"  : int(z["zone_id"])
                             if "zone_id" in z.index else
                             next(d["id"] for d in ZONE_DEFS
                                  if d["name"] == z["zone_name"]),
            }
        else:
            # Point not in any polygon — fall back to latitude
            station_zone[sid] = assign_by_latitude(info["lat"])
            print(f"    ⚠  {sid} ({info['name']}) not in any polygon "
                  f"— latitude fallback → {station_zone[sid]['zone_name']}")

    return station_zone


def assign_by_latitude(lat: float) -> dict:
    """Fallback zone assignment by latitude band."""
    for z in ZONE_DEFS:
        if z["lat_min"] <= lat < z["lat_max"]:
            return {"zone_name": z["name"], "zone_id": z["id"]}
    return {"zone_name": "Soudanian", "zone_id": 3}   # safe default


def build_station_zone_map() -> dict:
    """
    Try GeoJSON point-in-polygon first, fall back to latitude bands.
    Returns dict: station_id → {zone_name, zone_id}
    """
    # Try to find ecological zones file
    for p in ECO_ZONES_SEARCH:
        if p.exists():
            try:
                return assign_zones_geojson(str(p))
            except ImportError:
                print("  ⚠  geopandas not available — using latitude fallback")
                break
            except Exception as e:
                print(f"  ⚠  GeoJSON load failed ({e}) — using latitude fallback")
                break

    print("  Using latitude-band zone assignment (no GeoJSON found)")
    return {
        sid: assign_by_latitude(info["lat"])
        for sid, info in STATIONS.items()
    }


# ════════════════════════════════════════════════════════════
# § 2  ADD ZONES TO MERGED CSV
# ════════════════════════════════════════════════════════════

def add_zones_to_merged(input_path: Path,
                         output_path: Path) -> pd.DataFrame:
    """
    Load merged_obs_grid.csv, add zone columns, save zoned version.
    """
    print(f"\n  Loading: {input_path.name}")
    df = pd.read_csv(input_path)
    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")

    # Build zone map
    print("\n  Assigning ecological zones to stations …")
    zone_map = build_station_zone_map()

    # Print assignment summary
    print("\n  Station → Zone assignments:")
    print(f"  {'Station':<8} {'Name':<15} {'Lat':>6}  {'Zone'}")
    print(f"  {'─'*8} {'─'*15} {'─'*6}  {'─'*20}")
    for sid, info in sorted(STATIONS.items()):
        z = zone_map.get(sid, {"zone_name": "Unknown", "zone_id": 0})
        print(f"  {sid:<8} {info['name']:<15} {info['lat']:>6.2f}  "
              f"{z['zone_name']} (id={z['zone_id']})")

    # Add zone columns
    df["zone_name"] = df["station_id"].map(
        lambda s: zone_map.get(s, {}).get("zone_name", "Unknown")
    )
    df["zone_id"] = df["station_id"].map(
        lambda s: zone_map.get(s, {}).get("zone_id", 0)
    )

    # Report zone distribution
    print("\n  Zone distribution (station-months):")
    zone_counts = df.groupby(["zone_name","zone_id"]).size().reset_index(name="n_rows")
    zone_counts = zone_counts.sort_values("zone_id")
    for _, row in zone_counts.iterrows():
        n_stations = df[df["zone_name"] == row["zone_name"]]["station_id"].nunique()
        print(f"    Zone {row['zone_id']} — {row['zone_name']:<20} "
              f"{n_stations} station(s),  {row['n_rows']:,} rows")

    # Save
    df.to_csv(output_path, index=False)
    print(f"\n   Saved → {output_path.name}")
    print(f"     Shape  : {df.shape}")
    print(f"     Columns: {list(df.columns)}")

    return df


# ════════════════════════════════════════════════════════════
# § 3  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  ADD ECOLOGICAL ZONES TO MERGED CSV")
    print("=" * 60)

    input_path  = DATA_DIR / "merged_obs_grid.csv"
    output_path = DATA_DIR / "merged_obs_grid_zoned.csv"

    if not input_path.exists():
        raise FileNotFoundError(
            f"merged_obs_grid.csv not found at {input_path}\n"
            f"Run merge_extractions.py first."
        )

    df_zoned = add_zones_to_merged(input_path, output_path)

    print(f"""
  OUTPUT FILE
  ─────────────────────────────────────────────────────
  {output_path}

  EXTRA COLUMNS ADDED
    zone_name  — ecological zone name (string)
    zone_id    — zone number 1–5 (north to south)

  ZONE KEY
    1 — Saharian         (>18°N,   <25 mm/yr)
    2 — Sahelian         (14–18°N, 200–600 mm/yr)
    3 — Soudanian        (10–14°N, 600–1200 mm/yr)
    4 — Guinean          (7–10°N,  1200–2000 mm/yr)
    5 — Guineo-Congolean (<7°N,    >2000 mm/yr)

  USAGE IN ANALYSIS
    import pandas as pd
    df = pd.read_csv("merged_obs_grid_zoned.csv")
    # Filter to one zone
    sahelian = df[df["zone_name"] == "Sahelian"]
    # Group by zone
    df.groupby("zone_name")["CHIRPS"].mean()
  ─────────────────────────────────────────────────────
    """)
