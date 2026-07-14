// ╔══════════════════════════════════════════════════════════════╗
// ║   WEST AFRICA — PRECIPITATION PRODUCTS ASSESSMENT           ║
// ║   Google Earth Engine  |  JavaScript API  |  v4             ║
// ║   Asset: projects/ee-desmond/assets/west_africa_boundary0   ║
// ╚══════════════════════════════════════════════════════════════╝
// 
//  ARCHITECTURE
//  ─────────────────────────────────────────────────────────────
//  § 0   CONFIG & CONSTANTS
//  § 1   STUDY AREA
//  § 2   PRODUCT CATALOGUE
//  § 3   UTILITY FUNCTIONS           ← pure math / stat helpers
//  § 4   HARMONISATION HELPERS       ← unit conversion per product
//  § 5   GAUGE STATION DATA          ← replace with real CSV asset
//  § 6   LAZY IC BUILDER + CACHE     ← builds monthly ICs on demand
//  § 7   ASSET EXPORT UTILITIES      ← export intermediate results
//  § 8   ASSET INGEST UTILITIES      ← re-load pre-exported assets
//  § 9   VIS PARAMS
//  § 10  UI — STYLES & HELPERS       ← all colour/font definitions
//  § 11  UI — PANEL LAYOUT
//  § 12  ACTION: CLIMATOLOGY MAPS
//  § 13  ACTION: BIAS MAPS
//  § 14  ACTION: CORRELATION MAP
//  § 15  ACTION: TREND MAP
//  § 16  ACTION: SEASONAL MAPS
//  § 17  ACTION: TIME-SERIES CHART
//  § 18  ACTION: ANNUAL CYCLE CHART
//  § 19  ACTION: STATION VALIDATION
//  § 20  ACTION: CATEGORICAL METRICS
//  § 21  MAP CLICK INSPECTOR
//  § 22  BOUNDARY OVERLAY
// ─────────────────────────────────────────────────────────────


// ════════════════════════════════════════════════════════════
// § 0  CONFIG & CONSTANTS
// ════════════════════════════════════════════════════════════

var CFG = {
  startDate    : '2001-01-01',
  endDate      : '2020-12-31',
  targetScale  : 25000,        // metres ≈ 0.25°  (use 50000 if still slow)
  chartScale   : 50000,        // coarser for charts — faster
  rainThresh   : 1.0,          // mm/day  wet / dry threshold
  defaultProd  : 'CHIRPS',
  defaultRef   : 'GPM_IMERG',
  exportFolder : 'WA_Precip_Assets',  // Google Drive folder for assets
  assetFolder  : 'projects/ee-desmond/assets/', // GEE asset path prefix
};

var START_YR = parseInt(CFG.startDate.split('-')[0], 10);
var END_YR   = parseInt(CFG.endDate.split('-')[0],   10);


// ════════════════════════════════════════════════════════════
// § 1  STUDY AREA
// ════════════════════════════════════════════════════════════

var BOUNDARY = ee.FeatureCollection(
  'projects/ee-desmond/assets/west_africa_boundary0');
var ROI = BOUNDARY
          //.filter(ee.Filter.eq('admin0Name', 'Ghana'))
          .geometry().simplify({maxError: 5000});


// Hard-coded centre for West Africa — avoids simplify() shifting centroid
Map.setCenter(-5, 12, 5);
Map.setOptions('HYBRID');

// ════════════════════════════════════════════════════════════
// § 1b  ECOLOGICAL ZONES
// ════════════════════════════════════════════════════════════

var ECO_ZONES_READY = true;  // set false if asset not yet exported

var ECO_ZONE_DEFS = [
  {id:1, name:'Saharian',         color:'#F5DEB3', rainfall:'<25 mm/yr'},
  {id:2, name:'Sahelian',         color:'#E8A838', rainfall:'200-600 mm/yr'},
  {id:3, name:'Soudanian',        color:'#CC6600', rainfall:'600-1200 mm/yr'},
  {id:4, name:'Guinean',          color:'#78C850', rainfall:'1200-2000 mm/yr'},
  {id:5, name:'Guineo-Congolean', color:'#1A6B1A', rainfall:'>2000 mm/yr'},
];

var ECO_ZONES = ECO_ZONES_READY
  ? ee.FeatureCollection('projects/ee-desmond/assets/ecological_zones_5class')
  : ee.FeatureCollection([]);

var ECO_ZONE_NAMES = ['All West Africa']
  .concat(ECO_ZONE_DEFS.map(function(z){ return z.name; }));

function getAnalysisRegion() {
  if (!ECO_ZONES_READY) return ROI;
  var sel = (typeof zoneSel !== 'undefined') ? zoneSel.getValue() : 'All West Africa';
  if (!sel || sel === 'All West Africa') return ROI;
  return ECO_ZONES.filter(ee.Filter.eq('zone_name', sel))
                  .geometry().intersection(ROI, ee.ErrorMargin(100));
}

function printZonalStats(img, label) {
  if (!ECO_ZONES_READY) return;
  var stats = img.reduceRegions({
    collection: ECO_ZONES,
    reducer   : ee.Reducer.mean(),
    scale     : CFG.chartScale,
  });
  print(' Zonal stats — ' + label + ':', stats.select(['zone_name','mean']));
}


// ════════════════════════════════════════════════════════════
// § 2  PRODUCT CATALOGUE
// ════════════════════════════════════════════════════════════

var PRODUCTS = {

  CHIRPS: {
    collection : 'UCSB-CHG/CHIRPS/DAILY',
    band       : 'precipitation',
    scaleFactor: 1.0,           // mm/day — no conversion needed
    isMonthly  : false,
    specialFn  : null,
    type       : 'Satellite-gauge',
    res        : '0.05°',
    color      : '#2196F3',     // blue
  },

  PERSIANN_CDR: {
    collection : 'NOAA/PERSIANN-CDR',
    band       : 'precipitation',
    scaleFactor: 1.0,           // mm/day
    isMonthly  : false,
    specialFn  : null,
    type       : 'Satellite',
    res        : '0.25°',
    color      : '#FF9800',     // orange
  },

  // TRMM_3B43: {
  //   collection : 'TRMM/3B43V7',
  //   band       : 'precipitation',
  //   scaleFactor: 24.0,          // mm/hr → mm/day
  //   isMonthly  : true,
  //   specialFn  : null,
  //   type       : 'Satellite-gauge',
  //   res        : '0.25°',
  //   color      : '#4CAF50',     // green
  // },

  GPM_IMERG: {
    collection : 'NASA/GPM_L3/IMERG_MONTHLY_V07',
    band       : 'precipitation',
    scaleFactor: 24.0,          // mm/hr → mm/day
    isMonthly  : true,
    specialFn  : null,
    type       : 'Satellite-gauge',
    res        : '0.1°',
    color      : '#F44336',     // red
  },

  ERA5_LAND: {
    collection : 'ECMWF/ERA5_LAND/MONTHLY_AGGR',
    band       : 'total_precipitation_sum',
    scaleFactor: null,          // special: ÷ daysInMonth × 1000
    isMonthly  : true,
    specialFn  : 'ERA5_MON',
    type       : 'Reanalysis',
    res        : '0.1°',
    color      : '#9C27B0',     // purple
  },

  MERRA2: {
    collection : 'NASA/GSFC/MERRA/flx/2',
    band       : 'PRECTOTCORR',
    scaleFactor: 86400.0,       // kg/m²/s → mm/day
    isMonthly  : false,
    specialFn  : null,
    type       : 'Reanalysis',
    res        : '~0.5°',
    color      : '#E91E63',     // pink
  },

  TERRACLIMATE: {
    collection : 'IDAHO_EPSCOR/TERRACLIMATE',
    band       : 'pr',
    scaleFactor: null,          // special: monthly accum ÷ daysInMonth
    isMonthly  : true,
    specialFn  : 'TERRA',
    type       : 'Reanalysis-interp',
    res        : '~0.04°',
    color      : '#00BCD4',     // cyan
  },
  

};

var PKEYS = Object.keys(PRODUCTS);  // shorthand list of product keys
print('Products loaded:', PKEYS);


// ════════════════════════════════════════════════════════════
// § 3  UTILITY FUNCTIONS  (pure helpers — no GEE side-effects)
// ════════════════════════════════════════════════════════════
/**
 * Compute Pearson r, bias, MAE, RMSE, NSE, KGE from a paired
 * ee.FeatureCollection with properties 'sim' and 'obs'.
 * Returns ee.Dictionary.
 * If fewer than 3 valid pairs exist, returns sentinel (-9999)
 * instead of crashing with "Dictionary does not contain key: r".
 */
function computeMetrics(pairs) {
  var n = pairs.size();

  var corrResult = pairs.reduceColumns(
    ee.Reducer.pearsonsCorrelation(), ['sim', 'obs']);

  // Key is "correlation" not "r" — confirmed by diagnostic print
  var r = ee.Number(ee.Algorithms.If(
    n.gte(3),
    corrResult.get('correlation'),
    -9999
  ));

  var meanSim = pairs.aggregate_mean('sim');
  var meanObs = pairs.aggregate_mean('obs');
  var bias    = ee.Number(meanSim).subtract(meanObs);
  var pbias   = bias.divide(ee.Number(meanObs).add(1e-6)).multiply(100);

  // MAE
  var mae = pairs.map(function(f) {
    var d = ee.Number(f.get('sim')).subtract(ee.Number(f.get('obs'))).abs();
    return f.set('ae', d);
  }).aggregate_mean('ae');

  // RMSE
  var mse = pairs.map(function(f) {
    var d = ee.Number(f.get('sim')).subtract(ee.Number(f.get('obs')));
    return f.set('se', d.multiply(d));
  }).aggregate_mean('se');
  var rmse = ee.Number(mse).sqrt();

  // NSE
  var ssTot = pairs.map(function(f) {
    var d = ee.Number(f.get('obs')).subtract(ee.Number(meanObs));
    return f.set('d2', d.multiply(d));
  }).aggregate_sum('d2');
  var ssRes = pairs.map(function(f) {
    var d = ee.Number(f.get('sim')).subtract(ee.Number(f.get('obs')));
    return f.set('d2', d.multiply(d));
  }).aggregate_sum('d2');
  var nse = ee.Number(1).subtract(
    ee.Number(ssRes).divide(ee.Number(ssTot).add(1e-12)));

  // KGE
  var stdObs = pairs.map(function(f) {
    var d = ee.Number(f.get('obs')).subtract(ee.Number(meanObs));
    return f.set('d2', d.multiply(d));
  }).aggregate_mean('d2');
  var stdSim = pairs.map(function(f) {
    var d = ee.Number(f.get('sim')).subtract(ee.Number(meanSim));
    return f.set('d2', d.multiply(d));
  }).aggregate_mean('d2');
  var alpha = ee.Number(stdSim).sqrt()
               .divide(ee.Number(stdObs).sqrt().add(1e-12));
  var beta  = ee.Number(meanSim).divide(ee.Number(meanObs).add(1e-12));
  var kge   = ee.Number(1).subtract(
    r.subtract(1).pow(2)
     .add(alpha.subtract(1).pow(2))
     .add(beta.subtract(1).pow(2))
     .sqrt());

  return ee.Dictionary(ee.Algorithms.If(
    n.gte(3),
    ee.Dictionary({
      n        : n,
      r        : r,
      bias_mmd : bias,
      pbias_pct: pbias,
      mae_mmd  : mae,
      rmse_mmd : rmse,
      nse      : nse,
      kge      : kge,
    }),
    ee.Dictionary({
      n    : n,
      r    : -9999, bias_mmd : -9999, pbias_pct: -9999,
      mae_mmd: -9999, rmse_mmd: -9999, nse: -9999,
      kge  : -9999, note: 'insufficient_pairs (<3)',
    })
  ));
}

/**
 * Add a yr_mo string property to every image in an IC.
 * Used for inner-join matching across products.
 */
function tagYrMo(ic) {
  return ic.map(function(img) {
    var d = ee.Date(img.get('system:time_start'));
    var s = d.get('year').format('%04d')
             .cat('_').cat(d.get('month').format('%02d'));
    return img.set('yr_mo', s);
  });
}

/**
 * Tag IC with integer year and month properties.
 */
function tagYM(ic) {
  return ic.map(function(img) {
    var d = ee.Date(img.get('system:time_start'));
    return img.set('year', d.get('year')).set('month', d.get('month'));
  });
}

/**
 * Resample a single image to the common target grid.
 */
function toGrid(img) {
  return img.resample('bilinear')
            .reproject({crs:'EPSG:4326', scale: CFG.targetScale});
}

/**
 * Inner-join two ICs on yr_mo, then call a mapping function.
 * mapFn receives an ee.Feature with 'primary' and 'secondary' images.
 */
function joinOnYrMo(ic1, ic2, mapFn) {
  var j1 = tagYrMo(ic1);
  var j2 = tagYrMo(ic2);
  var joined = ee.Join.inner().apply({
    primary  : j1,
    secondary: j2,
    condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });
  return ee.ImageCollection(joined.map(mapFn));
}


// ════════════════════════════════════════════════════════════
// § 4  HARMONISATION HELPERS
// ════════════════════════════════════════════════════════════

// Standard: apply scaleFactor, mask negatives, rename
function harmoniseStd(img, key) {
  var p = PRODUCTS[key];
  var s = img.select([p.band])
             .multiply(p.scaleFactor)
             .rename('precip_mm_day');
  return s.toFloat().updateMask(s.gte(0))
          .copyProperties(img, ['system:time_start','system:time_end']);
}

// ERA5-Land monthly: stored as total monthly sum (metres)
// → mm/day = value × 1000 ÷ daysInMonth
function harmoniseERA5Mon(img) {
  var d   = ee.Date(img.get('system:time_start'));
  var dim = d.advance(1,'month').difference(d,'day');
  var s   = img.select(['total_precipitation_sum'])
               .multiply(ee.Image.constant(1000))
               .divide(ee.Image.constant(dim))
               .rename('precip_mm_day');
  return s.toFloat().updateMask(s.gte(0))
          .copyProperties(img, ['system:time_start','system:time_end']);
}

// TerraClimate: 'pr' is monthly accumulation in mm
// → mm/day = value ÷ daysInMonth
function harmoniseTerra(img) {
  var d   = ee.Date(img.get('system:time_start'));
  var dim = d.advance(1,'month').difference(d,'day');
  var s   = img.select(['pr'])
               .divide(ee.Image.constant(dim))
               .rename('precip_mm_day');
  return s.toFloat().updateMask(s.gte(0))
          .copyProperties(img, ['system:time_start','system:time_end']);
}

// MERRA2: raw collection is HOURLY (~175,000 images over 20 years).
// Aggregating hourly → daily here reduces it to ~7,300 images —
// same order as CHIRPS — so all downstream spatial operations
// (bias maps, seasonal means, correlations) stay within memory limits.
// Mean of 24 hourly kg/m²/s values × 86400 = mm/day (identical
// numerical result to applying scaleFactor image-by-image, but
// computed in a memory-efficient order).
function harmoniseMERRA2daily() {
  var raw = ee.ImageCollection('NASA/GSFC/MERRA/flx/2')
    .filterDate(CFG.startDate, CFG.endDate)
    .select('PRECTOTCORR');

  var nDays = ee.Date(CFG.endDate)
               .difference(ee.Date(CFG.startDate), 'day')
               .round();
  var days  = ee.List.sequence(0, nDays.subtract(1));

  return ee.ImageCollection(days.map(function(d) {
    var date     = ee.Date(CFG.startDate).advance(d, 'day');
    var dateNext = date.advance(1, 'day');
    var daily    = raw.filterDate(date, dateNext)
                      .mean()                   // mean of 24 hourly values
                      .multiply(86400)           // kg/m²/s → mm/day
                      .rename('precip_mm_day')
                      .toFloat();
    return daily.updateMask(daily.gte(0))
                .set('system:time_start', date.millis())
                .set('system:time_end',   dateNext.millis())
                .set('year',  date.get('year'))
                .set('month', date.get('month'));
  }));
}

// Dispatcher
function harmonise(img, key) {
  var fn = PRODUCTS[key].specialFn;
  if (fn === 'ERA5_MON') return harmoniseERA5Mon(img);
  if (fn === 'TERRA')    return harmoniseTerra(img);
  return harmoniseStd(img, key);
}

// Aggregate daily IC → monthly mean (memory-safe calendar filter)
function toMonthlyMean(ic) {
  var years  = ee.List.sequence(START_YR, END_YR);
  var months = ee.List.sequence(1, 12);
  var list   = years.map(function(yr) {
    return months.map(function(mo) {
      var s = ee.Date.fromYMD(yr, mo, 1);
      var e = s.advance(1, 'month');
      return ic.filterDate(s, e).mean()
               .set('system:time_start', s.millis())
               .set('year', yr).set('month', mo);
    });
  }).flatten();
  return ee.ImageCollection(list);
}

// ════════════════════════════════════════════════════════════
// § 5  GAUGE STATION DATA
// ════════════════════════════════════════════════════════════
//
//  ── HOW TO SWAP IN REAL DATA ────────────────────────────
//  Option A — Upload a CSV as a GEE Table Asset:
//    var STATION_FC = ee.FeatureCollection('users/you/wa_stations');
//    var OBS_FC     = ee.FeatureCollection('users/you/wa_obs');
//
//  Option B — Load from Google Drive after downloading GPCC .nc:
//    Process GPCC outside GEE → extract station values →
//    save as CSV → upload as GEE asset → load with Option A.
//
//  Required columns:
//    STATION_FC : station_id, lon, lat, station_name, elevation_m
//    OBS_FC     : station_id, year, month, obs_mm_day
// ──────────────────────────────────────────────────────────

var STATIONS_RAW = [
  {id:'WA001', name:'Dakar',        lon:-17.47, lat:14.73, elev:27},
  {id:'WA002', name:'Bamako',       lon:-7.95,  lat:12.65, elev:381},
  {id:'WA003', name:'Ouagadougou',  lon:-1.52,  lat:12.36, elev:306},
  {id:'WA004', name:'Niamey',       lon:2.17,   lat:13.51, elev:222},
  {id:'WA005', name:'Abuja',        lon:7.33,   lat:9.07,  elev:476},
  {id:'WA006', name:'Accra',        lon:-0.17,  lat:5.56,  elev:61},
  {id:'WA007', name:'Abidjan',      lon:-3.93,  lat:5.35,  elev:7},
  {id:'WA008', name:'Conakry',      lon:-13.67, lat:9.53,  elev:27},
  {id:'WA009', name:'Freetown',     lon:-13.23, lat:8.49,  elev:27},
  {id:'WA010', name:'Monrovia',     lon:-10.80, lat:6.30,  elev:23},
  {id:'WA011', name:'Lomé',         lon:1.22,   lat:6.13,  elev:25},
  {id:'WA012', name:'Cotonou',      lon:2.42,   lat:6.37,  elev:9},
  {id:'WA013', name:'Kano',         lon:8.52,   lat:12.05, elev:481},
  {id:'WA014', name:'Kumasi',       lon:-1.62,  lat:6.69,  elev:287},
  {id:'WA015', name:'Banjul',       lon:-16.68, lat:13.45, elev:28},
  {id:'WA016', name:'Nouakchott',   lon:-15.97, lat:18.07, elev:4},
];

var STATION_FC = ee.FeatureCollection(
  STATIONS_RAW.map(function(s) {
    return ee.Feature(ee.Geometry.Point([s.lon, s.lat]), {
      station_id: s.id, station_name: s.name,
      lon: s.lon, lat: s.lat, elevation_m: s.elev,
    });
  })
);

// ── Load real GPCC observations from uploaded asset ───────
var OBS_FC = ee.FeatureCollection(
  'projects/ee-desmond/assets/gpcc_obs_2001_2020'
).map(function(f) {
  return f.set({
    'year'      : ee.Number.parse(f.get('year')).toInt(),
    'month'     : ee.Number.parse(f.get('month')).toInt(),
    'obs_mm_day': ee.Number.parse(f.get('obs_mm_day')),
  });
});
print(' GPCC observations loaded:', OBS_FC.size(), 'records');

// ════════════════════════════════════════════════════════════
// § 6  LAZY IC BUILDER + CACHE
// ════════════════════════════════════════════════════════════
var IC_CACHE   = {};   // monthly ImageCollection cache
var MEAN_CACHE = {};   // long-term mean image cache

/**
 * Build (or return cached) harmonised monthly IC for a product.
 * Never called at startup — only when a button is clicked.
 */
function getIC(key) {
  if (IC_CACHE[key]) return IC_CACHE[key];

  var monthly;

  // MERRA2 is hourly (~175,000 images) — must pre-aggregate to daily
  // before any harmonisation or monthly mean step, otherwise every
  // spatial operation exceeds the interactive memory quota.
  // harmoniseMERRA2daily() returns ~7,300 daily images (same as CHIRPS).
  if (key === 'MERRA2') {
    monthly = toMonthlyMean(harmoniseMERRA2daily());

  } else {
    var p   = PRODUCTS[key];
    var raw = ee.ImageCollection(p.collection)
                .filterDate(CFG.startDate, CFG.endDate)
                .filterBounds(ROI)
                .select([p.band]);
    var harmonised = raw.map(function(img) { return harmonise(img, key); });
    monthly = p.isMonthly
      ? tagYM(harmonised)
      : toMonthlyMean(harmonised);
  }

  IC_CACHE[key] = monthly;
  return monthly;
}

/**
 * Long-term mean image (mm/day) — resampled, clipped.
 */
function getMean(key) {
  if (MEAN_CACHE[key]) return MEAN_CACHE[key];
  var m = toGrid(
    getIC(key).select('precip_mm_day').mean()
      .toFloat()
      .clip(ROI)
      .updateMask(ee.Image.constant(1).clip(ROI).mask())
  );
  MEAN_CACHE[key] = m;
  return m;
}


// ════════════════════════════════════════════════════════════
// § 7  ASSET EXPORT UTILITIES
//       Export intermediate results as GEE assets or Drive files.
//       Call these from the Export panel buttons or directly.
// ════════════════════════════════════════════════════════════

/**
 * Export long-term mean image to Google Drive (GeoTIFF).
 * @param {string} key   – product key
 */
function exportMeanToDrive(key) {
  Export.image.toDrive({
    image         : getMean(key).rename('precip_mm_day').toFloat(),
    description   : 'mean_' + key,
    folder        : CFG.exportFolder,
    fileNamePrefix: 'mean_' + key,
    region        : ROI, scale: CFG.targetScale,
    crs           : 'EPSG:4326', maxPixels: 1e13,
  });
  print('⬆ Export queued (Drive): mean_' + key);
}

/**
 * Export long-term mean image as a GEE Asset (for fast re-ingestion).
 * @param {string} key   – product key
 */
function exportMeanAsAsset(key) {
  Export.image.toAsset({
    image      : getMean(key).rename('precip_mm_day').toFloat(),
    description: 'asset_mean_' + key,
    assetId    : CFG.assetFolder + 'mean_' + key,
    region     : ROI, scale: CFG.targetScale,
    crs        : 'EPSG:4326', maxPixels: 1e13,
  });
  print('⬆ Export queued (Asset): ' + CFG.assetFolder + 'mean_' + key);
}

/**
 * Export monthly climatology (12-band image) as GEE asset.
 * Useful for sharing or reusing the pre-processed monthly stack.
 */
function exportClimatologyAsAsset(key) {
  var months = ee.List.sequence(1, 12);
  var clim   = ee.ImageCollection(months.map(function(m) {
    m = ee.Number(m).toInt();
    return getIC(key)
      .filter(ee.Filter.eq('month', m))
      .select('precip_mm_day').mean()
      .rename(ee.String('month_').cat(m.format()))
      .set('month', m);
  })).toBands().clip(ROI);

  Export.image.toAsset({
    image      : clim.toFloat(),
    description: 'asset_clim_' + key,
    assetId    : CFG.assetFolder + 'climatology_' + key,
    region     : ROI, scale: CFG.targetScale,
    crs        : 'EPSG:4326', maxPixels: 1e13,
  });
  print('⬆ Export queued (Asset): climatology_' + key);
}

/**
 * Export bias map (product vs reference) as GEE asset.
 */
function exportBiasAsAsset(key, ref) {
  var bias = getMean(key).subtract(getMean(ref)).rename('bias_mm_day');
  Export.image.toAsset({
    image      : bias.toFloat(),
    description: 'asset_bias_' + key + '_vs_' + ref,
    assetId    : CFG.assetFolder + 'bias_' + key + '_vs_' + ref,
    region     : ROI, scale: CFG.targetScale,
    crs        : 'EPSG:4326', maxPixels: 1e13,
  });
  print('⬆ Export queued (Asset): bias_' + key + '_vs_' + ref);
}


// ════════════════════════════════════════════════════════════
// § 8  ASSET INGEST UTILITIES
//       Re-load previously exported assets — instant, no recompute.
// ════════════════════════════════════════════════════════════

/**
 * Load a pre-exported mean image asset.
 * Returns null (with warning) if the asset doesn't exist yet.
 */
function loadMeanAsset(key) {
  var id = CFG.assetFolder + 'mean_' + key;
  try {
    return ee.Image(id);
  } catch(e) {
    print('⚠ Asset not found: ' + id +
          '  →  Run exportMeanAsAsset("' + key + '") first.');
    return null;
  }
}

/**
 * Load a pre-exported climatology asset (12-band image).
 */
function loadClimatologyAsset(key) {
  var id = CFG.assetFolder + 'climatology_' + key;
  try {
    return ee.Image(id);
  } catch(e) {
    print('⚠ Asset not found: ' + id);
    return null;
  }
}

/**
 * getMean() with asset fallback:
 *   1. If a pre-exported asset exists → use it (fast)
 *   2. Otherwise compute on-the-fly (slow)
 */
function getMeanWithFallback(key) {
  var id  = CFG.assetFolder + 'mean_' + key;
  var img = ee.Image(id);
  // Check existence via getInfo would block; instead return the
  // ee.Image directly — GEE will fail gracefully on the layer if absent
  return img.rename('precip_mm_day').unmask(getMean(key));
}


// ════════════════════════════════════════════════════════════
// § 9  VIS PARAMS
// ════════════════════════════════════════════════════════════

var VIS = {
  annual  : {min:0,    max:2500,  palette:['#FFFDE7','#FFF59D','#FFCC02',
                                           '#FF8F00','#E65100']},
  daily   : {min:0,    max:12,    palette:['#E3F2FD','#90CAF9','#1565C0',
                                           '#0D47A1','#01002E']},
  bias    : {min:-5,   max:5,     palette:['#B71C1C','#EF9A9A','#FFFFFF',
                                           '#90CAF9','#0D47A1']},
  pbias   : {min:-80,  max:80,    palette:['#B71C1C','#FFCDD2','#FFFFFF',
                                           '#BBDEFB','#0D47A1']},
  corr    : {min:0,    max:1,     palette:['#FFFFFF','#C8E6C9','#66BB6A',
                                           '#2E7D32','#1B5E20']},
  trend   : {min:-0.05,max:0.05,  palette:['#4E342E','#FF8A65','#FFFFFF',
                                           '#80DEEA','#006064']},
  pod     : {min:0,    max:1,     palette:['#FFF8E1','#FFE082','#FFB300',
                                           '#FF6F00']},
  far     : {min:0,    max:1,     palette:['#E8F5E9','#A5D6A7','#388E3C',
                                           '#1B5E20']},
};


// ════════════════════════════════════════════════════════════
// § 10  UI — STYLES & HELPERS
// ════════════════════════════════════════════════════════════

// Colour tokens
var C = {
  bg        : '#0D1B2A',   // panel background (very dark navy)
  bgSection : '#162032',   // section card background
  border    : '#1E3A5F',   // card border
  textH     : '#FFFFFF',   // heading white
  textSub   : '#90CAF9',   // sub-label light blue
  textMuted : '#546E7A',   // muted grey-blue
  accent    : '#1565C0',   // button default (dark blue)
  accentGrn : '#1B5E20',   // bias / export (dark green)
  accentPurp: '#4A148C',   // correlation
  accentOrng: '#E65100',   // trend / seasonal
  accentTeal: '#006064',   // charts
  accentRed : '#B71C1C',   // categorical
  accentGold: '#F57F17',   // station validation
  btnText   : '#FFFFFF',
};

// Shared button style generator
function btnStyle(bg) {
  return {
    stretch         : 'horizontal',
    margin          : '3px 0 3px 0',
    backgroundColor : bg,
    color           : C.btnText,
    fontWeight      : 'bold',
    fontSize        : '11px',
    padding         : '4px',
    border          : '1px solid rgba(255,255,255,0.15)',
  };
}

// Section card wrapper
function card(widgets, bgOverride) {
  return ui.Panel({
    widgets: widgets,
    style  : {
      margin         : '6px 0 4px 0',
      padding        : '8px',
      backgroundColor: bgOverride || C.bgSection,
      border         : '1px solid ' + C.border,
    },
  });
}

// Section heading
function heading(text, color) {
  return ui.Label(text, {
    fontWeight:'bold', fontSize:'12px',
    color: color || C.textH, margin:'0 0 5px 0',
  });
}

// Sub-label
function subLabel(text) {
  return ui.Label(text, {
    fontSize:'10px', color: C.textSub, margin:'0 0 3px 0',
  });
}

// Thin divider
function hr() {
  return ui.Label('', {
    border:'0.5px solid ' + C.border,
    margin:'6px 0', padding:'0', stretch:'horizontal',
  });
}

// GEE ui.Select ignores backgroundColor/color CSS on the native dropdown.
// Wrap each select in a white-background Panel with a coloured border so
// the widget is always clearly visible regardless of theme.
function styledSelect(items, value) {
  return ui.Select({
    items : items,
    value : value,
    style : { stretch:'horizontal', fontSize:'12px' },
  });
}

// Wrap a select in a visible labelled frame
function selectRow(labelTxt, selectWidget) {
  return ui.Panel({
    widgets: [
      ui.Label(labelTxt, {
        fontSize:'10px', fontWeight:'bold',
        color:'#e61c36',
        margin:'4px 0 2px 0',
        backgroundColor:'#f0f0f0',
      }),
      ui.Panel({
        widgets: [selectWidget],
        style  : {
          backgroundColor: '#FFFFFF',
          border         : '2px solid #42A5F5',
          padding        : '2px',
          stretch        : 'horizontal',
        },
      }),
    ],
    style: {margin:'0 0 6px 0', backgroundColor:'#f0f0f0'},
  });
}

// Status label (shared across all sections)
var STATUS = ui.Label('Ready — select a product and click a button.', {
  fontSize:'11px',
  color          : '#e61c36',    // bright yellow — readable on any bg
  fontWeight     : 'bold',
  whiteSpace     : 'pre',
  margin         : '4px 0 2px 0',
  backgroundColor: '#f0f0f0',
});
function setStatus(msg) { STATUS.setValue('⟳ ' + msg); }
function setDone(msg)   { STATUS.setValue('✓ ' + msg); }
function setError(msg)  { STATUS.setValue('✗ ' + msg); }

// Colour bar legend
function makeLegend(title, palette, lo, hi, unit) {
  return ui.Panel({
    widgets: [
      ui.Label(title, {fontSize:'10px', color:C.textH,
                        fontWeight:'bold', margin:'0 0 2px 0'}),
      ui.Thumbnail({
        image : ee.Image.pixelLonLat().select(0),
        params: {bbox:[0,0,1,0.1], dimensions:'170x12',
                 format:'png', min:0, max:1, palette:palette},
        style : {stretch:'horizontal', margin:'0 0 2px 0'},
      }),
      ui.Panel({
        widgets:[
          ui.Label(lo+' '+unit,
            {fontSize:'9px', color:C.textSub, margin:'0'}),
          ui.Label(hi+' '+unit,
            {fontSize:'9px', color:C.textSub,
             margin:'0', textAlign:'right'}),
        ],
        layout:ui.Panel.Layout.flow('horizontal'),
        style :{stretch:'horizontal'},
      }),
    ],
    style:{margin:'0 0 5px 0', backgroundColor:'#f0f0f0'},
  });
}


// ════════════════════════════════════════════════════════════
// § 11  UI — PANEL LAYOUT
// ════════════════════════════════════════════════════════════

// ── Panel ──────────────────────────────────────────────────
var panel = ui.Panel({
  style:{
    width:'280px',
    padding:'10px',
    backgroundColor:'#F5F5F5'
  }
});

// ── Clean card helper ──────────────────────────────────────
function card(widgets){
  return ui.Panel({
    widgets:widgets,
    style:{
      margin:'6px 0',
      padding:'8px',
      backgroundColor:'#FFFFFF',
      border:'1px solid #D0D0D0'
    }
  });
}

// ── Clean button style ─────────────────────────────────────
function btnStyle(color){
  return {
    stretch:'horizontal',
    margin:'4px 0',
    padding:'6px',
    backgroundColor:'#E0E0E0',
    color:'#000000',
    border:'1px solid #BDBDBD',
    fontWeight:'bold',
    textAlign:'center'
  };
}

// ── Header card ──────────────────────────────────────────
panel.add(card([
  ui.Label('🌧  West Africa', {
    fontWeight:'bold',
    fontSize:'16px',
    color:'#1565C0',
    margin:'0'
  }),
  ui.Label('Precipitation Assessment', {
    fontWeight:'bold',
    fontSize:'12px',
    color:'#424242',
    margin:'2px 0 0 0'
  }),
  ui.Label(CFG.startDate + ' – ' + CFG.endDate, {
    fontSize:'10px',
    color:'#757575',
    margin:'2px 0 0 0'
  })
]));

// ── Selector card ────────────────────────────────────────
var prodSel = styledSelect(PKEYS, CFG.defaultProd);
var refSel  = styledSelect(PKEYS, CFG.defaultRef);

panel.add(card([
  selectRow('📡  PRODUCT  (select to analyse)',prodSel),
  selectRow('📐  REFERENCE  (for bias & correlation)', refSel)
]));

// ── Zone selector ─────────────────────────────────────────
var zoneSel = styledSelect(ECO_ZONE_NAMES, 'All West Africa');

panel.add(card([
  ui.Label('🌿  ECOLOGICAL ZONE', {
    fontSize:'10px', fontWeight:'bold', color:'#2e7d32', margin:'4px 0 2px 0',
  }),
  zoneSel,
  ui.Label('Restricts maps & charts to selected zone', {
    fontSize:'9px', color:'#757575', margin:'2px 0 0 0',
  }),
]));

// ── Status card ──────────────────────────────────────────
var selReadout = ui.Label('Product: CHIRPS  |  Ref: GPM_IMERG', {
  fontSize:'10px',
  color:'#000000',
  fontWeight:'bold',
  margin:'0 0 4px 0'
});

prodSel.onChange(function(v){
  selReadout.setValue('Product: '+v+'  |  Ref: '+refSel.getValue());
});

refSel.onChange(function(v){
  selReadout.setValue('Product: '+prodSel.getValue()+'  |  Ref: '+v);
});

panel.add(card([selReadout, STATUS]));

// ── Spatial Layers card ──────────────────────────────────
panel.add(card([
  heading('  Spatial Layers', '#1565C0'),

  ui.Button({label:'Annual Total Map', style:btnStyle(), onClick:runAnnualTotal}),
  ui.Button({label:'Mean Daily Rate Map', style:btnStyle(), onClick:runDailyMean}),
  ui.Button({label:'Bias Map (vs Ref)', style:btnStyle(), onClick:runBias}),
  ui.Button({label:'Correlation Map (vs Ref)', style:btnStyle(), onClick:runCorrelation}),
  ui.Button({label:'Trend Map', style:btnStyle(), onClick:runTrend})
]));

// ── Zonal Analysis card ─────────────────────────────────
panel.add(card([
  heading('🌿  Zonal Analysis', '#2e7d32'),
  ui.Button({label:'Show Zone Boundaries',             style:btnStyle(), onClick:showZoneBoundaries}),
  ui.Button({label:'Zonal Mean (all zones)',           style:btnStyle(), onClick:runZonalMean}),
  ui.Button({label:'Zonal Bias (all zones)',           style:btnStyle(), onClick:runZonalBias}),
  ui.Button({label:'Zonal Annual Cycle',               style:btnStyle(), onClick:runZonalAnnualCycle}),
  ui.Button({label:'Annual Cycle — All Products × Zones', style:btnStyle(), onClick:runZonalAnnualCycleAllProducts}),
  ui.Button({label:'Full Metric Matrix (~5 min)',      style:btnStyle(), onClick:runZonalMetricMatrix}),
  ui.Button({label:'Product Ranking by Zone (~5 min)', style:btnStyle(), onClick:runZonalProductRanking}),
  ui.Button({label:'Threshold Sensitivity',            style:btnStyle(), onClick:runThresholdSensitivity}),
  ui.Button({label:'Inter-product Agreement Map',      style:btnStyle(), onClick:runInterProductAgreement}),
]));

// ── Seasonal card ────────────────────────────────────────
var seasonSel = styledSelect(['DJF','MAM','JJA','SON'], 'JJA');

panel.add(card([
  heading('🗓  Seasonal Mean', '#1565C0'),
  selectRow('Season', seasonSel),
  ui.Button({
    label:'Add Seasonal Mean Map',
    style:btnStyle(),
    onClick:runSeasonal
  })
]));

// ── Charts card ──────────────────────────────────────────
panel.add(card([
  heading('📉  Charts', '#1565C0'),

  ui.Button({label:'Time Series — All Products', style:btnStyle(), onClick:runTimeSeriesAll}),
  ui.Button({label:'Time Series — Selected Product', style:btnStyle(), onClick:runTimeSeriesSingle}),
  ui.Button({label:'Annual Cycle Chart', style:btnStyle(), onClick:runAnnualCycle})
]));

// ── Station Validation card ──────────────────────────────
var stationItems = STATIONS_RAW.map(function(s){
  return s.id+' – '+s.name;
});

var stnSel = styledSelect(stationItems, stationItems[0]);

panel.add(card([
  heading('📍  Station Validation', '#1565C0'),
  selectRow('Station', stnSel),

  ui.Button({
    label:'Validate Station vs Product',
    style:btnStyle(),
    onClick:runStationValidation
  }),

  ui.Button({
    label:'Categorical Metrics (POD / FAR / CSI)',
    style:btnStyle(),
    onClick:runCategorical
  })
]));

// ── Export card ──────────────────────────────────────────
panel.add(card([
  heading('⬆  Export / Assets', '#1565C0'),

  ui.Button({
    label:'Export Mean → Drive',
    style:btnStyle(),
    onClick:function(){
      exportMeanToDrive(prodSel.getValue());
      setDone('Queued: mean → Drive');
    }
  }),

  ui.Button({
    label:'Export Mean → GEE Asset',
    style:btnStyle(),
    onClick:function(){
      exportMeanAsAsset(prodSel.getValue());
      setDone('Queued: mean → Asset');
    }
  }),

  ui.Button({
    label:'Export Climatology → GEE Asset',
    style:btnStyle(),
    onClick:function(){
      exportClimatologyAsAsset(prodSel.getValue());
      setDone('Queued: climatology → Asset');
    }
  }),

  ui.Button({
    label:'Export Bias Map → GEE Asset',
    style:btnStyle(),
    onClick:function(){
      exportBiasAsAsset(prodSel.getValue(), refSel.getValue());
      setDone('Queued: bias → Asset');
    }
  }),

  subLabel('Monitor progress in the Tasks tab ↑')
]));

// ── Legend card ──────────────────────────────────────────
panel.add(card([
  heading('🎨  Legend', '#1565C0'),

  makeLegend('Annual Total', VIS.annual.palette, 0, 2500, 'mm/yr'),
  makeLegend('Mean Daily', VIS.daily.palette, 0, 12, 'mm/day'),
  makeLegend('Bias', VIS.bias.palette, -5, 5, 'mm/day'),
  makeLegend('Correlation', VIS.corr.palette, 0, 1, 'r'),
  makeLegend('Trend', VIS.trend.palette, -0.05, 0.05, 'mm/d/yr')
]));

// ── Product key card ─────────────────────────────────────
var keyWidgets = [heading('Products', '#1565C0')];

PKEYS.forEach(function(k){
  var p = PRODUCTS[k];

  keyWidgets.push(
    ui.Panel({
      widgets:[
        ui.Label('■',{color:p.color,fontSize:'14px',margin:'0 5px 0 0'}),
        ui.Label(k+'  '+p.res,{
          color:'#424242',
          fontSize:'10px',
          margin:'1px 0'
        })
      ],
      layout:ui.Panel.Layout.flow('horizontal'),
      style:{margin:'1px 0'}
    })
  );
});

panel.add(card(keyWidgets));

// ── Inspector ────────────────────────────────────────────
var inspectOut = ui.Label('👆 Click map to sample pixel', {
  fontSize:'10px',
  color:'#424242',
  whiteSpace:'pre'
});

panel.add(card([
  heading('🔍  Inspector', '#1565C0'),
  inspectOut
]));

ui.root.add(panel);


// ════════════════════════════════════════════════════════════
// § 12  ACTION: CLIMATOLOGY MAPS
// ════════════════════════════════════════════════════════════

function runAnnualTotal() {
  var key    = prodSel.getValue();
  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  setStatus('Annual total: ' + key);
  Map.addLayer(getMean(key).multiply(365.25).clip(region), VIS.annual,
    '🌧 Annual Total – ' + key + ' [' + zone + '] (mm/yr)');
  setDone('Annual total added: ' + key + ' [' + zone + ']');
}

function runDailyMean() {
  var key    = prodSel.getValue();
  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  setStatus('Daily mean: ' + key);
  Map.addLayer(getMean(key).clip(region), VIS.daily,
    '📅 Daily Mean – ' + key + ' [' + zone + '] (mm/d)');
  setDone('Daily mean added: ' + key + ' [' + zone + ']');
}


// ════════════════════════════════════════════════════════════
// § 13  ACTION: BIAS MAPS
// ════════════════════════════════════════════════════════════

function runBias() {
  var key = prodSel.getValue();
  var ref = refSel.getValue();
  if (key === ref) { setError('Product = Reference — choose different.'); return; }
  setStatus('Bias: ' + key + ' vs ' + ref);
  var prodM = getMean(key).clip(ROI);
  var refM  = getMean(ref).clip(ROI);
  var bias  = prodM.subtract(refM).rename('bias_mm_day').clip(ROI);
  var pbias = prodM.subtract(refM).divide(refM.add(1e-6))
                .multiply(100).rename('pbias_pct').clip(ROI);
  // Clamp pbias to ±150% so edge/ocean pixels don't wash out the palette
  var pbiasC = pbias.clamp(-80,80).rename('pbias_pct').clip(ROI);
  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  Map.addLayer(bias.clip(region),   VIS.bias,  '⚖ Bias – '  + key + ' vs ' + ref + ' [' + zone + '] (mm/d)');
  Map.addLayer(pbiasC.clip(region), VIS.pbias, '% Bias – ' + key + ' vs ' + ref + ' [' + zone + '] (%)');
  setDone('Bias maps added: ' + key + ' vs ' + ref + ' [' + zone + ']');
}


// ════════════════════════════════════════════════════════════
// § 14  ACTION: CORRELATION MAP
// ════════════════════════════════════════════════════════════

function runCorrelation() {
  var key = prodSel.getValue();
  var ref = refSel.getValue();
  if (key === ref) { setError('Product = Reference.'); return; }
  setStatus('Correlation: ' + key + ' vs ' + ref + '\n(~30-60s)');

  var prodIC = tagYrMo(getIC(key).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('prod'); }));
  var refIC  = tagYrMo(getIC(ref).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('ref'); }));

  var joined = ee.Join.inner().apply({
    primary  : prodIC, secondary: refIC,
    condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });
  var corr = ee.ImageCollection(joined.map(function(f) {
    return ee.Image(f.get('primary')).addBands(ee.Image(f.get('secondary')));
  })).select(['prod','ref']).reduce(ee.Reducer.pearsonsCorrelation())
    .select('correlation').clip(ROI);

  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  Map.addLayer(corr.clip(region), VIS.corr, '🔗 r – ' + key + ' vs ' + ref + ' [' + zone + ']');
  setDone('Correlation map added [' + zone + '].');
}


// ════════════════════════════════════════════════════════════
// § 15  ACTION: TREND MAP
// ════════════════════════════════════════════════════════════

function runTrend() {
  var key = prodSel.getValue();
  setStatus('Trend: ' + key + '\n(~30-60s)');
  var t0      = ee.Date(CFG.startDate).millis();
  var msPerYr = 1000 * 60 * 60 * 24 * 365.25;
  var withT   = getIC(key).select('precip_mm_day').map(function(img) {
    var t = ee.Number(img.get('system:time_start'))
               .subtract(t0).divide(msPerYr).float();
    return toGrid(img.clip(ROI)).float()
             .addBands(ee.Image.constant(t).rename('time').float());
  });
  var trend = withT.select(['time','precip_mm_day'])
    .reduce(ee.Reducer.linearFit()).select('scale')
    .rename('trend').clip(ROI);
  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  Map.addLayer(trend.clip(region), VIS.trend, '📈 Trend – ' + key + ' [' + zone + '] (mm/d/yr)');
  setDone('Trend map added: ' + key + ' [' + zone + ']');
}


// ════════════════════════════════════════════════════════════
// § 16  ACTION: SEASONAL MAPS
// ════════════════════════════════════════════════════════════

function runSeasonal() {
  var key    = prodSel.getValue();
  var season = seasonSel.getValue();
  var zone   = zoneSel.getValue();
  var region = getAnalysisRegion();
  var moMap  = {DJF:[12,1,2], MAM:[3,4,5], JJA:[6,7,8], SON:[9,10,11]};
  setStatus('Seasonal mean: ' + season + ' / ' + key + ' [' + zone + ']');
  var ic   = tagYM(getIC(key));
  var mean = toGrid(
    ic.filter(ee.Filter.inList('month', moMap[season]))
      .select('precip_mm_day').mean().clip(region)
  );
  Map.addLayer(mean, VIS.daily, '🗓 ' + season + ' – ' + key + ' [' + zone + '] (mm/d)');
  setDone(season + ' mean added: ' + key + ' [' + zone + ']');
}


// ════════════════════════════════════════════════════════════
// § 17  ACTION: TIME-SERIES CHARTS
// ════════════════════════════════════════════════════════════

function runTimeSeriesAll() {
  var zone   = zoneSel.getValue();
  var region = getAnalysisRegion();
  setStatus('Building time-series chart\n(all products, ~60s)');
  var keys   = PKEYS;
  var colors = keys.map(function(k){ return PRODUCTS[k].color; });

  // Stack all products into one IC using the first product as base
  // then add each additional product as a band matched by yr_mo
  // This avoids combine() timestamp issues and nested reduceRegion OOM
  var base = tagYrMo(getIC(keys[0]).select('precip_mm_day'))
    .map(function(img){ return img.rename(keys[0]); });

  var stacked = keys.slice(1).reduce(function(baseIC, key) {
    var other = tagYrMo(getIC(key).select('precip_mm_day'))
      .map(function(img){ return img.rename(key); });
    var joined = ee.Join.inner().apply({
      primary  : baseIC,
      secondary: other,
      condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
    });
    return ee.ImageCollection(joined.map(function(f) {
      return ee.Image(f.get('primary'))
               .addBands(ee.Image(f.get('secondary')))
               .copyProperties(ee.Image(f.get('primary')),
                 ['system:time_start','yr_mo']);
    }));
  }, base);

  print(ui.Chart.image.series({
    imageCollection: stacked,
    region         : region,
    reducer        : ee.Reducer.mean(),
    scale          : CFG.chartScale,
    xProperty      : 'system:time_start',
  }).setSeriesNames(keys).setChartType('LineChart').setOptions({
    title    : 'Monthly Precipitation – ' + zone + ' (All Products)',
    vAxis    : {title:'mm/day'},
    hAxis    : {title:'Date', format:'MMM yyyy'},
    lineWidth: 1.5, pointSize:0, colors: colors,
    legend   : {position:'right'}, height:380,
    backgroundColor: '#FAFAFA',
  }));
  setDone('Time-series chart printed: ' + zone);
}

function runTimeSeriesSingle() {
  var key    = prodSel.getValue();
  var zone   = zoneSel.getValue();
  var region = getAnalysisRegion();
  setStatus('Time-series: ' + key + ' [' + zone + ']');
  print(ui.Chart.image.series({
    imageCollection: getIC(key).select('precip_mm_day'),
    region: region, reducer: ee.Reducer.mean(),
    scale: CFG.chartScale, xProperty: 'system:time_start',
  }).setSeriesNames([key]).setChartType('LineChart').setOptions({
    title    : 'Monthly Mean – ' + key + ' [' + zone + ']',
    vAxis    : {title:'mm/day'},
    hAxis    : {title:'Date', format:'MMM yyyy'},
    lineWidth: 1.5, pointSize:0,
    colors   : [PRODUCTS[key].color],
    legend   : {position:'none'}, height:350,
    backgroundColor: '#FAFAFA',
  }));
  setDone('Time-series printed: ' + key + ' [' + zone + ']');
}
// ════════════════════════════════════════════════════════════
// § 18  ACTION: ANNUAL CYCLE CHART
// ════════════════════════════════════════════════════════════

// ── Edit this list to include / exclude countries ──────────
var ANNUAL_CYCLE_COUNTRIES = null;

function getChartRegion() {
  if (!ANNUAL_CYCLE_COUNTRIES || ANNUAL_CYCLE_COUNTRIES.length === 0) {
    return ee.Geometry.Rectangle([-0.5, 5.4, 0.5, 6.4]);
  }
  var countries = ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
    .filter(ee.Filter.inList('country_na', ANNUAL_CYCLE_COUNTRIES));
  return countries.geometry().dissolve({maxError: 1000});
}

function runAnnualCycle() {
  var zone = zoneSel.getValue();
  var chartRegion = (zone && zone !== 'All West Africa')
    ? getAnalysisRegion()
    : getChartRegion();
  var regionLabel = (zone && zone !== 'All West Africa')
    ? zone + ' zone'
    : (ANNUAL_CYCLE_COUNTRIES && ANNUAL_CYCLE_COUNTRIES.length > 0)
      ? ANNUAL_CYCLE_COUNTRIES.join(', ')
      : 'West Africa (full region)';

  setStatus('Annual cycle chart\n(~30-60s …)');
  var colors = PKEYS.map(function(k){ return PRODUCTS[k].color; });
  var TICKS  = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];

  var fc = ee.FeatureCollection(
    ee.List.sequence(1, 12).map(function(mo) {
      mo = ee.Number(mo).toInt();
      var firstBand = getIC(PKEYS[0])
        .filter(ee.Filter.calendarRange(mo, mo, 'month'))
        .select('precip_mm_day').mean().rename(PKEYS[0]);
      var img = PKEYS.slice(1).reduce(function(acc, key) {
        var band = getIC(key)
          .filter(ee.Filter.calendarRange(mo, mo, 'month'))
          .select('precip_mm_day').mean().rename(key);
        return ee.Image(acc).addBands(band);
      }, firstBand);
      var vals = ee.Image(img).reduceRegion({
        reducer  : ee.Reducer.mean(),
        geometry : chartRegion,
        scale    : 100000,
        maxPixels: 1e9,
        tileScale: 8,
      });
      return ee.Feature(null, vals.set('month', mo));
    })
  );

  print(ui.Chart.feature.byFeature({
    features   : fc,
    xProperty  : 'month',
    yProperties: PKEYS,
  }).setChartType('LineChart').setOptions({
    title      : 'Mean Annual Cycle – ' + regionLabel,
    vAxis      : {title:'Precipitation (mm/day)'},
    hAxis      : {title:'Month', ticks:TICKS},
    lineWidth  : 2, pointSize:5, colors:colors,
    legend     : {position:'right'}, height:380,
    backgroundColor: '#FAFAFA',
  }));
  setDone('Annual cycle chart printed: ' + regionLabel);
}


// ════════════════════════════════════════════════════════════
// § 19  ACTION: STATION VALIDATION
// ════════════════════════════════════════════════════════════

function runStationValidation() {
  var key    = prodSel.getValue();
  var selStr = stnSel.getValue();
  var sId    = selStr.split(' – ')[0];
  var sObj   = null;
  STATIONS_RAW.forEach(function(s){ if(s.id === sId) sObj = s; });
  if (!sObj) { setError('Station not found.'); return; }

  setStatus('Validating ' + sObj.name + '\nvs ' + key + ' …');
  var pt  = ee.Geometry.Point([sObj.lon, sObj.lat]);
  var ic  = tagYM(getIC(key)).select('precip_mm_day');

  var sampled = ic.map(function(img) {
    var val = img.reduceRegion({
      reducer:ee.Reducer.first(), geometry:pt, scale:CFG.targetScale,
    }).get('precip_mm_day');
    return ee.Feature(null, {
      station_id:sId, product:key,
      year:img.get('year'), month:img.get('month'), sim:val,
    });
  });

  var stObs  = OBS_FC.filter(ee.Filter.eq('station_id', sId));
  var joined = ee.Join.inner().apply({
    primary  : sampled, secondary: stObs,
    condition: ee.Filter.and(
      ee.Filter.equals({leftField:'year',  rightField:'year'}),
      ee.Filter.equals({leftField:'month', rightField:'month'})
    ),
  });

  var pairs = joined.map(function(feat) {
    var sim = ee.Number(ee.Feature(feat.get('primary')).get('sim'));
    var obs = ee.Number(ee.Feature(feat.get('secondary')).get('obs_mm_day'));
    return ee.Feature(null, {sim:sim, obs:obs});
  });

  var validPairs = pairs.filter(ee.Filter.notNull(['sim', 'obs']));
  var metrics    = computeMetrics(validPairs);
  print('📐 Metrics – ' + sObj.name + ' / ' + key + ':', metrics);

  print(ui.Chart.feature.byFeature({
    features:validPairs, xProperty:'obs', yProperties:['sim'],
  }).setChartType('ScatterChart').setOptions({
    title    : 'Obs vs ' + key + '  |  ' + sObj.name,
    hAxis    : {title:'Observed (mm/day)', minValue:0},
    vAxis    : {title:key + ' (mm/day)',   minValue:0},
    pointSize: 3, colors:[PRODUCTS[key].color],
    trendlines: {0:{type:'linear', color:'#FF0000', lineWidth:1}},
    height   : 380, backgroundColor:'#FAFAFA',
  }));
  setDone('Validation done: ' + sObj.name + ' / ' + key +
          '\n(metrics in Console)');
}


// ════════════════════════════════════════════════════════════
// § 20  ACTION: CATEGORICAL METRICS
// ════════════════════════════════════════════════════════════

function runCategorical() {
  var key = prodSel.getValue();
  var ref = refSel.getValue();
  if (key === ref) { setError('Product = Reference.'); return; }

  var region = getAnalysisRegion();
  var zone   = zoneSel.getValue();
  setStatus('Categorical metrics:\n' + key + ' vs ' + ref + ' [' + zone + ']\n(~30-60s)');

  var prodIC = tagYrMo(tagYM(getIC(key)).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(region)).rename('prod'); }));
  var refIC  = tagYrMo(tagYM(getIC(ref)).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(region)).rename('ref'); }));

  var joined = ee.Join.inner().apply({
    primary  : prodIC, secondary: refIC,
    condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });

  var cont = ee.ImageCollection(joined.map(function(feat) {
    var p  = ee.Image(feat.get('primary'));
    var r  = ee.Image(feat.get('secondary'));
    var pR = p.gte(CFG.rainThresh);
    var rR = r.gte(CFG.rainThresh);
    return pR.and(rR)                .rename('hits')
      .addBands(rR.and(pR.not())     .rename('misses'))
      .addBands(pR.and(rR.not())     .rename('false_al'))
      .addBands(pR.not().and(rR.not()).rename('cn'));
  })).sum().clip(region);

  var tot = cont.reduceRegion({
    reducer:ee.Reducer.sum(), geometry:region,
    scale:CFG.chartScale, maxPixels:1e12,
  });
  var H  = ee.Number(tot.get('hits'));
  var M  = ee.Number(tot.get('misses'));
  var FA = ee.Number(tot.get('false_al'));
  var CN = ee.Number(tot.get('cn'));
  var N  = H.add(M).add(FA).add(CN);

  print('🎯 Categorical – ' + key + ' vs ' + ref + ' [' + zone + ']:',
    ee.Dictionary({
      POD      : H.divide(H.add(M)),
      FAR      : FA.divide(H.add(FA)),
      CSI      : H.divide(H.add(M).add(FA)),
      ETS      : H.subtract(H.add(M).multiply(H.add(FA)).divide(N))
                  .divide(H.add(M).add(FA)
                    .subtract(H.add(M).multiply(H.add(FA)).divide(N))),
      FREQ_BIAS: H.add(FA).divide(H.add(M)),
      hits:H, misses:M, false_al:FA, correct_neg:CN,
    }));

  Map.addLayer(
    cont.select('hits').divide(cont.select('hits').add(cont.select('misses'))),
    VIS.pod, '🎯 POD – ' + key + ' vs ' + ref + ' [' + zone + ']');
  Map.addLayer(
    cont.select('false_al').divide(
      cont.select('hits').add(cont.select('false_al'))),
    VIS.far, '⚠ FAR – ' + key + ' vs ' + ref + ' [' + zone + ']');

  setDone('Categorical metrics printed & maps added [' + zone + '].');
}

// ════════════════════════════════════════════════════════════
// § 20b  ZONAL ANALYSIS FUNCTIONS
// ════════════════════════════════════════════════════════════

// ── 1. Show zone boundaries on map ───────────────────────────────────────
function showZoneBoundaries() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  ECO_ZONE_DEFS.forEach(function(z) {
    var zone = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name));
    Map.addLayer(zone.style({fillColor: z.color + '44', color:'00000000'}),
      {}, '🌿 ' + z.name + ' (' + z.rainfall + ')', true);
  });
  // Map.addLayer(ECO_ZONES.style({fillColor:'00000000', color:'333333', width:1.5}),
  //   {}, '🌿 Zone boundaries', true);
  // setDone('Zone boundaries added to map.');
}

// ── 2. Zonal mean mm/day for selected product ─────────────────────────────
function runZonalMean() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var key = prodSel.getValue();
  setStatus('Zonal mean: ' + key + ' (~30s)');
  var mean = getMean(key);
  var zoneStats = mean.reduceRegions({
    collection: ECO_ZONES, reducer: ee.Reducer.mean(), scale: CFG.chartScale,
  });
  print(' Zonal mean (mm/day) — ' + key + ':', zoneStats.select(['zone_name','mean']));
  ECO_ZONE_DEFS.forEach(function(z) {
    var geom = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name)).geometry();
    Map.addLayer(mean.clip(geom), VIS.daily, '🌿 ' + z.name + ' — ' + key, true);
  });
  // Map.addLayer(ECO_ZONES.style({fillColor:'00000000', color:'333333', width:1.5}),
  //   {}, '🌿 Zone boundaries', true);
  // setDone('Zonal mean printed — ' + key);
}

// ── 3. Zonal bias per zone (product vs reference) ─────────────────────────
function runZonalBias() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var key = prodSel.getValue();
  var ref = refSel.getValue();
  if (key === ref) { setError('Product = Reference.'); return; }
  setStatus('Zonal bias: ' + key + ' vs ' + ref + ' (~30s)');
  var bias  = getMean(key).subtract(getMean(ref)).rename('bias_mm_day');
  var pbias = getMean(key).subtract(getMean(ref))
                .divide(getMean(ref).add(1e-6)).multiply(100).rename('pbias_pct');
  var zoneStats = bias.addBands(pbias).reduceRegions({
    collection: ECO_ZONES, reducer: ee.Reducer.mean(), scale: CFG.chartScale,
  });
  print(' Zonal bias — ' + key + ' vs ' + ref + ':',
    zoneStats.select(['zone_name','bias_mm_day','pbias_pct']));
  Map.addLayer(bias.clip(ROI), VIS.bias, '⚖ Bias – ' + key + ' vs ' + ref + ' (mm/d)');
  // Map.addLayer(ECO_ZONES.style({fillColor:'00000000', color:'333333', width:1.5}),
  //   {}, '🌿 Zone boundaries', true);
  // setDone('Zonal bias printed — ' + key + ' vs ' + ref);
}

// ── 4. Zonal annual cycle — selected product, one line per zone ───────────
function runZonalAnnualCycle() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var key = prodSel.getValue();
  setStatus('Zonal annual cycle: ' + key + ' (~60s)');
  var TICKS = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];
  var zoneColors = ECO_ZONE_DEFS.map(function(z){ return z.color; });
  var zoneNames  = ECO_ZONE_DEFS.map(function(z){ return z.name; });
  var fc = ee.FeatureCollection(ee.List.sequence(1, 12).map(function(mo) {
    mo = ee.Number(mo).toInt();
    var monthMean = getIC(key)
      .filter(ee.Filter.calendarRange(mo, mo, 'month'))
      .select('precip_mm_day').mean();
    var zoneVals = monthMean.reduceRegions({
      collection: ECO_ZONES, reducer: ee.Reducer.mean(), scale: CFG.chartScale,
    });
    var props = ECO_ZONE_DEFS.reduce(function(dict, z) {
      var val = zoneVals.filter(ee.Filter.eq('zone_name', z.name)).first().get('mean');
      return ee.Dictionary(dict).set(z.name, val);
    }, ee.Dictionary({}));
    return ee.Feature(null, ee.Dictionary(props).set('month', mo));
  }));
  print(ui.Chart.feature.byFeature({
    features: fc, xProperty: 'month', yProperties: zoneNames,
  }).setChartType('LineChart').setOptions({
    title      : 'Annual Cycle by Ecological Zone — ' + key,
    vAxis      : {title:'Precipitation (mm/day)'},
    hAxis      : {title:'Month', ticks:TICKS},
    lineWidth  : 2, pointSize:4, colors: zoneColors,
    legend     : {position:'right'}, height:400,
    backgroundColor: '#FAFAFA',
  }));
  setDone('Zonal annual cycle printed — ' + key);
}

// ── 5. Zonal annual cycle — all 7 products, one chart per zone ───────────
// Novel analysis #3: shows bimodal Guinean vs unimodal Sahelian signal
// and where products disagree within each zone
function runZonalAnnualCycleAllProducts() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  setStatus('Annual cycle × all zones\n(~2-3 min, 5 charts)');
  var TICKS = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];
  var colors = PKEYS.map(function(k){ return PRODUCTS[k].color; });

  ECO_ZONE_DEFS.forEach(function(z) {
    var zoneGeom = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name)).geometry();

    var fc = ee.FeatureCollection(ee.List.sequence(1, 12).map(function(mo) {
      mo = ee.Number(mo).toInt();
      var firstBand = getIC(PKEYS[0])
        .filter(ee.Filter.calendarRange(mo, mo, 'month'))
        .select('precip_mm_day').mean().clip(zoneGeom).rename(PKEYS[0]);
      var img = PKEYS.slice(1).reduce(function(acc, key) {
        var band = getIC(key)
          .filter(ee.Filter.calendarRange(mo, mo, 'month'))
          .select('precip_mm_day').mean().clip(zoneGeom).rename(key);
        return ee.Image(acc).addBands(band);
      }, firstBand);
      var vals = ee.Image(img).reduceRegion({
        reducer: ee.Reducer.mean(), geometry: zoneGeom,
        scale: CFG.chartScale, maxPixels: 1e9, tileScale: 4,
      });
      return ee.Feature(null, vals.set('month', mo));
    }));

    print(ui.Chart.feature.byFeature({
      features: fc, xProperty: 'month', yProperties: PKEYS,
    }).setChartType('LineChart').setOptions({
      title      : 'Annual Cycle — ' + z.name + ' (' + z.rainfall + ')',
      vAxis      : {title:'Precipitation (mm/day)'},
      hAxis      : {title:'Month', ticks:TICKS},
      lineWidth  : 2, pointSize:4, colors: colors,
      legend     : {position:'right'}, height:350,
      backgroundColor: '#FAFAFA',
    }));
  });
  setDone('5 zonal annual cycle charts printed — check Console.');
}

// ── 6. Full zonal metric matrix — all products × all zones × 8 metrics ───
// Novel analysis #1: core contribution table for the paper
// Runtime: ~3-5 minutes
function runZonalMetricMatrix() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var ref = refSel.getValue();
  setStatus('Zonal metric matrix\nvs ' + ref + '\n(~3-5 min)');
  var refIC      = tagYM(getIC(ref)).select('precip_mm_day');
  var refMonthly = tagYrMo(refIC);

  PKEYS.forEach(function(key) {
    if (key === ref) return;
    var prodMonthly = tagYrMo(tagYM(getIC(key)).select('precip_mm_day'));

    ECO_ZONE_DEFS.forEach(function(z) {
      var zoneGeom = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name)).geometry();

      var joined = ee.Join.inner().apply({
        primary  : prodMonthly,
        secondary: refMonthly,
        condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
      });

      var pairs = ee.FeatureCollection(joined.map(function(feat) {
        var simVal = ee.Image(feat.get('primary')).clip(zoneGeom).reduceRegion({
          reducer: ee.Reducer.mean(), geometry: zoneGeom,
          scale: CFG.chartScale, maxPixels: 1e9,
        }).get('precip_mm_day');
        var obsVal = ee.Image(feat.get('secondary')).clip(zoneGeom).reduceRegion({
          reducer: ee.Reducer.mean(), geometry: zoneGeom,
          scale: CFG.chartScale, maxPixels: 1e9,
        }).get('precip_mm_day');
        return ee.Feature(null, {sim: simVal, obs: obsVal});
      }));

      var validPairs = pairs.filter(ee.Filter.notNull(['sim','obs']));
      var metrics    = computeMetrics(validPairs);
      print(' ' + key + ' vs ' + ref + ' | ' + z.name + ':', metrics);
    });
  });
  setDone('Zonal metric matrix printed — check Console.');
}

// ── 7. Product ranking by KGE per zone ───────────────────────────────────
// Novel analysis #4: direct management recommendation per zone
// Runtime: ~3-5 minutes
function runZonalProductRanking() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var ref = refSel.getValue();
  setStatus('Product ranking by zone\nvs ' + ref + '\n(~3-5 min)');
  var refMonthly = tagYrMo(tagYM(getIC(ref)).select('precip_mm_day'));

  ECO_ZONE_DEFS.forEach(function(z) {
    var zoneGeom = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name)).geometry();

    var kgeList = PKEYS.filter(function(k){ return k !== ref; }).map(function(key) {
      var prodMonthly = tagYrMo(tagYM(getIC(key)).select('precip_mm_day'));
      var joined = ee.Join.inner().apply({
        primary  : prodMonthly,
        secondary: refMonthly,
        condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
      });
      var pairs = ee.FeatureCollection(joined.map(function(feat) {
        var simVal = ee.Image(feat.get('primary')).clip(zoneGeom).reduceRegion({
          reducer: ee.Reducer.mean(), geometry: zoneGeom,
          scale: CFG.chartScale, maxPixels: 1e9,
        }).get('precip_mm_day');
        var obsVal = ee.Image(feat.get('secondary')).clip(zoneGeom).reduceRegion({
          reducer: ee.Reducer.mean(), geometry: zoneGeom,
          scale: CFG.chartScale, maxPixels: 1e9,
        }).get('precip_mm_day');
        return ee.Feature(null, {sim: simVal, obs: obsVal});
      }));
      var metrics = computeMetrics(pairs.filter(ee.Filter.notNull(['sim','obs'])));
      return ee.Feature(null, {
        product: key, zone: z.name,
        KGE: metrics.get('kge'), NSE: metrics.get('nse'),
        r  : metrics.get('r'),   pbias: metrics.get('pbias_pct'),
      });
    });

    print(' Product ranking — ' + z.name + ' (vs ' + ref + '):',
      ee.FeatureCollection(kgeList).select(['product','KGE','NSE','r','pbias']));
  });
  setDone('Product ranking printed per zone — check Console.');
}

// ── 8. Categorical threshold sensitivity by zone ──────────────────────────
// Novel analysis #6: tests 0.5, 1.0, 2.0 mm/day thresholds per zone
// Shows whether Sahel FAR is threshold-specific or fundamental
function runThresholdSensitivity() {
  if (!ECO_ZONES_READY) { setError('Ecological zones asset not loaded.'); return; }
  var key = prodSel.getValue();
  var ref = refSel.getValue();
  if (key === ref) { setError('Product = Reference.'); return; }
  setStatus('Threshold sensitivity\n' + key + ' vs ' + ref + '\n(~2 min)');

  var prodIC = tagYrMo(tagYM(getIC(key)).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('prod'); }));
  var refIC  = tagYrMo(tagYM(getIC(ref)).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('ref'); }));
  var joined = ee.Join.inner().apply({
    primary: prodIC, secondary: refIC,
    condition: ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });

  [0.5, 1.0, 2.0].forEach(function(thresh) {
    var cont = ee.ImageCollection(joined.map(function(feat) {
      var p = ee.Image(feat.get('primary'));
      var r = ee.Image(feat.get('secondary'));
      var pR = p.gte(thresh);
      var rR = r.gte(thresh);
      return pR.and(rR)           .rename('hits')
        .addBands(rR.and(pR.not()).rename('misses'))
        .addBands(pR.and(rR.not()).rename('false_al'));
    })).sum();

    ECO_ZONE_DEFS.forEach(function(z) {
      var zoneGeom = ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name)).geometry();
      var tot = cont.clip(zoneGeom).reduceRegion({
        reducer: ee.Reducer.sum(), geometry: zoneGeom,
        scale: CFG.chartScale, maxPixels: 1e12,
      });
      var H  = ee.Number(tot.get('hits'));
      var M  = ee.Number(tot.get('misses'));
      var FA = ee.Number(tot.get('false_al'));
      print('🎯 thresh=' + thresh + ' | ' + z.name + ' | ' + key + ' vs ' + ref + ':',
        ee.Dictionary({
          POD: H.divide(H.add(M)),
          FAR: FA.divide(H.add(FA)),
          CSI: H.divide(H.add(M).add(FA)),
        }));
    });
  });
  setDone('Threshold sensitivity printed — check Console.');
}

// ── 9. Inter-product agreement map ───────────────────────────────────────
// Novel analysis #7: pixel-wise std dev across all 7 products
// High values = where products disagree most = where ensemble is needed
function runInterProductAgreement() {
  setStatus('Inter-product agreement\n(~60s)');
  var firstMean = getMean(PKEYS[0]).rename(PKEYS[0]);
  var stacked   = PKEYS.slice(1).reduce(function(acc, key) {
    return ee.Image(acc).addBands(getMean(key).rename(key));
  }, firstMean);
  var stdImg = stacked.reduce(ee.Reducer.stdDev()).rename('std_mm_day').clip(ROI);

  Map.addLayer(stdImg, {
    min:0, max:3,
    palette:['#FFFFFF','#FFF176','#FFB300','#E65100','#B71C1C'],
  }, '📏 Inter-product std dev (mm/day)', true);

  if (ECO_ZONES_READY) {
    var zoneAgreement = stdImg.reduceRegions({
      collection: ECO_ZONES, reducer: ee.Reducer.mean(), scale: CFG.chartScale,
    });
    print(' Inter-product std dev by zone (mm/day):',
      zoneAgreement.select(['zone_name','mean']));
    // Map.addLayer(ECO_ZONES.style({fillColor:'00000000', color:'333333', width:1.5}),
    //   {}, '🌿 Zone boundaries', true);
  }
  setDone('Inter-product agreement map added — std dev by zone in Console.');
}


// ════════════════════════════════════════════════════════════
// § 21  MAP CLICK INSPECTOR
// ════════════════════════════════════════════════════════════

Map.onClick(function(coords) {
  inspectOut.setValue('⟳ Sampling …');
  var key = prodSel.getValue();
  var pt  = ee.Geometry.Point([coords.lon, coords.lat]);

  getMean(key).rename('precip_mm_day').reduceRegion({
    reducer:ee.Reducer.first(), geometry:pt, scale:CFG.targetScale,
  }).evaluate(function(res) {
    if (!res) { inspectOut.setValue('No data.'); return; }
    var v = res['precip_mm_day'];
    inspectOut.setValue(
      '📍 ' + coords.lat.toFixed(3) + '°N  ' +
              coords.lon.toFixed(3) + '°E\n' +
      key + ':  ' +
      (v != null ? (Math.round(v*100)/100)+' mm/day (LT mean)' : 'n/a')
    );
  });

  // Pixel time-series chart for selected product
  print(ui.Chart.image.series({
    imageCollection: getIC(key).select('precip_mm_day'),
    region: pt, reducer: ee.Reducer.first(),
    scale: CFG.targetScale, xProperty: 'system:time_start',
  }).setSeriesNames([key]).setChartType('LineChart').setOptions({
    title    : '📍 Pixel Time Series  |  ' + key + '  |  ' +
               coords.lat.toFixed(2)+'°N '+coords.lon.toFixed(2)+'°E',
    vAxis    : {title:'mm/day'},
    hAxis    : {title:'Date', format:'MMM yyyy'},
    lineWidth: 1.5, pointSize:2,
    colors   : [PRODUCTS[key].color],
    legend   : {position:'none'}, height:320,
    backgroundColor: '#FAFAFA',
  }));
});


// ════════════════════════════════════════════════════════════
// § 22  BOUNDARY OVERLAY  (always on top)
// ════════════════════════════════════════════════════════════

Map.addLayer(
  ee.Image().byte().paint({
    featureCollection: BOUNDARY, color:1, width:2
  }),
  {palette:['#FF5722'], opacity:0.9},
  '🗺 West Africa Boundary', true
);

Map.addLayer(STATION_FC, {color:'#FFEB3B'}, '📍 Gauge Stations', true);

// Force viewport to West Africa AFTER all layers are added
// (prevents any layer centroid calculation from shifting the view)
Map.setCenter(-5, 12, 5);

print(' Dashboard ready.');
print('   Select a product, then click any button to compute a layer.');
print('   Heavy operations (correlation, trend, categorical) take 30–90s.');