// ============================================================
// MODULE: actions
// All runXxx analysis functions and zonal analysis
// Each function receives selector values as parameters —
// no circular dependency with ui_panel
// ============================================================

var CFG_MOD  = require('users/Desmond/climate_studies:utils/config');
var PROD_MOD = require('users/Desmond/climate_studies:utils/products');
var HAR      = require('users/Desmond/climate_studies:utils/harmonise');
var AREA     = require('users/Desmond/climate_studies:utils/study_area');
var STN      = require('users/Desmond/climate_studies:utils/stations');
var UI       = require('users/Desmond/climate_studies:utils/ui_helpers');

var CFG      = CFG_MOD.CFG;
var VIS      = CFG_MOD.VIS;
var PRODUCTS = PROD_MOD.PRODUCTS;
var PKEYS    = PROD_MOD.PKEYS;
var ROI      = AREA.ROI;

// ── Spatial layers ────────────────────────────────────────────

exports.runAnnualTotal = function(key, zone) {
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Annual total: ' + key);
  Map.addLayer(HAR.getMean(key, ROI).multiply(365.25).clip(region),
    VIS.annual, 'Annual Total – ' + key + ' [' + zone + '] (mm/yr)');
  UI.setDone('Annual total added: ' + key);
};

exports.runDailyMean = function(key, zone) {
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Daily mean: ' + key);
  Map.addLayer(HAR.getMean(key, ROI).clip(region),
    VIS.daily, 'Daily Mean – ' + key + ' [' + zone + '] (mm/d)');
  UI.setDone('Daily mean added: ' + key);
};

exports.runBias = function(key, ref, zone) {
  if (key === ref) { UI.setError('Product = Reference.'); return; }
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Bias: ' + key + ' vs ' + ref);
  var prodM  = HAR.getMean(key, ROI).clip(ROI);
  var refM   = HAR.getMean(ref, ROI).clip(ROI);
  var bias   = prodM.subtract(refM).rename('bias_mm_day');
  var pbias  = prodM.subtract(refM).divide(refM.add(1e-6))
    .multiply(100).clamp(-80,80).rename('pbias_pct');
  Map.addLayer(bias.clip(region),  VIS.bias,
    'Bias – ' + key + ' vs ' + ref + ' (mm/d)');
  Map.addLayer(pbias.clip(region), VIS.pbias,
    '% Bias – ' + key + ' vs ' + ref + ' (%)');
  UI.setDone('Bias maps added: ' + key + ' vs ' + ref);
};

exports.runCorrelation = function(key, ref, zone) {
  if (key === ref) { UI.setError('Product = Reference.'); return; }
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Correlation: ' + key + ' vs ' + ref + ' (~30-60s)');
  var tagFn  = HAR.tagYrMo;
  var toGrid = HAR.toGrid;
  var prodIC = tagFn(HAR.getIC(key).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('prod'); }));
  var refIC  = tagFn(HAR.getIC(ref).select('precip_mm_day')
    .map(function(i){ return toGrid(i.clip(ROI)).rename('ref'); }));
  var joined = ee.Join.inner().apply({
    primary:prodIC, secondary:refIC,
    condition:ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });
  var corr = ee.ImageCollection(joined.map(function(f) {
    return ee.Image(f.get('primary'))
      .addBands(ee.Image(f.get('secondary')));
  })).select(['prod','ref']).reduce(ee.Reducer.pearsonsCorrelation())
    .select('correlation').clip(ROI);
  Map.addLayer(corr.clip(region), VIS.corr,
    'r – ' + key + ' vs ' + ref + ' [' + zone + ']');
  UI.setDone('Correlation map added.');
};

exports.runTrend = function(key, zone) {
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Trend: ' + key + ' (~30-60s)');
  var t0      = ee.Date(CFG.startDate).millis();
  var msPerYr = 1000 * 60 * 60 * 24 * 365.25;
  var withT   = HAR.getIC(key).select('precip_mm_day').map(function(img) {
    var t = ee.Number(img.get('system:time_start'))
      .subtract(t0).divide(msPerYr).float();
    return HAR.toGrid(img.clip(ROI)).float()
      .addBands(ee.Image.constant(t).rename('time').float());
  });
  var trend = withT.select(['time','precip_mm_day'])
    .reduce(ee.Reducer.linearFit()).select('scale')
    .rename('trend').clip(ROI);
  Map.addLayer(trend.clip(region), VIS.trend,
    'Trend – ' + key + ' [' + zone + '] (mm/d/yr)');
  UI.setDone('Trend map added: ' + key);
};

exports.runSeasonal = function(key, season, zone) {
  var region = AREA.getAnalysisRegion(zone);
  var moMap  = {DJF:[12,1,2], MAM:[3,4,5], JJA:[6,7,8], SON:[9,10,11]};
  UI.setStatus('Seasonal mean: ' + season + ' / ' + key);
  var mean = HAR.toGrid(
    HAR.tagYM(HAR.getIC(key))
      .filter(ee.Filter.inList('month', moMap[season]))
      .select('precip_mm_day').mean().clip(region)
  );
  Map.addLayer(mean, VIS.daily, season + ' – ' + key + ' (mm/d)');
  UI.setDone(season + ' mean added: ' + key);
};

// ── Time-series charts ────────────────────────────────────────

exports.runTimeSeriesAll = function(zone) {
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Time-series all products (~60s)');
  var colors = PKEYS.map(function(k){ return PRODUCTS[k].color; });
  var base   = HAR.tagYrMo(HAR.getIC(PKEYS[0]).select('precip_mm_day'))
    .map(function(img){ return img.rename(PKEYS[0]); });
  var stacked = PKEYS.slice(1).reduce(function(baseIC, key) {
    var other = HAR.tagYrMo(HAR.getIC(key).select('precip_mm_day'))
      .map(function(img){ return img.rename(key); });
    var joined = ee.Join.inner().apply({
      primary:baseIC, secondary:other,
      condition:ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
    });
    return ee.ImageCollection(joined.map(function(f) {
      return ee.Image(f.get('primary'))
        .addBands(ee.Image(f.get('secondary')))
        .copyProperties(ee.Image(f.get('primary')),
          ['system:time_start','yr_mo']);
    }));
  }, base);
  print(ui.Chart.image.series({
    imageCollection:stacked, region:region,
    reducer:ee.Reducer.mean(), scale:CFG.chartScale,
    xProperty:'system:time_start',
  }).setSeriesNames(PKEYS).setChartType('LineChart').setOptions({
    title:'Monthly Precipitation – ' + zone + ' (All Products)',
    vAxis:{title:'mm/day'},
    hAxis:{title:'Date', format:'MMM yyyy'},
    lineWidth:1.5, pointSize:0, colors:colors,
    legend:{position:'right'}, height:380,
  }));
  UI.setDone('Time-series chart printed.');
};

exports.runTimeSeriesSingle = function(key, zone) {
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Time-series: ' + key);
  print(ui.Chart.image.series({
    imageCollection:HAR.getIC(key).select('precip_mm_day'),
    region:region, reducer:ee.Reducer.mean(),
    scale:CFG.chartScale, xProperty:'system:time_start',
  }).setSeriesNames([key]).setChartType('LineChart').setOptions({
    title:'Monthly Mean – ' + key + ' [' + zone + ']',
    vAxis:{title:'mm/day'}, lineWidth:1.5, pointSize:0,
    colors:[PRODUCTS[key].color], legend:{position:'none'}, height:350,
  }));
  UI.setDone('Time-series printed: ' + key);
};

exports.runAnnualCycle = function(zone) {
  var chartRegion = (zone && zone !== 'All West Africa')
    ? AREA.getAnalysisRegion(zone)
    : ee.Geometry.Rectangle([-0.5,5.4,0.5,6.4]);
  var label = (zone && zone !== 'All West Africa') ? zone : 'West Africa';
  UI.setStatus('Annual cycle chart (~30-60s)');
  var TICKS = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];
  var colors = PKEYS.map(function(k){ return PRODUCTS[k].color; });
  var fc = ee.FeatureCollection(ee.List.sequence(1,12).map(function(mo) {
    mo = ee.Number(mo).toInt();
    var firstBand = HAR.getIC(PKEYS[0])
      .filter(ee.Filter.calendarRange(mo,mo,'month'))
      .select('precip_mm_day').mean().rename(PKEYS[0]);
    var img = PKEYS.slice(1).reduce(function(acc, key) {
      return ee.Image(acc).addBands(
        HAR.getIC(key).filter(ee.Filter.calendarRange(mo,mo,'month'))
          .select('precip_mm_day').mean().rename(key));
    }, firstBand);
    return ee.Feature(null,
      ee.Image(img).reduceRegion({
        reducer:ee.Reducer.mean(), geometry:chartRegion,
        scale:100000, maxPixels:1e9, tileScale:8,
      }).set('month', mo));
  }));
  print(ui.Chart.feature.byFeature({
    features:fc, xProperty:'month', yProperties:PKEYS,
  }).setChartType('LineChart').setOptions({
    title:'Mean Annual Cycle – ' + label,
    vAxis:{title:'Precipitation (mm/day)'},
    hAxis:{title:'Month', ticks:TICKS},
    lineWidth:2, pointSize:5, colors:colors,
    legend:{position:'right'}, height:380,
  }));
  UI.setDone('Annual cycle chart printed.');
};

// ── Station validation ────────────────────────────────────────

exports.runStationValidation = function(key, stationStr) {
  var sId  = stationStr.split(' – ')[0];
  var sObj = null;
  STN.STATIONS_RAW.forEach(function(s){ if(s.id === sId) sObj = s; });
  if (!sObj) { UI.setError('Station not found.'); return; }
  UI.setStatus('Validating ' + sObj.name + ' vs ' + key);
  var pt      = ee.Geometry.Point([sObj.lon, sObj.lat]);
  var ic      = HAR.tagYM(HAR.getIC(key)).select('precip_mm_day');
  var sampled = ic.map(function(img) {
    var val = img.reduceRegion({
      reducer:ee.Reducer.first(), geometry:pt,
      scale:CFG.targetScale,
    }).get('precip_mm_day');
    return ee.Feature(null, {
      station_id:sId, product:key,
      year:img.get('year'), month:img.get('month'), sim:val,
    });
  });
  var stObs  = STN.OBS_FC.filter(ee.Filter.eq('station_id', sId));
  var joined = ee.Join.inner().apply({
    primary:sampled, secondary:stObs,
    condition:ee.Filter.and(
      ee.Filter.equals({leftField:'year',  rightField:'year'}),
      ee.Filter.equals({leftField:'month', rightField:'month'})
    ),
  });
  var pairs = joined.map(function(feat) {
    return ee.Feature(null, {
      sim: ee.Number(ee.Feature(feat.get('primary')).get('sim')),
      obs: ee.Number(ee.Feature(feat.get('secondary')).get('obs_mm_day')),
    });
  });
  var validPairs = pairs.filter(ee.Filter.notNull(['sim','obs']));
  print('Metrics – ' + sObj.name + ' / ' + key + ':',
    HAR.computeMetrics(validPairs));
  print(ui.Chart.feature.byFeature({
    features:validPairs, xProperty:'obs', yProperties:['sim'],
  }).setChartType('ScatterChart').setOptions({
    title:'Obs vs ' + key + '  |  ' + sObj.name,
    hAxis:{title:'Observed (mm/day)', minValue:0},
    vAxis:{title:key + ' (mm/day)',   minValue:0},
    pointSize:3, colors:[PRODUCTS[key].color],
    trendlines:{0:{type:'linear', color:'#FF0000', lineWidth:1}},
    height:380,
  }));
  UI.setDone('Validation done: ' + sObj.name);
};

// ── Categorical metrics ───────────────────────────────────────

exports.runCategorical = function(key, ref, zone) {
  if (key === ref) { UI.setError('Product = Reference.'); return; }
  var region = AREA.getAnalysisRegion(zone);
  UI.setStatus('Categorical: ' + key + ' vs ' + ref + ' (~30-60s)');
  var prodIC = HAR.tagYrMo(HAR.tagYM(HAR.getIC(key)).select('precip_mm_day')
    .map(function(i){ return HAR.toGrid(i.clip(region)).rename('prod'); }));
  var refIC  = HAR.tagYrMo(HAR.tagYM(HAR.getIC(ref)).select('precip_mm_day')
    .map(function(i){ return HAR.toGrid(i.clip(region)).rename('ref'); }));
  var joined = ee.Join.inner().apply({
    primary:prodIC, secondary:refIC,
    condition:ee.Filter.equals({leftField:'yr_mo', rightField:'yr_mo'}),
  });
  var cont = ee.ImageCollection(joined.map(function(feat) {
    var p  = ee.Image(feat.get('primary'));
    var r  = ee.Image(feat.get('secondary'));
    var pR = p.gte(CFG.rainThresh);
    var rR = r.gte(CFG.rainThresh);
    return pR.and(rR).rename('hits')
      .addBands(rR.and(pR.not()).rename('misses'))
      .addBands(pR.and(rR.not()).rename('false_al'))
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
  print('Categorical – ' + key + ' vs ' + ref + ' [' + zone + ']:',
    ee.Dictionary({
      POD:H.divide(H.add(M)), FAR:FA.divide(H.add(FA)),
      CSI:H.divide(H.add(M).add(FA)),
      FREQ_BIAS:H.add(FA).divide(H.add(M)),
      hits:H, misses:M, false_al:FA, correct_neg:CN,
    }));
  Map.addLayer(
    cont.select('hits').divide(cont.select('hits').add(cont.select('misses'))),
    VIS.pod, 'POD – ' + key + ' vs ' + ref);
  Map.addLayer(
    cont.select('false_al').divide(cont.select('hits').add(cont.select('false_al'))),
    VIS.far, 'FAR – ' + key + ' vs ' + ref);
  UI.setDone('Categorical metrics printed.');
};

// ── Zonal analysis ────────────────────────────────────────────

exports.showZoneBoundaries = function() {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  AREA.ECO_ZONE_DEFS.forEach(function(z) {
    Map.addLayer(
      AREA.ECO_ZONES.filter(ee.Filter.eq('zone_name', z.name))
        .style({fillColor:z.color+'44', color:'00000000'}),
      {}, z.name + ' (' + z.rainfall + ')', true);
  });
};

exports.runZonalMean = function(key) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  UI.setStatus('Zonal mean: ' + key);
  var mean = HAR.getMean(key, ROI);
  print('Zonal mean (mm/day) — ' + key + ':',
    mean.reduceRegions({
      collection:AREA.ECO_ZONES,
      reducer:ee.Reducer.mean(),
      scale:CFG.chartScale,
    }).select(['zone_name','mean']));
  AREA.ECO_ZONE_DEFS.forEach(function(z) {
    Map.addLayer(mean.clip(
      AREA.ECO_ZONES.filter(ee.Filter.eq('zone_name',z.name)).geometry()),
      VIS.daily, z.name + ' — ' + key, true);
  });
  UI.setDone('Zonal mean printed: ' + key);
};

exports.runZonalBias = function(key, ref) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  if (key === ref) { UI.setError('Product = Reference.'); return; }
  UI.setStatus('Zonal bias: ' + key + ' vs ' + ref);
  var bias  = HAR.getMean(key,ROI).subtract(HAR.getMean(ref,ROI)).rename('bias_mm_day');
  var pbias = HAR.getMean(key,ROI).subtract(HAR.getMean(ref,ROI))
    .divide(HAR.getMean(ref,ROI).add(1e-6)).multiply(100).rename('pbias_pct');
  print('Zonal bias — ' + key + ' vs ' + ref + ':',
    bias.addBands(pbias).reduceRegions({
      collection:AREA.ECO_ZONES, reducer:ee.Reducer.mean(),
      scale:CFG.chartScale,
    }).select(['zone_name','bias_mm_day','pbias_pct']));
  Map.addLayer(bias.clip(ROI), VIS.bias, 'Bias – ' + key + ' vs ' + ref);
  UI.setDone('Zonal bias printed.');
};

exports.runZonalAnnualCycle = function(key) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  UI.setStatus('Zonal annual cycle: ' + key + ' (~60s)');
  var TICKS = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];
  var zoneColors = AREA.ECO_ZONE_DEFS.map(function(z){ return z.color; });
  var zoneNames  = AREA.ECO_ZONE_DEFS.map(function(z){ return z.name; });
  var fc = ee.FeatureCollection(ee.List.sequence(1,12).map(function(mo) {
    mo = ee.Number(mo).toInt();
    var monthMean = HAR.getIC(key)
      .filter(ee.Filter.calendarRange(mo,mo,'month'))
      .select('precip_mm_day').mean();
    var zoneVals  = monthMean.reduceRegions({
      collection:AREA.ECO_ZONES, reducer:ee.Reducer.mean(),
      scale:CFG.chartScale,
    });
    var props = AREA.ECO_ZONE_DEFS.reduce(function(dict, z) {
      return ee.Dictionary(dict).set(z.name,
        zoneVals.filter(ee.Filter.eq('zone_name',z.name)).first().get('mean'));
    }, ee.Dictionary({}));
    return ee.Feature(null, ee.Dictionary(props).set('month', mo));
  }));
  print(ui.Chart.feature.byFeature({
    features:fc, xProperty:'month', yProperties:zoneNames,
  }).setChartType('LineChart').setOptions({
    title:'Annual Cycle by Zone — ' + key,
    vAxis:{title:'Precipitation (mm/day)'},
    hAxis:{title:'Month', ticks:TICKS},
    lineWidth:2, pointSize:4, colors:zoneColors,
    legend:{position:'right'}, height:400,
  }));
  UI.setDone('Zonal annual cycle printed.');
};

exports.runZonalAnnualCycleAllProducts = function() {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  UI.setStatus('Annual cycle all zones (~2-3 min, 5 charts)');
  var TICKS = [
    {v:1,f:'Jan'},{v:2,f:'Feb'},{v:3,f:'Mar'},{v:4,f:'Apr'},
    {v:5,f:'May'},{v:6,f:'Jun'},{v:7,f:'Jul'},{v:8,f:'Aug'},
    {v:9,f:'Sep'},{v:10,f:'Oct'},{v:11,f:'Nov'},{v:12,f:'Dec'},
  ];
  var colors = PKEYS.map(function(k){ return PRODUCTS[k].color; });
  AREA.ECO_ZONE_DEFS.forEach(function(z) {
    var zoneGeom = AREA.ECO_ZONES
      .filter(ee.Filter.eq('zone_name',z.name)).geometry();
    var fc = ee.FeatureCollection(ee.List.sequence(1,12).map(function(mo) {
      mo = ee.Number(mo).toInt();
      var img = PKEYS.slice(1).reduce(function(acc, key) {
        return ee.Image(acc).addBands(
          HAR.getIC(key).filter(ee.Filter.calendarRange(mo,mo,'month'))
            .select('precip_mm_day').mean().clip(zoneGeom).rename(key));
      }, HAR.getIC(PKEYS[0]).filter(ee.Filter.calendarRange(mo,mo,'month'))
          .select('precip_mm_day').mean().clip(zoneGeom).rename(PKEYS[0]));
      return ee.Feature(null,
        ee.Image(img).reduceRegion({
          reducer:ee.Reducer.mean(), geometry:zoneGeom,
          scale:CFG.chartScale, maxPixels:1e9, tileScale:4,
        }).set('month', mo));
    }));
    print(ui.Chart.feature.byFeature({
      features:fc, xProperty:'month', yProperties:PKEYS,
    }).setChartType('LineChart').setOptions({
      title:'Annual Cycle — ' + z.name + ' (' + z.rainfall + ')',
      vAxis:{title:'Precipitation (mm/day)'},
      hAxis:{title:'Month', ticks:TICKS},
      lineWidth:2, pointSize:4, colors:colors,
      legend:{position:'right'}, height:350,
    }));
  });
  UI.setDone('5 zonal annual cycle charts printed.');
};

exports.runZonalMetricMatrix = function(ref) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  UI.setStatus('Metric matrix vs ' + ref + ' (~3-5 min)');
  var refMonthly = HAR.tagYrMo(HAR.tagYM(HAR.getIC(ref)).select('precip_mm_day'));
  PKEYS.forEach(function(key) {
    if (key === ref) return;
    var prodMonthly = HAR.tagYrMo(HAR.tagYM(HAR.getIC(key)).select('precip_mm_day'));
    AREA.ECO_ZONE_DEFS.forEach(function(z) {
      var zoneGeom = AREA.ECO_ZONES
        .filter(ee.Filter.eq('zone_name',z.name)).geometry();
      var joined = ee.Join.inner().apply({
        primary:prodMonthly, secondary:refMonthly,
        condition:ee.Filter.equals({leftField:'yr_mo',rightField:'yr_mo'}),
      });
      var pairs = ee.FeatureCollection(joined.map(function(feat) {
        return ee.Feature(null, {
          sim: ee.Image(feat.get('primary')).clip(zoneGeom).reduceRegion({
            reducer:ee.Reducer.mean(), geometry:zoneGeom,
            scale:CFG.chartScale, maxPixels:1e9,
          }).get('precip_mm_day'),
          obs: ee.Image(feat.get('secondary')).clip(zoneGeom).reduceRegion({
            reducer:ee.Reducer.mean(), geometry:zoneGeom,
            scale:CFG.chartScale, maxPixels:1e9,
          }).get('precip_mm_day'),
        });
      }));
      print(key + ' vs ' + ref + ' | ' + z.name + ':',
        HAR.computeMetrics(pairs.filter(ee.Filter.notNull(['sim','obs']))));
    });
  });
  UI.setDone('Metric matrix printed.');
};

exports.runZonalProductRanking = function(ref) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  UI.setStatus('Product ranking by zone vs ' + ref + ' (~3-5 min)');
  var refMonthly = HAR.tagYrMo(HAR.tagYM(HAR.getIC(ref)).select('precip_mm_day'));
  AREA.ECO_ZONE_DEFS.forEach(function(z) {
    var zoneGeom = AREA.ECO_ZONES
      .filter(ee.Filter.eq('zone_name',z.name)).geometry();
    var kgeList = PKEYS.filter(function(k){ return k !== ref; }).map(function(key) {
      var prodMonthly = HAR.tagYrMo(HAR.tagYM(HAR.getIC(key)).select('precip_mm_day'));
      var joined = ee.Join.inner().apply({
        primary:prodMonthly, secondary:refMonthly,
        condition:ee.Filter.equals({leftField:'yr_mo',rightField:'yr_mo'}),
      });
      var pairs = ee.FeatureCollection(joined.map(function(feat) {
        return ee.Feature(null, {
          sim: ee.Image(feat.get('primary')).clip(zoneGeom).reduceRegion({
            reducer:ee.Reducer.mean(), geometry:zoneGeom,
            scale:CFG.chartScale, maxPixels:1e9,
          }).get('precip_mm_day'),
          obs: ee.Image(feat.get('secondary')).clip(zoneGeom).reduceRegion({
            reducer:ee.Reducer.mean(), geometry:zoneGeom,
            scale:CFG.chartScale, maxPixels:1e9,
          }).get('precip_mm_day'),
        });
      }));
      var m = HAR.computeMetrics(pairs.filter(ee.Filter.notNull(['sim','obs'])));
      return ee.Feature(null, {
        product:key, zone:z.name,
        KGE:m.get('kge'), NSE:m.get('nse'),
        r:m.get('r'), pbias:m.get('pbias_pct'),
      });
    });
    print('Product ranking — ' + z.name + ':',
      ee.FeatureCollection(kgeList).select(['product','KGE','NSE','r','pbias']));
  });
  UI.setDone('Product ranking printed.');
};

exports.runThresholdSensitivity = function(key, ref) {
  if (!AREA.ECO_ZONES_READY) { UI.setError('Zones not loaded.'); return; }
  if (key === ref) { UI.setError('Product = Reference.'); return; }
  UI.setStatus('Threshold sensitivity (~2 min)');
  var prodIC = HAR.tagYrMo(HAR.tagYM(HAR.getIC(key)).select('precip_mm_day')
    .map(function(i){ return HAR.toGrid(i.clip(ROI)).rename('prod'); }));
  var refIC  = HAR.tagYrMo(HAR.tagYM(HAR.getIC(ref)).select('precip_mm_day')
    .map(function(i){ return HAR.toGrid(i.clip(ROI)).rename('ref'); }));
  var joined = ee.Join.inner().apply({
    primary:prodIC, secondary:refIC,
    condition:ee.Filter.equals({leftField:'yr_mo',rightField:'yr_mo'}),
  });
  [0.5, 1.0, 2.0].forEach(function(thresh) {
    var cont = ee.ImageCollection(joined.map(function(feat) {
      var p = ee.Image(feat.get('primary'));
      var r = ee.Image(feat.get('secondary'));
      return p.gte(thresh).and(r.gte(thresh)).rename('hits')
        .addBands(r.gte(thresh).and(p.lt(thresh)).rename('misses'))
        .addBands(p.gte(thresh).and(r.lt(thresh)).rename('false_al'));
    })).sum();
    AREA.ECO_ZONE_DEFS.forEach(function(z) {
      var zoneGeom = AREA.ECO_ZONES
        .filter(ee.Filter.eq('zone_name',z.name)).geometry();
      var tot = cont.clip(zoneGeom).reduceRegion({
        reducer:ee.Reducer.sum(), geometry:zoneGeom,
        scale:CFG.chartScale, maxPixels:1e12,
      });
      var H  = ee.Number(tot.get('hits'));
      var M  = ee.Number(tot.get('misses'));
      var FA = ee.Number(tot.get('false_al'));
      print('thresh='+thresh+' | '+z.name+' | '+key+' vs '+ref+':',
        ee.Dictionary({
          POD:H.divide(H.add(M)),
          FAR:FA.divide(H.add(FA)),
          CSI:H.divide(H.add(M).add(FA)),
        }));
    });
  });
  UI.setDone('Threshold sensitivity printed.');
};

exports.runInterProductAgreement = function() {
  UI.setStatus('Inter-product agreement (~60s)');
  var stacked = PKEYS.slice(1).reduce(function(acc, key) {
    return ee.Image(acc).addBands(HAR.getMean(key,ROI).rename(key));
  }, HAR.getMean(PKEYS[0],ROI).rename(PKEYS[0]));
  var stdImg = stacked.reduce(ee.Reducer.stdDev())
    .rename('std_mm_day').clip(ROI);
  Map.addLayer(stdImg, {
    min:0, max:3,
    palette:['#FFFFFF','#FFF176','#FFB300','#E65100','#B71C1C'],
  }, 'Inter-product std dev (mm/day)', true);
  if (AREA.ECO_ZONES_READY) {
    print('Inter-product std dev by zone:',
      stdImg.reduceRegions({
        collection:AREA.ECO_ZONES,
        reducer:ee.Reducer.mean(),
        scale:CFG.chartScale,
      }).select(['zone_name','mean']));
  }
  UI.setDone('Inter-product agreement added.');
};