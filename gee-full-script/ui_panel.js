// ============================================================
// MODULE: ui_panel
// Panel layout, button wiring, click inspector, boundary overlay
// All action functions receive selector values as parameters —
// no circular dependency with actions module
// ============================================================

var CFG_MOD  = require('users/Desmond/climate_studies:utils/config');
var PROD_MOD = require('users/Desmond/climate_studies:utils/products');
var AREA     = require('users/Desmond/climate_studies:utils/study_area');
var STN      = require('users/Desmond/climate_studies:utils/stations');
var ASS      = require('users/Desmond/climate_studies:utils/assets_io');
var UI       = require('users/Desmond/climate_studies:utils/ui_helpers');
var ACT      = require('users/Desmond/climate_studies:utils/actions');
var HAR      = require('users/Desmond/climate_studies:utils/harmonise');

var CFG      = CFG_MOD.CFG;
var VIS      = CFG_MOD.VIS;
var PKEYS    = PROD_MOD.PKEYS;
var PRODUCTS = PROD_MOD.PRODUCTS;

// ── Map setup ─────────────────────────────────────────────────
Map.setCenter(-5, 12, 5);
Map.setOptions('HYBRID');

// ── Selector widgets ─────────────────────────────────────────
var prodSel   = UI.styledSelect(PKEYS, CFG.defaultProd);
var refSel    = UI.styledSelect(PKEYS, CFG.defaultRef);
var zoneSel   = UI.styledSelect(AREA.ECO_ZONE_NAMES, 'All West Africa');
var seasonSel = UI.styledSelect(['DJF','MAM','JJA','SON'], 'JJA');
var stnItems  = STN.STATIONS_RAW.map(function(s){ return s.id+' – '+s.name; });
var stnSel    = UI.styledSelect(stnItems, stnItems[0]);

// ── Shorthand to read current selector values ─────────────────
var key  = function(){ return prodSel.getValue(); };
var ref  = function(){ return refSel.getValue();  };
var zone = function(){ return zoneSel.getValue();  };

// ── Panel ─────────────────────────────────────────────────────
var panel = ui.Panel({
  style:{width:'280px', padding:'10px', backgroundColor:'#F5F5F5'}
});

// Header
panel.add(UI.card([
  ui.Label('🌧  West Africa', {
    fontWeight:'bold', fontSize:'16px', color:'#1565C0', margin:'0'
  }),
  ui.Label('Precipitation Assessment', {
    fontWeight:'bold', fontSize:'12px', color:'#424242', margin:'2px 0 0 0'
  }),
  ui.Label(CFG.startDate + ' – ' + CFG.endDate, {
    fontSize:'10px', color:'#757575', margin:'2px 0 0 0'
  })
]));

// Product / Reference selectors
panel.add(UI.card([
  UI.selectRow('📡  PRODUCT  (select to analyse)', prodSel),
  UI.selectRow('📐  REFERENCE  (for bias & correlation)', refSel)
]));

// Zone selector
panel.add(UI.card([
  ui.Label('🌿  ECOLOGICAL ZONE', {
    fontSize:'10px', fontWeight:'bold', color:'#2e7d32', margin:'4px 0 2px 0',
  }),
  zoneSel,
  ui.Label('Restricts maps & charts to selected zone', {
    fontSize:'9px', color:'#757575', margin:'2px 0 0 0',
  }),
]));

// Status readout
var selReadout = ui.Label('Product: CHIRPS  |  Ref: GPM_IMERG', {
  fontSize:'10px', color:'#000000', fontWeight:'bold', margin:'0 0 4px 0'
});
prodSel.onChange(function(v){
  selReadout.setValue('Product: '+v+'  |  Ref: '+refSel.getValue());
});
refSel.onChange(function(v){
  selReadout.setValue('Product: '+prodSel.getValue()+'  |  Ref: '+v);
});
panel.add(UI.card([selReadout, UI.STATUS]));

// Spatial Layers
panel.add(UI.card([
  UI.heading('🗺  Spatial Layers'),
  ui.Button({label:'Annual Total Map',      style:UI.btnStyle(),
    onClick:function(){ ACT.runAnnualTotal(key(), zone()); }}),
  ui.Button({label:'Mean Daily Rate Map',   style:UI.btnStyle(),
    onClick:function(){ ACT.runDailyMean(key(), zone()); }}),
  ui.Button({label:'Bias Map (vs Ref)',     style:UI.btnStyle(),
    onClick:function(){ ACT.runBias(key(), ref(), zone()); }}),
  ui.Button({label:'Correlation Map',       style:UI.btnStyle(),
    onClick:function(){ ACT.runCorrelation(key(), ref(), zone()); }}),
  ui.Button({label:'Trend Map',             style:UI.btnStyle(),
    onClick:function(){ ACT.runTrend(key(), zone()); }}),
]));

// Zonal Analysis
panel.add(UI.card([
  UI.heading('🌿  Zonal Analysis', '#2e7d32'),
  ui.Button({label:'Show Zone Boundaries',
    style:UI.btnStyle(), onClick:ACT.showZoneBoundaries}),
  ui.Button({label:'Zonal Mean (all zones)',
    style:UI.btnStyle(), onClick:function(){ ACT.runZonalMean(key()); }}),
  ui.Button({label:'Zonal Bias (all zones)',
    style:UI.btnStyle(), onClick:function(){ ACT.runZonalBias(key(), ref()); }}),
  ui.Button({label:'Zonal Annual Cycle',
    style:UI.btnStyle(), onClick:function(){ ACT.runZonalAnnualCycle(key()); }}),
  ui.Button({label:'Annual Cycle — All Products × Zones',
    style:UI.btnStyle(), onClick:ACT.runZonalAnnualCycleAllProducts}),
  ui.Button({label:'Full Metric Matrix (~5 min)',
    style:UI.btnStyle(), onClick:function(){ ACT.runZonalMetricMatrix(ref()); }}),
  ui.Button({label:'Product Ranking by Zone (~5 min)',
    style:UI.btnStyle(), onClick:function(){ ACT.runZonalProductRanking(ref()); }}),
  ui.Button({label:'Threshold Sensitivity',
    style:UI.btnStyle(), onClick:function(){ ACT.runThresholdSensitivity(key(), ref()); }}),
  ui.Button({label:'Inter-product Agreement Map',
    style:UI.btnStyle(), onClick:ACT.runInterProductAgreement}),
]));

// Seasonal
panel.add(UI.card([
  UI.heading('🗓  Seasonal Mean'),
  UI.selectRow('Season', seasonSel),
  ui.Button({label:'Add Seasonal Mean Map', style:UI.btnStyle(),
    onClick:function(){
      ACT.runSeasonal(key(), seasonSel.getValue(), zone());
    }}),
]));

// Charts
panel.add(UI.card([
  UI.heading('📉  Charts'),
  ui.Button({label:'Time Series — All Products', style:UI.btnStyle(),
    onClick:function(){ ACT.runTimeSeriesAll(zone()); }}),
  ui.Button({label:'Time Series — Selected Product', style:UI.btnStyle(),
    onClick:function(){ ACT.runTimeSeriesSingle(key(), zone()); }}),
  ui.Button({label:'Annual Cycle Chart', style:UI.btnStyle(),
    onClick:function(){ ACT.runAnnualCycle(zone()); }}),
]));

// Station Validation
panel.add(UI.card([
  UI.heading('📍  Station Validation'),
  UI.selectRow('Station', stnSel),
  ui.Button({label:'Validate Station vs Product', style:UI.btnStyle(),
    onClick:function(){
      ACT.runStationValidation(key(), stnSel.getValue());
    }}),
  ui.Button({label:'Categorical Metrics (POD / FAR / CSI)', style:UI.btnStyle(),
    onClick:function(){ ACT.runCategorical(key(), ref(), zone()); }}),
]));

// Export
panel.add(UI.card([
  UI.heading('⬆  Export / Assets'),
  ui.Button({label:'Export Mean → Drive', style:UI.btnStyle(),
    onClick:function(){
      ASS.exportMeanToDrive(key(), AREA.ROI);
      UI.setDone('Queued: mean → Drive');
    }}),
  ui.Button({label:'Export Mean → GEE Asset', style:UI.btnStyle(),
    onClick:function(){
      ASS.exportMeanAsAsset(key(), AREA.ROI);
      UI.setDone('Queued: mean → Asset');
    }}),
  ui.Button({label:'Export Climatology → GEE Asset', style:UI.btnStyle(),
    onClick:function(){
      ASS.exportClimatologyAsAsset(key(), AREA.ROI);
      UI.setDone('Queued: climatology → Asset');
    }}),
  ui.Button({label:'Export Bias Map → GEE Asset', style:UI.btnStyle(),
    onClick:function(){
      ASS.exportBiasAsAsset(key(), ref(), AREA.ROI);
      UI.setDone('Queued: bias → Asset');
    }}),
  UI.subLabel('Monitor progress in the Tasks tab ↑'),
]));

// Legend
panel.add(UI.card([
  UI.heading('🎨  Legend'),
  UI.makeLegend('Annual Total', VIS.annual.palette,  0,     2500, 'mm/yr'),
  UI.makeLegend('Mean Daily',   VIS.daily.palette,   0,     12,   'mm/day'),
  UI.makeLegend('Bias',         VIS.bias.palette,   -5,     5,    'mm/day'),
  UI.makeLegend('Correlation',  VIS.corr.palette,    0,     1,    'r'),
  UI.makeLegend('Trend',        VIS.trend.palette,  -0.05,  0.05, 'mm/d/yr'),
]));

// Product key
var keyWidgets = [UI.heading('Products')];
PKEYS.forEach(function(k) {
  keyWidgets.push(ui.Panel({
    widgets:[
      ui.Label('■',{color:PRODUCTS[k].color, fontSize:'14px', margin:'0 5px 0 0'}),
      ui.Label(k+'  '+PRODUCTS[k].res, {color:'#424242', fontSize:'10px', margin:'1px 0'}),
    ],
    layout:ui.Panel.Layout.flow('horizontal'),
    style:{margin:'1px 0'}
  }));
});
panel.add(UI.card(keyWidgets));

// Inspector
var inspectOut = ui.Label('👆 Click map to sample pixel', {
  fontSize:'10px', color:'#424242', whiteSpace:'pre'
});
panel.add(UI.card([UI.heading('🔍  Inspector'), inspectOut]));

ui.root.add(panel);

// ── Map click inspector ───────────────────────────────────────
Map.onClick(function(coords) {
  inspectOut.setValue('⟳ Sampling …');
  var k  = key();
  var pt = ee.Geometry.Point([coords.lon, coords.lat]);
  HAR.getMean(k, AREA.ROI).rename('precip_mm_day').reduceRegion({
    reducer:ee.Reducer.first(), geometry:pt, scale:CFG.targetScale,
  }).evaluate(function(res) {
    if (!res) { inspectOut.setValue('No data.'); return; }
    var v = res['precip_mm_day'];
    inspectOut.setValue(
      '📍 ' + coords.lat.toFixed(3) + '°N  ' + coords.lon.toFixed(3) + '°E\n' +
      k + ':  ' +
      (v != null ? (Math.round(v*100)/100)+' mm/day (LT mean)' : 'n/a')
    );
  });
  print(ui.Chart.image.series({
    imageCollection:HAR.getIC(k).select('precip_mm_day'),
    region:pt, reducer:ee.Reducer.first(),
    scale:CFG.targetScale, xProperty:'system:time_start',
  }).setSeriesNames([k]).setChartType('LineChart').setOptions({
    title:'Pixel Time Series  |  ' + k + '  |  ' +
          coords.lat.toFixed(2)+'°N '+coords.lon.toFixed(2)+'°E',
    vAxis:{title:'mm/day'},
    lineWidth:1.5, pointSize:2, colors:[PRODUCTS[k].color],
    legend:{position:'none'}, height:320,
  }));
});

// ── Boundary overlay ─────────────────────────────────────────
Map.addLayer(
  ee.Image().byte().paint({
    featureCollection:AREA.BOUNDARY, color:1, width:2
  }),
  {palette:['#FF5722'], opacity:0.9},
  '🗺 West Africa Boundary', true
);
Map.addLayer(STN.STATION_FC, {color:'#FFEB3B'}, '📍 Gauge Stations', true);
Map.setCenter(-5, 12, 5);

print('Dashboard ready.');
print('Select a product, then click any button to compute a layer.');