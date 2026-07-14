// ============================================================
// MODULE: assets_io
// Export and ingest functions for Drive and GEE Assets
// ============================================================

var CFG_MOD  = require('users/Desmond/climate_studies:utils/config');
var HAR      = require('users/Desmond/climate_studies:utils/harmonise');
var CFG      = CFG_MOD.CFG;

exports.exportMeanToDrive = function(key, roi) {
  Export.image.toDrive({
    image         : HAR.getMean(key, roi).rename('precip_mm_day').toFloat(),
    description   : 'mean_' + key,
    folder        : CFG.exportFolder,
    fileNamePrefix: 'mean_' + key,
    region:roi, scale:CFG.targetScale,
    crs:'EPSG:4326', maxPixels:1e13,
  });
  print('Export queued (Drive): mean_' + key);
};

exports.exportMeanAsAsset = function(key, roi) {
  Export.image.toAsset({
    image      : HAR.getMean(key, roi).rename('precip_mm_day').toFloat(),
    description: 'asset_mean_' + key,
    assetId    : CFG.assetFolder + 'mean_' + key,
    region:roi, scale:CFG.targetScale,
    crs:'EPSG:4326', maxPixels:1e13,
  });
  print('Export queued (Asset): mean_' + key);
};

exports.exportClimatologyAsAsset = function(key, roi) {
  var months = ee.List.sequence(1, 12);
  var clim   = ee.ImageCollection(months.map(function(m) {
    m = ee.Number(m).toInt();
    return HAR.getIC(key)
      .filter(ee.Filter.eq('month', m))
      .select('precip_mm_day').mean()
      .rename(ee.String('month_').cat(m.format()))
      .set('month', m);
  })).toBands().clip(roi);
  Export.image.toAsset({
    image      : clim.toFloat(),
    description: 'asset_clim_' + key,
    assetId    : CFG.assetFolder + 'climatology_' + key,
    region:roi, scale:CFG.targetScale,
    crs:'EPSG:4326', maxPixels:1e13,
  });
  print('Export queued (Asset): climatology_' + key);
};

exports.exportBiasAsAsset = function(key, ref, roi) {
  var bias = HAR.getMean(key, roi)
    .subtract(HAR.getMean(ref, roi)).rename('bias_mm_day');
  Export.image.toAsset({
    image      : bias.toFloat(),
    description: 'asset_bias_' + key + '_vs_' + ref,
    assetId    : CFG.assetFolder + 'bias_' + key + '_vs_' + ref,
    region:roi, scale:CFG.targetScale,
    crs:'EPSG:4326', maxPixels:1e13,
  });
  print('Export queued (Asset): bias_' + key + '_vs_' + ref);
};

exports.loadMeanAsset = function(key) {
  return ee.Image(CFG.assetFolder + 'mean_' + key);
};

exports.getMeanWithFallback = function(key, roi) {
  return ee.Image(CFG.assetFolder + 'mean_' + key)
    .rename('precip_mm_day').unmask(HAR.getMean(key, roi));
};