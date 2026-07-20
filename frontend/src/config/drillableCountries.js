// Bridges a gap in the /api/coverage contract: country entries carry no
// slug (the field /api/coverage/children needs), and a slug is not always
// derivable from the country name ("United States" -> "us"). Keyed by
// iso_numeric - the same join key /api/coverage already uses - so lookup
// from a WorldMap selection is a single map read.
//
// A country only gets the "Explore {country}'s regions" affordance when it
// is BOTH drillable per the API (children_with_data > 0) AND listed here
// (we have both a slug to query and admin-1 geometry to draw). Adding a new
// country needs one line here plus its geometry file under
// src/assets/admin1/<iso_numeric>.json - no other code change.
//
// `load` is a dynamic import so admin-1 geometry (up to ~340KB per
// country) never lands in the initial bundle - it is fetched only when a
// user actually drills into that specific country.
const DRILLABLE_COUNTRIES = {
  '840': { slug: 'us', load: () => import('../assets/admin1/840.json') },
  '276': { slug: 'germany', load: () => import('../assets/admin1/276.json') },
  '056': { slug: 'belgium', load: () => import('../assets/admin1/056.json') },
};

export default DRILLABLE_COUNTRIES;
