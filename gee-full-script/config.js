// ============================================================
// MODULE: config
// Global configuration, date ranges, visualisation params
// ============================================================

exports.CFG = {
  startDate   : '2001-01-01',
  endDate     : '2020-12-31',
  targetScale : 25000,
  chartScale  : 50000,
  rainThresh  : 1.0,
  defaultProd : 'CHIRPS',
  defaultRef  : 'GPM_IMERG',
  exportFolder: 'WA_Precip_Assets',
  assetFolder : 'projects/ee-desmond/assets/',
};

exports.START_YR = 2001;
exports.END_YR   = 2020;

exports.VIS = {
  annual: {min:0,    max:2500,  palette:['#FFFDE7','#FFF59D','#FFCC02','#FF8F00','#E65100']},
  daily : {min:0,    max:12,    palette:['#E3F2FD','#90CAF9','#1565C0','#0D47A1','#01002E']},
  bias  : {min:-5,   max:5,     palette:['#B71C1C','#EF9A9A','#FFFFFF','#90CAF9','#0D47A1']},
  pbias : {min:-80,  max:80,    palette:['#B71C1C','#FFCDD2','#FFFFFF','#BBDEFB','#0D47A1']},
  corr  : {min:0,    max:1,     palette:['#FFFFFF','#C8E6C9','#66BB6A','#2E7D32','#1B5E20']},
  trend : {min:-0.05,max:0.05,  palette:['#4E342E','#FF8A65','#FFFFFF','#80DEEA','#006064']},
  pod   : {min:0,    max:1,     palette:['#FFF8E1','#FFE082','#FFB300','#FF6F00']},
  far   : {min:0,    max:1,     palette:['#E8F5E9','#A5D6A7','#388E3C','#1B5E20']},
};