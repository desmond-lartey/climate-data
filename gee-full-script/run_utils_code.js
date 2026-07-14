// ============================================================
// MAIN — West Africa Precipitation Assessment
// All logic lives in utils/ modules.
// To change study area, products or date range:
//   edit utils/config  or  utils/study_area only.
// ============================================================

// Loading ui_panel triggers all modules in dependency order:
// config → products → harmonise → study_area → stations
// → ui_helpers → assets_io → actions → ui_panel
// The panel wires all buttons and adds all map layers.

require('users/Desmond/climate_studies:utils/ui_panel');