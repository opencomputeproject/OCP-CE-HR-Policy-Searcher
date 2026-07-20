// Pure helpers for the world map: binning, the atlas/coverage join, and the
// small set of tracked places too small to click reliably on a 110m polygon.
// Kept dependency-free so they're trivial to unit test without rendering.

export const BIN_KEYS = ['untracked', 't0', 'b1', 'b2', 'b3'];

export const BIN_LABELS = {
  untracked: 'Not yet tracked',
  t0: 'Tracked, nothing found yet',
  b1: '1–5 policies',
  b2: '6–15 policies',
  b3: '16+ policies',
};

// Two grays, deliberately: "untracked" (no coverage record at all - we have
// not looked) must never be visually or semantically confused with "t0"
// (a coverage record exists, sources are watched, nothing has surfaced yet).
export function binForCoverage(entry) {
  if (!entry) return 'untracked';
  if (entry.policies === 0) return 't0';
  if (entry.policies <= 5) return 'b1';
  if (entry.policies <= 15) return 'b2';
  return 'b3';
}

// Countries whose 110m polygon exists but is too small to hover/click
// reliably, plus countries absent from the 110m atlas entirely. Both get a
// dot marker layered on top so precision never gates access to a tracked
// place. Singapore's coordinates are pinned to this map's own projection
// (Equal Earth, viewBox 0 0 960 421.5) - not a general-purpose lookup.
export const MICRO_AREA_THRESHOLD = 30;
export const OFF_ATLAS_MICROSTATES = {
  702: { name: 'Singapore', cx: 762.1, cy: 231.0 },
};

// Joins the static world-atlas geometry to a live /api/coverage response,
// keyed by iso_numeric (the pinned join key). Every atlas country appears
// exactly once, tagged with its bin; countries with no coverage record are
// 'untracked' rather than dropped, so the map still draws their outline.
//
// Three de-facto territories (Kosovo, N. Cyprus, Somaliland) are drawn in
// the 110m atlas with an empty id - world-atlas carries no numeric code for
// them. Per the pinned design decision, contested territories with no
// iso_numeric render list-only in the off-map tray, never as a border fill
// ("loses no data, takes no cartographic stance"). The registry backs this:
// a resolved country with a falsy iso_numeric always routes to `supranational`,
// never `countries`, so these ids could never join to a coverage record
// anyway - excluding them here also sidesteps a React key collision, since
// all three would otherwise share the key "".
export function joinCountries(worldCountries, coverageCountries) {
  const byIso = new Map();
  for (const c of coverageCountries || []) {
    byIso.set(String(c.iso_numeric), c);
  }

  return worldCountries
    .filter((geo) => geo.id)
    .map((geo) => {
      const cov = byIso.get(geo.id) || null;
      return { geo, cov, bin: binForCoverage(cov) };
    });
}

// Parses an SVG path `d` string's coordinate pairs to find its bounding-box
// width, in the same world units the atlas polygon is drawn in. The 110m
// atlas paths (d3.geoPath output) are straight M/L/Z segments only - no
// curves or H/V shorthand - so every pair of consecutive numbers is an
// (x, y) vertex and this simple scan is exact, not an approximation.
export function pathBoundingWidth(d) {
  if (!d) return null;
  const nums = d.match(/-?\d+\.?\d*(?:e-?\d+)?/g);
  if (!nums || nums.length < 2) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  for (let i = 0; i < nums.length - 1; i += 2) {
    const x = parseFloat(nums[i]);
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
  }
  if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return null;
  return maxX - minX;
}

// Dot markers for tracked places a click can't reliably land on: on-atlas
// polygons under the area threshold, plus places absent from the atlas
// entirely (Singapore). Untracked microstates get no marker - there's no
// coverage record to show, and the polygon (however tiny) already renders.
//
// `polyWidth` (world units) lets the renderer hide an on-atlas dot once its
// own polygon has grown large enough on screen to click directly - see
// isMarkerHidden below. Off-atlas markers (no polygon exists at all) get
// `polyWidth: null` and must never be hidden by that check.
export function computeMicroMarkers(worldCountries, coverageCountries) {
  const byId = new Map(worldCountries.map((c) => [c.id, c]));
  const byIso = new Map((coverageCountries || []).map((c) => [String(c.iso_numeric), c]));
  const markers = [];

  for (const cov of coverageCountries || []) {
    const id = String(cov.iso_numeric);
    const geo = byId.get(id);
    if (geo && geo.area >= MICRO_AREA_THRESHOLD) continue;
    const coords = geo || OFF_ATLAS_MICROSTATES[id];
    if (!coords) continue;
    markers.push({
      id,
      name: cov.name,
      cx: coords.cx,
      cy: coords.cy,
      bin: binForCoverage(byIso.get(id)),
      polyWidth: geo ? pathBoundingWidth(geo.d) : null,
    });
  }

  return markers;
}

// Micro-marker dots are drawn in WORLD units (the atlas viewBox), so at
// r=4.2 flat they'd inflate into a giant disc as the viewBox zoom narrows.
// Scaling the radius by the current viewBox width against the full-world
// width keeps the dot a constant size on screen at any zoom level.
export const MICRO_MARKER_BASE_RADIUS = 4.2;
export const MICRO_MARKER_BASE_WIDTH = 960;

export function microMarkerRadius(viewBoxWidth) {
  return MICRO_MARKER_BASE_RADIUS * (viewBoxWidth / MICRO_MARKER_BASE_WIDTH);
}

// Once an on-atlas marker's own polygon is comfortably clickable on screen,
// the dot on top of it is redundant clutter - hide it. Screen width is
// estimated from the polygon's world-unit bounding width against how many
// screen pixels the current viewBox spans. Off-atlas markers (polyWidth
// null - e.g. Singapore) have no polygon to fall back on, so they are never
// hidden, at any zoom: the dot is the only way to reach them.
// Screen width (px) at which an on-atlas polygon is a comfortable click
// target on its own, so its helper dot can be hidden. Kept a little below a
// fingertip target (~44px) so small islands (Ireland's outline caps at ~48px
// even at max zoom) actually cross it and their dot disappears when zoomed
// in, rather than sitting exactly on the boundary and never hiding.
export const MARKER_HIDE_THRESHOLD_PX = 40;

export function isMarkerHidden(marker, viewBoxWidth, svgPxWidth) {
  if (marker.polyWidth == null) return false;
  if (!viewBoxWidth || !svgPxWidth) return false;
  const screenWidth = (marker.polyWidth * svgPxWidth) / viewBoxWidth;
  return screenWidth > MARKER_HIDE_THRESHOLD_PX;
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
}

// Joins one country's admin-1 geometry (frontend/src/assets/admin1/<iso>.json
// `units[]`) to a live /api/coverage/children `children[]` response, keyed by
// ISO 3166-2 `code`. Mirrors joinCountries: every geometry unit appears
// exactly once, tagged with its bin. A unit absent from `children[]` (the
// API omits children with zero data) is 'untracked' rather than dropped, so
// the country outline still draws in full.
export function joinAdmin1(units, children) {
  const byCode = new Map();
  for (const c of children || []) {
    byCode.set(c.code, c);
  }

  return (units || []).map((unit) => {
    const cov = byCode.get(unit.code) || null;
    return { unit, cov, bin: binForCoverage(cov) };
  });
}
