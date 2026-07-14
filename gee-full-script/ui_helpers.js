// ============================================================
// MODULE: ui_helpers
// UI colour tokens, widget factories, STATUS label
// ============================================================

// Colour tokens
exports.C = {
  bg        : '#F5F5F5',
  bgSection : '#FFFFFF',
  border    : '#D0D0D0',
  textH     : '#1565C0',
  textSub   : '#424242',
  textMuted : '#757575',
  accent    : '#1565C0',
};

exports.btnStyle = function() {
  return {
    stretch        : 'horizontal',
    margin         : '4px 0',
    padding        : '6px',
    backgroundColor: '#E0E0E0',
    color          : '#000000',
    border         : '1px solid #BDBDBD',
    fontWeight     : 'bold',
    textAlign      : 'center'
  };
};

exports.card = function(widgets) {
  return ui.Panel({
    widgets: widgets,
    style: {
      margin         : '6px 0',
      padding        : '8px',
      backgroundColor: '#FFFFFF',
      border         : '1px solid #D0D0D0'
    }
  });
};

exports.heading = function(text, color) {
  return ui.Label(text, {
    fontWeight:'bold', fontSize:'12px',
    color: color || '#1565C0',
    margin:'0 0 5px 0'
  });
};

exports.subLabel = function(text) {
  return ui.Label(text, {
    fontSize:'10px', color:'#757575', margin:'0 0 3px 0'
  });
};

exports.styledSelect = function(items, value) {
  return ui.Select({
    items:items, value:value,
    style:{stretch:'horizontal', fontSize:'12px'}
  });
};

exports.selectRow = function(labelTxt, selectWidget) {
  return ui.Panel({
    widgets: [
      ui.Label(labelTxt, {
        fontSize:'10px', fontWeight:'bold',
        color:'#e61c36', margin:'4px 0 2px 0',
        backgroundColor:'#f0f0f0'
      }),
      ui.Panel({
        widgets:[selectWidget],
        style:{
          backgroundColor:'#FFFFFF',
          border:'2px solid #42A5F5',
          padding:'2px', stretch:'horizontal'
        }
      })
    ],
    style:{margin:'0 0 6px 0', backgroundColor:'#f0f0f0'}
  });
};

// Shared STATUS label — required by both ui_panel and actions
// Because GEE caches modules, both get the same object instance
exports.STATUS = ui.Label(
  'Ready — select a product and click a button.', {
    fontSize:'11px', color:'#e61c36', fontWeight:'bold',
    whiteSpace:'pre', margin:'4px 0 2px 0',
    backgroundColor:'#f0f0f0'
  }
);

exports.setStatus = function(msg) { exports.STATUS.setValue('⟳ ' + msg); };
exports.setDone   = function(msg) { exports.STATUS.setValue('✓ ' + msg); };
exports.setError  = function(msg) { exports.STATUS.setValue('✗ ' + msg); };

exports.makeLegend = function(title, palette, lo, hi, unit) {
  return ui.Panel({
    widgets:[
      ui.Label(title, {
        fontSize:'10px', fontWeight:'bold',
        color:'#1565C0', margin:'0 0 2px 0'
      }),
      ui.Thumbnail({
        image : ee.Image.pixelLonLat().select(0),
        params: {bbox:[0,0,1,0.1], dimensions:'170x12',
          format:'png', min:0, max:1, palette:palette},
        style : {stretch:'horizontal', margin:'0 0 2px 0'}
      }),
      ui.Panel({
        widgets:[
          ui.Label(lo+' '+unit,
            {fontSize:'9px', color:'#546E7A', margin:'0'}),
          ui.Label(hi+' '+unit,
            {fontSize:'9px', color:'#546E7A',
             margin:'0', textAlign:'right'}),
        ],
        layout:ui.Panel.Layout.flow('horizontal'),
        style:{stretch:'horizontal'}
      })
    ],
    style:{margin:'0 0 5px 0', backgroundColor:'#f0f0f0'}
  });
};