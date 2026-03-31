"""
============================================================
DIAGNOSTIC SCRIPT — Run this FIRST to diagnose zone issues
============================================================
Run:  python diagnose_zones.py
============================================================
"""
import sys
from pathlib import Path

print("="*60)
print("  ZONE DIAGNOSTICS")
print("="*60)

# 1. Check geopandas
print("\n[1] Checking geopandas...")
try:
    import geopandas as gpd
    from shapely.geometry import Point
    print(f"   geopandas {gpd.__version__} available")
    HAS_GP = True
except ImportError as e:
    print(f"  ❌ geopandas NOT available: {e}")
    HAS_GP = False

# 2. Check shapely
print("\n[2] Checking shapely...")
try:
    import shapely
    print(f"   shapely {shapely.__version__} available")
except ImportError as e:
    print(f"  ❌ shapely NOT available: {e}")

# 3. Find ecological zones files
print("\n[3] Searching for ecological zone files...")
search_dirs = [
    Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment"),
    Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class"),
    Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR"),
]
found_files = []
for d in search_dirs:
    if d.exists():
        for pat in ["*.geojson", "*.shp"]:
            for f in d.glob(pat):
                found_files.append(f)
                print(f"   Found: {f}")
    else:
        print(f"  ⚠  Dir not found: {d}")

if not found_files:
    print("  ❌ No zone files found!")

# 4. Try loading each file and test containment
print("\n[4] Testing zone file loading + point-in-polygon...")
STATIONS = {
    "WA001": (-17.47, 14.73),   # Dakar — should be Sahelian
    "WA002": ( -7.95, 12.65),   # Bamako — should be Sahelian/Soudanian
    "WA004": (  2.17, 13.51),   # Niamey — should be Sahelian
    "WA005": (  7.33,  9.07),   # Abuja — should be Soudanian/Guinean
    "WA013": (  8.52, 12.05),   # Kano — should be Soudanian
    "WA006": ( -0.17,  5.56),   # Accra — should be Guineo-Congolean
    "WA015": (-16.68, 13.45),   # Banjul — should be Sahelian
}

if HAS_GP and found_files:
    for fpath in found_files:
        print(f"\n  --- Testing {fpath.name} ---")
        try:
            gdf = gpd.read_file(str(fpath))
            print(f"  Rows: {len(gdf)}")
            print(f"  Columns: {list(gdf.columns)}")
            print(f"  CRS: {gdf.crs}")
            if "zone_name" in gdf.columns:
                print(f"  Zones: {sorted(gdf['zone_name'].unique())}")
            print(f"  Bounds: {gdf.total_bounds}")
            
            print("\n  Point-in-polygon test:")
            for stn, (lon, lat) in STATIONS.items():
                pt = Point(lon, lat)
                exact = gdf[gdf.geometry.contains(pt)]
                buf   = gdf[gdf.geometry.intersects(pt.buffer(0.5))]
                buf2  = gdf[gdf.geometry.intersects(pt.buffer(1.0))]
                
                if len(exact) > 0:
                    result = f" EXACT → {exact.iloc[0]['zone_name']}"
                elif len(buf) > 0:
                    result = f"~  BUFFER0.5 → {buf.iloc[0]['zone_name']}"
                elif len(buf2) > 0:
                    result = f"~  BUFFER1.0 → {buf2.iloc[0]['zone_name']}"
                else:
                    # Nearest
                    gdf2 = gdf.copy()
                    gdf2["dist"] = gdf2.geometry.centroid.distance(pt)
                    nearest = gdf2.sort_values("dist").iloc[0]
                    result = f"📍 NEAREST → {nearest['zone_name']} (dist={nearest['dist']:.3f}°)"
                
                print(f"    {stn} ({lon:7.2f}, {lat:.2f})  {result}")
        except Exception as e:
            print(f"  ❌ Error loading {fpath.name}: {e}")
            import traceback
            traceback.print_exc()

# 5. Check merged CSV
print("\n[5] Checking merged_obs_grid.csv...")
data_dir = Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR")
merged_path = data_dir / "merged_obs_grid.csv"
if merged_path.exists():
    import pandas as pd
    df = pd.read_csv(merged_path, nrows=5)
    print(f"   Found merged_obs_grid.csv")
    print(f"  Columns: {list(df.columns)}")
    print(f"  First rows:")
    print(df.head(3).to_string())
else:
    print(f"  ❌ Not found at {merged_path}")

# 6. Check validation_by_zone.csv
print("\n[6] Checking existing validation_by_zone.csv...")
vzone = data_dir / "validation_by_zone.csv"
if vzone.exists():
    import pandas as pd
    df = pd.read_csv(vzone)
    print(f"  Zones present: {sorted(df['zone_name'].unique())}")
    print(f"  Shape: {df.shape}")
else:
    print("  Not found")

print("\n" + "="*60)
print("  DIAGNOSIS COMPLETE — paste output above for analysis")
print("="*60)
