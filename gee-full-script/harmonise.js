// ============================================================
// MODULE: harmonise
// Utility functions, harmonisation helpers, IC builder + cache
// ============================================================

var CFG_MOD  = require('users/Desmond/climate_studies:utils/config');
var PROD_MOD = require('users/Desmond/climate_studies:utils/products');
var CFG      = CFG_MOD.CFG;
var PRODUCTS = PROD_MOD.PRODUCTS;
var START_YR = CFG_MOD.START_YR;
var END_YR   = CFG_MOD.END_YR;

// ── Caches ────────────────────────────────────────────────────
var IC_CACHE   = {};
var MEAN_CACHE = {};

// ── Pure utility functions ────────────────────────────────────

exports.computeMetrics = function(pairs) {
  var n = pairs.size();
  var corrResult = pairs.reduceColumns(
    ee.Reducer.pearsonsCorrelation(), ['sim','obs']);
  var r = ee.Number(ee.Algorithms.If(
    n.gte(3), corrResult.get('correlation'), -9999));

  var meanSim = pairs.aggregate_mean('sim');
  var meanObs = pairs.aggregate_mean('obs');
  var bias    = ee.Number(meanSim).subtract(meanObs);
  var pbias   = bias.divide(ee.Number(meanObs).add(1e-6)).multiply(100);

  var mae = pairs.map(function(f) {
    return f.set('ae', ee.Number(f.get('sim'))
      .subtract(ee.Number(f.get('obs'))).abs());
  }).aggregate_mean('ae');

  var mse = pairs.map(function(f) {
    var d = ee.Number(f.get('sim')).subtract(ee.Number(f.get('obs')));
    return f.set('se', d.multiply(d));
  }).aggregate_mean('se');
  var rmse = ee.Number(mse).sqrt();

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
  var beta = ee.Number(meanSim).divide(ee.Number(meanObs).add(1e-12));
  var kge  = ee.Number(1).subtract(
    r.subtract(1).pow(2)
     .add(alpha.subtract(1).pow(2))
     .add(beta.subtract(1).pow(2)).sqrt());

  return ee.Dictionary(ee.Algorithms.If(
    n.gte(3),
    ee.Dictionary({
      n:n, r:r, bias_mmd:bias, pbias_pct:pbias,
      mae_mmd:mae, rmse_mmd:rmse, nse:nse, kge:kge
    }),
    ee.Dictionary({
      n:n, r:-9999, bias_mmd:-9999, pbias_pct:-9999,
      mae_mmd:-9999, rmse_mmd:-9999, nse:-9999,
      kge:-9999, note:'insufficient_pairs (<3)'
    })
  ));
};

exports.tagYrMo = function(ic) {
  return ic.map(function(img) {
    var d = ee.Date(img.get('system:time_start'));
    var s = d.get('year').format('%04d')
      .cat('_').cat(d.get('month').format('%02d'));
    return img.set('yr_mo', s);
  });
};

exports.tagYM = function(ic) {
  return ic.map(function(img) {
    var d = ee.Date(img.get('system:time_start'));
    return img.set('year', d.get('year')).set('month', d.get('month'));
  });
};

exports.toGrid = function(img) {
  return img.resample('bilinear')
    .reproject({crs:'EPSG:4326', scale:CFG.targetScale});
};

exports.joinOnYrMo = function(ic1, ic2, mapFn) {
  var j1 = exports.tagYrMo(ic1);
  var j2 = exports.tagYrMo(ic2);
  var joined = ee.Join.inner().apply({
    primary:j1, secondary:j2,
    condition:ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });
  return ee.ImageCollection(joined.map(mapFn));
};

// ── Harmonisation helpers ─────────────────────────────────────

function harmoniseStd(img, key) {
  var p = PRODUCTS[key];
  var s = img.select([p.band]).multiply(p.scaleFactor)
    .rename('precip_mm_day');
  return s.toFloat().updateMask(s.gte(0))
    .copyProperties(img, ['system:time_start','system:time_end']);
}

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

function harmoniseTerra(img) {
  var d   = ee.Date(img.get('system:time_start'));
  var dim = d.advance(1,'month').difference(d,'day');
  var s   = img.select(['pr']).divide(ee.Image.constant(dim))
    .rename('precip_mm_day');
  return s.toFloat().updateMask(s.gte(0))
    .copyProperties(img, ['system:time_start','system:time_end']);
}

function harmoniseMERRA2daily() {
  var raw = ee.ImageCollection('NASA/GSFC/MERRA/flx/2')
    .filterDate(CFG.startDate, CFG.endDate).select('PRECTOTCORR');
  var nDays = ee.Date(CFG.endDate)
    .difference(ee.Date(CFG.startDate),'day').round();
  return ee.ImageCollection(ee.List.sequence(0, nDays.subtract(1))
    .map(function(d) {
      var date     = ee.Date(CFG.startDate).advance(d,'day');
      var dateNext = date.advance(1,'day');
      var daily    = raw.filterDate(date, dateNext).mean()
        .multiply(86400).rename('precip_mm_day').toFloat();
      return daily.updateMask(daily.gte(0))
        .set('system:time_start', date.millis())
        .set('system:time_end',   dateNext.millis())
        .set('year',  date.get('year'))
        .set('month', date.get('month'));
    }));
}

function harmonise(img, key) {
  var fn = PRODUCTS[key].specialFn;
  if (fn === 'ERA5_MON') return harmoniseERA5Mon(img);
  if (fn === 'TERRA')    return harmoniseTerra(img);
  return harmoniseStd(img, key);
}

function toMonthlyMean(ic) {
  var years  = ee.List.sequence(START_YR, END_YR);
  var months = ee.List.sequence(1, 12);
  var list   = years.map(function(yr) {
    return months.map(function(mo) {
      var s = ee.Date.fromYMD(yr, mo, 1);
      var e = s.advance(1,'month');
      return ic.filterDate(s, e).mean()
        .set('system:time_start', s.millis())
        .set('year', yr).set('month', mo);
    });
  }).flatten();
  return ee.ImageCollection(list);
}

// ── IC builder + cache ────────────────────────────────────────

exports.getIC = function(key) {
  if (IC_CACHE[key]) return IC_CACHE[key];
  var monthly;
  if (key === 'MERRA2') {
    monthly = toMonthlyMean(harmoniseMERRA2daily());
  } else {
    var p   = PRODUCTS[key];
    var raw = ee.ImageCollection(p.collection)
      .filterDate(CFG.startDate, CFG.endDate)
      .select([p.band]);
    var harmonised = raw.map(function(img) {
      return harmonise(img, key);
    });
    monthly = p.isMonthly
      ? exports.tagYM(harmonised)
      : toMonthlyMean(harmonised);
  }
  IC_CACHE[key] = monthly;
  return monthly;
};

exports.getMean = function(key, roi) {
  if (MEAN_CACHE[key]) return MEAN_CACHE[key];
  var m = exports.toGrid(
    exports.getIC(key).select('precip_mm_day').mean()
      .toFloat().clip(roi)
      .updateMask(ee.Image.constant(1).clip(roi).mask())
  );
  MEAN_CACHE[key] = m;
  return m;
};