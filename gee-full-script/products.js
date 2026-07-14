// ============================================================
// MODULE: products
// Precipitation product catalogue and keys list
// ============================================================

exports.PRODUCTS = {

  CHIRPS: {
    collection : 'UCSB-CHG/CHIRPS/DAILY',
    band       : 'precipitation',
    scaleFactor: 1.0,
    isMonthly  : false,
    specialFn  : null,
    type       : 'Satellite-gauge',
    res        : '0.05°',
    color      : '#2196F3',
  },

  PERSIANN_CDR: {
    collection : 'NOAA/PERSIANN-CDR',
    band       : 'precipitation',
    scaleFactor: 1.0,
    isMonthly  : false,
    specialFn  : null,
    type       : 'Satellite',
    res        : '0.25°',
    color      : '#FF9800',
  },

  GPM_IMERG: {
    collection : 'NASA/GPM_L3/IMERG_MONTHLY_V07',
    band       : 'precipitation',
    scaleFactor: 24.0,
    isMonthly  : true,
    specialFn  : null,
    type       : 'Satellite-gauge',
    res        : '0.1°',
    color      : '#F44336',
  },

  ERA5_LAND: {
    collection : 'ECMWF/ERA5_LAND/MONTHLY_AGGR',
    band       : 'total_precipitation_sum',
    scaleFactor: null,
    isMonthly  : true,
    specialFn  : 'ERA5_MON',
    type       : 'Reanalysis',
    res        : '0.1°',
    color      : '#9C27B0',
  },

  MERRA2: {
    collection : 'NASA/GSFC/MERRA/flx/2',
    band       : 'PRECTOTCORR',
    scaleFactor: 86400.0,
    isMonthly  : false,
    specialFn  : null,
    type       : 'Reanalysis',
    res        : '~0.5°',
    color      : '#E91E63',
  },

  TERRACLIMATE: {
    collection : 'IDAHO_EPSCOR/TERRACLIMATE',
    band       : 'pr',
    scaleFactor: null,
    isMonthly  : true,
    specialFn  : 'TERRA',
    type       : 'Reanalysis-interp',
    res        : '~0.04°',
    color      : '#00BCD4',
  },
};

exports.PKEYS = Object.keys(exports.PRODUCTS);