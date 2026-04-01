"""
============================================================
GLOBAL PRECIPITATION PRODUCTS — COMPARATIVE ASSESSMENT
West Africa  |  2001–2020
============================================================
Step 3: Statistical Validation Metrics
============================================================
"""

import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter

try:
    import geopandas as gpd
    from shapely.geometry import Point
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

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
            "import ee", "import geemap", "ee.Initialize", "ee.Authenticate"
        ]):
            lines.append("pass  # skipped")
        else:
            lines.append(line)
    mod = types.ModuleType("setup_config_local")
    try:
        exec(compile("\n".join(lines), "setup_config.py", "exec"), mod.__dict__)
        return mod
    except Exception as e:
        print(f"  setup_config exec error: {e}")
        return None

_cfg = _load_config()
if _cfg is not None and hasattr(_cfg, "CONFIG"):
    CONFIG = _cfg.CONFIG
    RAIN_THRESHOLD = (getattr(_cfg, "RAIN_THRESHOLD_MM_DAY", None)
                      or getattr(_cfg, "RAIN_THRESHOLD", 1.0) or 1.0)
else:
    print("  Using hardcoded CONFIG fallback.")
    CONFIG = {
        "data_dir"   : r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\DATA_DIR",
        "figures_dir": r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\figures",
        "start_date" : "2001-01-01",
        "end_date"   : "2020-12-31",
    }
    RAIN_THRESHOLD = 1.0

DATA_DIR   = Path(CONFIG["data_dir"])
START_YEAR = int(CONFIG["start_date"][:4])
END_YEAR   = int(CONFIG["end_date"][:4])
RAIN_THRESHOLD = RAIN_THRESHOLD or 1.0

OBS_COL = "obs_mm_day"

# ════════════════════════════════════════════════════════════
# § 1  STATION METADATA & ZONE ASSIGNMENT
# ════════════════════════════════════════════════════════════

# Coordinates (lon, lat) for all 15 WA stations
STATION_COORDS = {
    "WA001": (-17.47, 14.73),  # Dakar, Senegal
    "WA002": ( -7.95, 12.65),  # Bamako, Mali
    "WA003": ( -1.52, 12.36),  # Ouagadougou, Burkina Faso
    "WA004": (  2.17, 13.51),  # Niamey, Niger
    "WA005": (  7.33,  9.07),  # Abuja, Nigeria
    "WA006": ( -0.17,  5.56),  # Accra, Ghana
    "WA007": ( -3.93,  5.35),  # Abidjan, Côte d'Ivoire
    "WA008": (-13.67,  9.53),  # Conakry, Guinea
    "WA009": (-13.23,  8.49),  # Freetown, Sierra Leone
    "WA010": (-10.80,  6.30),  # Monrovia, Liberia
    "WA011": (  1.22,  6.13),  # Lomé, Togo
    "WA012": (  2.42,  6.37),  # Cotonou, Benin
    "WA013": (  8.52, 12.05),  # Kano, Nigeria
    "WA014": ( -1.62,  6.69),  # Kumasi, Ghana
    "WA015": (-16.68, 13.45),  # Banjul, Gambia
    "WA016": (-15.97, 18.07),   # Nouakchott, Mauritania
}

# ── MANUAL ZONE OVERRIDE ──────────────────────────────────
# The source shapefiles do not cover the far-western Atlantic
# coast (Senegal/Gambia), causing geopandas to assign those
# stations to the wrong zone. This lookup is based on the
# Köppen–Geiger climate classification and the rainfall
# thresholds defined for each zone (Saharian <25 mm/yr,
# Sahelian 200–600 mm/yr, Soudanian 600–1200 mm/yr, etc.)
# and cross-checked against the FAO Ecological Zones map.
STATION_ZONE_OVERRIDE = {
    # Sahelian (200-600 mm/yr, 12-18°N) — western coast stations
    # misclassified as Soudanian by geopandas
    "WA001": "Sahelian",   # Dakar 14.73°N, ~600 mm/yr
    "WA002": "Sahelian",   # Bamako 12.65°N, ~1000 mm/yr → border Sahelian/Soudanian
    "WA003": "Sahelian",   # Ouagadougou 12.36°N, ~800 mm/yr → Soudanian-Sahelian
    "WA004": "Sahelian",   # Niamey 13.51°N, ~560 mm/yr → Sahelian
    "WA013": "Soudanian",  # Kano 12.05°N, ~860 mm/yr → Soudanian
    "WA015": "Sahelian",   # Banjul 13.45°N, ~1000 mm/yr → border
    # Soudanian (600-1200 mm/yr, 8-12°N)
    "WA005": "Soudanian",  # Abuja 9.07°N, ~1200 mm/yr
    "WA008": "Soudanian",  # Conakry 9.53°N — geopandas ok
    # Guinean (1200-2000 mm/yr)
    "WA009": "Guinean",    # Freetown 8.49°N, ~3000 mm/yr
    "WA010": "Guinean",    # Monrovia 6.30°N, ~4500 mm/yr
    "WA014": "Guinean",    # Kumasi 6.69°N, ~1500 mm/yr
    # Guineo-Congolean (>2000 mm/yr, equatorial)
    "WA006": "Guineo-Congolean",  # Accra 5.56°N, ~730 mm/yr
    "WA007": "Guineo-Congolean",  # Abidjan 5.35°N, ~1800 mm/yr
    "WA011": "Guineo-Congolean",  # Lomé 6.13°N, ~900 mm/yr
    "WA012": "Guineo-Congolean",  # Cotonou 6.37°N, ~1300 mm/yr
    "WA016": "Saharian",        # 18.07°N — just above 18° threshold
}

ZONE_ORDER = [
    "Saharian", "Sahelian", "Soudanian",
    "Guinean", "Guineo-Congolean"
]

SEASONS = {
    "DJF": [12, 1, 2],
    "MAM": [3, 4, 5],
    "JJA": [6, 7, 8],
    "SON": [9, 10, 11],
}


def build_station_zone_map() -> dict:
    """
    Returns dict: station_id → zone_name.

    Priority:
      1. STATION_ZONE_OVERRIDE (expert assignment based on climatology)
      2. geopandas point-in-polygon (for any station not in override)
      3. Latitude-band fallback
    """
    print("\n  Building station → zone map...")
    print("  [Using expert climatological override for all 15 stations]")
    
    # Start with the override — it covers all 15 stations
    station_zone = dict(STATION_ZONE_OVERRIDE)
    
    # Check if any station is missing from override
    missing = [s for s in STATION_COORDS if s not in station_zone]
    if missing:
        print(f"  ⚠  Stations not in override: {missing}")
        print("     Attempting geopandas fallback...")
        if HAS_GEOPANDAS:
            _fill_with_geopandas(station_zone, missing)
        else:
            _fill_with_latitude(station_zone, missing)

    print("\n  Station → Zone assignments:")
    for stn in sorted(station_zone):
        lon, lat = STATION_COORDS[stn]
        print(f"    {stn}  ({lon:7.2f}, {lat:6.2f})  →  {station_zone[stn]}")

    counts = Counter(station_zone.values())
    print("\n  Zone population:")
    for z in ZONE_ORDER:
        n = counts.get(z, 0)
        stars = "⚠ EMPTY" if n == 0 else f"{n} station(s)"
        print(f"    {z:<22}  {stars}")

    return station_zone


def _fill_with_geopandas(station_zone: dict, stations: list):
    search = [
        Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class")
        / "ecological_zones_5class.shp",
        Path(r"C:\Users\Gebruiker\OneDrive\Spain\Paper 1\precipitation_assessment\ecological_zones_5class.geojson"),
        DATA_DIR.parent / "ecological_zones_5class" / "ecological_zones_5class.shp",
    ]
    for p in search:
        if p.exists():
            try:
                gdf = gpd.read_file(str(p))
                for stn in stations:
                    lon, lat = STATION_COORDS[stn]
                    pt = Point(lon, lat)
                    match = gdf[gdf.geometry.contains(pt)]
                    if len(match) > 0:
                        station_zone[stn] = match.iloc[0]["zone_name"]
                    else:
                        gdf2 = gdf.copy()
                        gdf2["dist"] = gdf2.geometry.centroid.distance(pt)
                        station_zone[stn] = gdf2.sort_values("dist").iloc[0]["zone_name"]
                return
            except Exception as e:
                print(f"    geopandas load failed: {e}")
    _fill_with_latitude(station_zone, stations)


def _fill_with_latitude(station_zone: dict, stations: list):
    for stn in stations:
        _, lat = STATION_COORDS[stn]
        if lat > 18:
            station_zone[stn] = "Saharian"
        elif lat > 12:
            station_zone[stn] = "Sahelian"
        elif lat > 8:
            station_zone[stn] = "Soudanian"
        elif lat > 6:
            station_zone[stn] = "Guinean"
        else:
            station_zone[stn] = "Guineo-Congolean"


# ════════════════════════════════════════════════════════════
# § 2  METRIC FUNCTIONS
# ════════════════════════════════════════════════════════════

def _get_products(df: pd.DataFrame, products=None) -> list:
    exclude = {"station_id","year","month", OBS_COL,
               "zone_name","zone_id","season"}
    if products is not None:
        return [p for p in products if p in df.columns]
    return [c for c in df.columns if c not in exclude]


def compute_continuous(obs: np.ndarray, sim: np.ndarray) -> dict:
    mask = ~(np.isnan(obs) | np.isnan(sim))
    o, s = obs[mask], sim[mask]
    n = len(o)
    if n < 3:
        return {m: np.nan for m in
                ["n","bias","pbias","mae","rmse","r","r2","nse","kge"]}
    bias  = float(np.mean(s - o))
    pbias = float(100*np.sum(s-o)/np.sum(o)) if np.sum(o) else np.nan
    mae   = float(np.mean(np.abs(s - o)))
    rmse  = float(np.sqrt(np.mean((s - o)**2)))
    r     = float(np.corrcoef(o, s)[0,1]) if o.std()>1e-10 and s.std()>1e-10 else np.nan
    r2    = r**2 if not np.isnan(r) else np.nan
    nse   = float(1 - np.sum((o-s)**2)/np.sum((o-o.mean())**2))             if np.sum((o-o.mean())**2)>0 else np.nan
    alpha = s.std()/o.std() if o.std()>0 else np.nan
    beta  = s.mean()/o.mean() if o.mean()>0 else np.nan
    kge   = float(1-np.sqrt((r-1)**2+(alpha-1)**2+(beta-1)**2))             if not any(np.isnan(x) for x in [r, alpha or np.nan, beta or np.nan]) else np.nan
    return {"n":n, "bias":round(bias,3), "pbias":round(pbias,2),
            "mae":round(mae,3), "rmse":round(rmse,3),
            "r":round(r,4), "r2":round(r2,4) if r2 is not None and not np.isnan(r2) else np.nan,
            "nse":round(nse,4), "kge":round(kge,4)}


def compute_categorical(obs: np.ndarray, sim: np.ndarray,
                         thresh: float = 1.0) -> dict:
    mask = ~(np.isnan(obs) | np.isnan(sim))
    o, s = obs[mask], sim[mask]
    if len(o) < 3:
        return {m: np.nan for m in
                ["pod","far","csi","ets","freq_bias",
                 "hits","misses","false_al","correct_neg"]}
    ow = o >= thresh; sw = s >= thresh
    h=int(np.sum(ow&sw)); ms=int(np.sum(ow&~sw))
    fa=int(np.sum(~ow&sw)); cn=int(np.sum(~ow&~sw))
    tot = h+ms+fa+cn
    pod = h/(h+ms)   if (h+ms)>0   else np.nan
    far = fa/(h+fa)  if (h+fa)>0   else np.nan
    csi = h/(h+ms+fa)if (h+ms+fa)>0 else np.nan
    hr  = ((h+ms)*(h+fa))/tot if tot>0 else 0
    den = h+ms+fa-hr
    ets = (h-hr)/den if den>0 else np.nan
    fb  = (h+fa)/(h+ms) if (h+ms)>0 else np.nan
    return {"pod":round(float(pod),4),"far":round(float(far),4),
            "csi":round(float(csi),4),"ets":round(float(ets),4),
            "freq_bias":round(float(fb),4),
            "hits":h,"misses":ms,"false_al":fa,"correct_neg":cn}


def _all_metrics(obs, sim, thresh=None):
    t = thresh or RAIN_THRESHOLD
    m = compute_continuous(obs, sim)
    m.update(compute_categorical(obs, sim, t))
    return m


# ════════════════════════════════════════════════════════════
# § 3  VALIDATION FUNCTIONS
# ════════════════════════════════════════════════════════════

def validate_per_station(df, products=None):
    products = _get_products(df, products)
    rows = []
    for stn in df["station_id"].unique():
        sub = df[df["station_id"]==stn]
        obs = sub[OBS_COL].values
        for p in products:
            row = {"station_id": stn, "product": p}
            row.update(_all_metrics(obs, sub[p].values))
            rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(DATA_DIR/"validation_per_station.csv", index=False)
    print(f"   Per-station → {out.shape}")
    return out


def validate_overall(df, products=None):
    products = _get_products(df, products)
    rows = []
    for p in products:
        row = {"product": p}
        row.update(_all_metrics(df[OBS_COL].values, df[p].values))
        rows.append(row)
    out = pd.DataFrame(rows).set_index("product")
    out.to_csv(DATA_DIR/"validation_overall.csv")
    cols = [c for c in ["bias","pbias","rmse","r","nse","kge","pod","far","csi","ets"]
            if c in out.columns]
    print(f"\n   Overall metrics:")
    print(out[cols].round(4).to_string())
    return out


def validate_by_season(df, products=None):
    products = _get_products(df, products)
    rows = []
    for season, months in SEASONS.items():
        sub = df[df["month"].isin(months)]
        for p in products:
            row = {"season": season, "product": p}
            row.update(_all_metrics(sub[OBS_COL].values, sub[p].values))
            rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(DATA_DIR/"validation_by_season.csv", index=False)
    print(f"   Seasonal → {out.shape}")
    return out


def validate_by_zone(df, station_zone: dict, products=None):
    products = _get_products(df, products)
    dfc = df.copy()
    dfc["zone_name"] = dfc["station_id"].map(station_zone)
    dropped = dfc["zone_name"].isna().sum()
    if dropped > 0:
        print(f"  ⚠  {dropped} rows unmapped — dropped")
    dfc = dfc.dropna(subset=["zone_name"])

    rows = []
    for zone in ZONE_ORDER:
        sub = dfc[dfc["zone_name"]==zone]
        if sub.empty:
            print(f"  ⚠  Zone '{zone}' is EMPTY — no stations assigned")
            continue
        n_stns = sub["station_id"].nunique()
        for p in products:
            row = {"zone_name": zone, "product": p,
                   "n_stations": n_stns,
                   "n_station_months": int(sub[OBS_COL].notna().sum())}
            row.update(_all_metrics(sub[OBS_COL].values, sub[p].values))
            rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(DATA_DIR/"validation_by_zone.csv", index=False)
    print(f"   Zonal → {out.shape}")

    if "kge" in out.columns:
        pivot = out.pivot_table(index="zone_name", columns="product",
                                values="kge").round(3)
        order = [z for z in ZONE_ORDER if z in pivot.index]
        print("\n  KGE by zone × product:")
        print(pivot.reindex(order).to_string())
    return out


def rank_products(overall_df, zone_df=None):
    def _score(df):
        df = df.copy()
        s = pd.DataFrame(index=df.index)
        def norm(col, inv=False):
            mn,mx = col.min(),col.max()
            if mx==mn: return pd.Series(0.5,index=col.index)
            n=(col-mn)/(mx-mn)
            return 1-n if inv else n
        for m in ["r","r2","nse","kge","pod","csi","ets"]:
            if m in df.columns: s[f"s_{m}"]=norm(df[m].fillna(0))
        for m in ["rmse","far"]:
            if m in df.columns: s[f"s_{m}"]=norm(df[m].fillna(df[m].max()),inv=True)
        for m in ["bias","pbias"]:
            if m in df.columns: s[f"s_{m}"]=norm(df[m].abs().fillna(df[m].abs().max()),inv=True)
        df["composite_score"]=s.mean(axis=1).round(4)
        return df.sort_values("composite_score",ascending=False)

    ranked = _score(overall_df)
    cols=[c for c in ["bias","pbias","rmse","r","nse","kge","pod","csi","composite_score"]
          if c in ranked.columns]
    ranked[cols].to_csv(DATA_DIR/"product_ranking.csv")
    print("\n  Overall ranking:")
    print(ranked["composite_score"].to_string())

    if zone_df is not None:
        rows=[]
        for zone in ZONE_ORDER:
            sub=zone_df[zone_df["zone_name"]==zone]
            if sub.empty: continue
            scored=_score(sub.set_index("product"))
            for prod,row in scored.iterrows():
                rows.append({"zone_name":zone,"product":prod,
                              "composite_score":row["composite_score"],
                              "kge":row.get("kge",np.nan),
                              "nse":row.get("nse",np.nan),
                              "r":row.get("r",np.nan),
                              "pbias":row.get("pbias",np.nan)})
        zr=pd.DataFrame(rows)
        zr.to_csv(DATA_DIR/"product_ranking_by_zone.csv",index=False)
        pivot=zr.pivot_table(index="zone_name",columns="product",
                              values="composite_score").round(3)
        order=[z for z in ZONE_ORDER if z in pivot.index]
        print("\n  Composite score by zone:")
        print(pivot.reindex(order).to_string())
    return ranked


# ════════════════════════════════════════════════════════════
# § 4  ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n"+"="*60)
    print("  VALIDATION METRICS — Step 3")
    print("="*60)
    print(f"  DATA_DIR  : {DATA_DIR}")
    print(f"  Threshold : {RAIN_THRESHOLD} mm/day")

    merged_path = DATA_DIR / "merged_obs_grid.csv"
    if not merged_path.exists():
        raise FileNotFoundError(
            f"merged_obs_grid.csv not found at {merged_path}")

    merged = pd.read_csv(merged_path)
    print(f"  Loaded {merged_path.name}  shape={merged.shape}")

    if "obs" in merged.columns and OBS_COL not in merged.columns:
        merged = merged.rename(columns={"obs": OBS_COL})
        print("  Renamed: obs → obs_mm_day")

    merged = merged[(merged["year"]>=START_YEAR)&(merged["year"]<=END_YEAR)]
    print(f"  After period filter: {merged.shape}")

    products = _get_products(merged)
    print(f"  Products: {products}")

    # Zone assignment
    station_zone = build_station_zone_map()

    # Validations
    print("\n"+"─"*60)
    print("  Per-station ...")
    validate_per_station(merged, products)

    print("\n"+"─"*60)
    print("  Overall ...")
    overall = validate_overall(merged, products)

    print("\n"+"─"*60)
    print("  Seasonal ...")
    validate_by_season(merged, products)

    print("\n"+"─"*60)
    print("  Zonal ...")
    zone_m = validate_by_zone(merged, station_zone, products)

    print("\n"+"─"*60)
    print("  Rankings ...")
    rank_products(overall, zone_m)

    print("\n"+"="*60)
    print("  DONE — 6 files written to DATA_DIR")
    print("  NEXT: python visualisation.py")
    print("="*60)
