// ============================================================
// MODULE: study_area
// Study boundary, ecological zones, region helpers
// ============================================================

exports.BOUNDARY = ee.FeatureCollection(
  'projects/ee-desmond/assets/west_africa_boundary0');

exports.ROI = exports.BOUNDARY
  .geometry().simplify({maxError:5000});

exports.ECO_ZONES_READY = true;

exports.ECO_ZONE_DEFS = [
  {id:1, name:'Saharian',         color:'#F5DEB3', rainfall:'<25 mm/yr'},
  {id:2, name:'Sahelian',         color:'#E8A838', rainfall:'200-600 mm/yr'},
  {id:3, name:'Soudanian',        color:'#CC6600', rainfall:'600-1200 mm/yr'},
  {id:4, name:'Guinean',          color:'#78C850', rainfall:'1200-2000 mm/yr'},
  {id:5, name:'Guineo-Congolean', color:'#1A6B1A', rainfall:'>2000 mm/yr'},
];

exports.ECO_ZONES = exports.ECO_ZONES_READY
  ? ee.FeatureCollection(
      'projects/ee-desmond/assets/ecological_zones_5class')
  : ee.FeatureCollection([]);

exports.ECO_ZONE_NAMES = ['All West Africa'].concat(
  exports.ECO_ZONE_DEFS.map(function(z){ return z.name; }));

// Returns the geometry to use for analysis based on zone selector
exports.getAnalysisRegion = function(zoneName) {
  if (!exports.ECO_ZONES_READY) return exports.ROI;
  if (!zoneName || zoneName === 'All West Africa') return exports.ROI;
  return exports.ECO_ZONES
    .filter(ee.Filter.eq('zone_name', zoneName))
    .geometry().intersection(exports.ROI, ee.ErrorMargin(100));
};

// Print zonal stats for a given image across all eco zones
exports.printZonalStats = function(img, label, chartScale) {
  if (!exports.ECO_ZONES_READY) return;
  var stats = img.reduceRegions({
    collection: exports.ECO_ZONES,
    reducer:    ee.Reducer.mean(),
    scale:      chartScale,
  });
  print('Zonal stats — ' + label + ':', stats.select(['zone_name','mean']));
};