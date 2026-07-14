// ============================================================
// MODULE: stations
// Gauge station metadata and observation data
// ============================================================

exports.STATIONS_RAW = [
  {id:'WA001', name:'Dakar',       lon:-17.47, lat:14.73, elev:27},
  {id:'WA002', name:'Bamako',      lon:-7.95,  lat:12.65, elev:381},
  {id:'WA003', name:'Ouagadougou', lon:-1.52,  lat:12.36, elev:306},
  {id:'WA004', name:'Niamey',      lon:2.17,   lat:13.51, elev:222},
  {id:'WA005', name:'Abuja',       lon:7.33,   lat:9.07,  elev:476},
  {id:'WA006', name:'Accra',       lon:-0.17,  lat:5.56,  elev:61},
  {id:'WA007', name:'Abidjan',     lon:-3.93,  lat:5.35,  elev:7},
  {id:'WA008', name:'Conakry',     lon:-13.67, lat:9.53,  elev:27},
  {id:'WA009', name:'Freetown',    lon:-13.23, lat:8.49,  elev:27},
  {id:'WA010', name:'Monrovia',    lon:-10.80, lat:6.30,  elev:23},
  {id:'WA011', name:'Lomé',        lon:1.22,   lat:6.13,  elev:25},
  {id:'WA012', name:'Cotonou',     lon:2.42,   lat:6.37,  elev:9},
  {id:'WA013', name:'Kano',        lon:8.52,   lat:12.05, elev:481},
  {id:'WA014', name:'Kumasi',      lon:-1.62,  lat:6.69,  elev:287},
  {id:'WA015', name:'Banjul',      lon:-16.68, lat:13.45, elev:28},
  {id:'WA016', name:'Nouakchott',  lon:-15.97, lat:18.07, elev:4},
];

exports.STATION_FC = ee.FeatureCollection(
  exports.STATIONS_RAW.map(function(s) {
    return ee.Feature(ee.Geometry.Point([s.lon, s.lat]), {
      station_id:  s.id,
      station_name:s.name,
      lon:s.lon, lat:s.lat, elevation_m:s.elev,
    });
  })
);

exports.OBS_FC = ee.FeatureCollection(
  'projects/ee-desmond/assets/gpcc_obs_2001_2020'
).map(function(f) {
  return f.set({
    year      : ee.Number.parse(f.get('year')).toInt(),
    month     : ee.Number.parse(f.get('month')).toInt(),
    obs_mm_day: ee.Number.parse(f.get('obs_mm_day')),
  });
});

print('GPCC observations loaded:', exports.OBS_FC.size(), 'records');