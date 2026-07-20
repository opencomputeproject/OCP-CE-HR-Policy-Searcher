import {
  MARKER_HIDE_THRESHOLD_PX,
  MICRO_MARKER_BASE_RADIUS,
  OFF_ATLAS_MICROSTATES,
  binForCoverage,
  computeMicroMarkers,
  isMarkerHidden,
  joinAdmin1,
  joinCountries,
  microMarkerRadius,
  pathBoundingWidth,
  pluralize,
} from './mapCoverage';

const WORLD = [
  { id: '840', name: 'United States of America', d: 'M0,0Z', cx: 205.8, cy: 84, area: 7642.9 },
  { id: '752', name: 'Sweden', d: 'M1,1Z', cx: 500, cy: 60, area: 360.7 },
  { id: '442', name: 'Luxembourg', d: 'M2,2Z', cx: 480, cy: 90, area: 3.1 },
  { id: '', name: 'Kosovo', d: 'M3,3Z', cx: 529.6, cy: 88, area: 9.2 },
  { id: '', name: 'Somaliland', d: 'M4,4Z', cx: 604.4, cy: 198, area: 135.1 },
];

// Wide-but-tiny-area outline (e.g. a sliver-shaped territory) - a second,
// standalone atlas used only by the polyWidth/hide-threshold tests below so
// it doesn't perturb the shared WORLD fixture's counts used elsewhere.
const WORLD_WITH_SLIVER = [
  ...WORLD,
  {
    id: '074', name: 'Bouvet Island', d: 'M10,10L30,12L28,30L9,28Z', cx: 20, cy: 20, area: 5,
  },
];

describe('binForCoverage', () => {
  it('is untracked with no coverage record - the first gray', () => {
    expect(binForCoverage(null)).toBe('untracked');
    expect(binForCoverage(undefined)).toBe('untracked');
  });

  it('is t0 for a tracked country with zero policies - the second gray', () => {
    expect(binForCoverage({ sources: 3, policies: 0 })).toBe('t0');
  });

  it('bins by policy count thresholds, never confusing t0 with untracked', () => {
    expect(binForCoverage({ sources: 1, policies: 1 })).toBe('b1');
    expect(binForCoverage({ sources: 1, policies: 5 })).toBe('b1');
    expect(binForCoverage({ sources: 1, policies: 6 })).toBe('b2');
    expect(binForCoverage({ sources: 1, policies: 15 })).toBe('b2');
    expect(binForCoverage({ sources: 1, policies: 16 })).toBe('b3');
  });
});

describe('joinCountries', () => {
  it('keeps every atlas country, tagging untracked ones rather than dropping them', () => {
    const joined = joinCountries(WORLD, [
      { iso_numeric: '840', name: 'United States', sources: 162, policies: 23 },
    ]);
    expect(joined).toHaveLength(3);
    expect(joined.find((j) => j.geo.id === '840').bin).toBe('b3');
    expect(joined.find((j) => j.geo.id === '752').bin).toBe('untracked');
    expect(joined.find((j) => j.geo.id === '752').cov).toBeNull();
  });

  it('joins on iso_numeric even when the API sends it as a number', () => {
    const joined = joinCountries(WORLD, [{ iso_numeric: 840, name: 'US', sources: 1, policies: 0 }]);
    expect(joined.find((j) => j.geo.id === '840').bin).toBe('t0');
  });

  it('excludes empty-id contested territories rather than fill them as untracked', () => {
    // Kosovo/N. Cyprus/Somaliland carry no iso_numeric in world-atlas - the
    // pinned decision is list-only, off-map, never a border fill. Rendering
    // them here would also collide on the shared key "".
    const joined = joinCountries(WORLD, []);
    expect(joined.map((j) => j.geo.name)).not.toEqual(
      expect.arrayContaining(['Kosovo', 'Somaliland']),
    );
    expect(joined).toHaveLength(3);
  });
});

describe('computeMicroMarkers', () => {
  it('adds a dot for a tiny tracked polygon but not an untracked one', () => {
    const markers = computeMicroMarkers(WORLD, [
      { iso_numeric: '442', name: 'Luxembourg', sources: 1, policies: 0 },
    ]);
    expect(markers).toHaveLength(1);
    expect(markers[0]).toMatchObject({ id: '442', name: 'Luxembourg', bin: 't0' });
  });

  it('skips a normal-sized tracked country - its polygon is clickable on its own', () => {
    const markers = computeMicroMarkers(WORLD, [
      { iso_numeric: '840', name: 'United States', sources: 162, policies: 23 },
    ]);
    expect(markers).toHaveLength(0);
  });

  it('places an off-atlas microstate using its pinned fallback coordinates', () => {
    const singapore = Object.keys(OFF_ATLAS_MICROSTATES)[0];
    const markers = computeMicroMarkers(WORLD, [
      { iso_numeric: singapore, name: 'Singapore', sources: 2, policies: 0 },
    ]);
    expect(markers).toHaveLength(1);
    expect(markers[0].cx).toBe(OFF_ATLAS_MICROSTATES[singapore].cx);
  });

  it('sets polyWidth from the polygon bounding box for an on-atlas marker', () => {
    const markers = computeMicroMarkers(WORLD_WITH_SLIVER, [
      { iso_numeric: '074', name: 'Bouvet Island', sources: 1, policies: 0 },
    ]);
    expect(markers).toHaveLength(1);
    // d = M10,10 L30,12 L28,30 L9,28 Z -> x ranges 9..30
    expect(markers[0].polyWidth).toBeCloseTo(21, 5);
  });

  it('sets polyWidth to null for an off-atlas marker - it has no polygon to measure', () => {
    const singapore = Object.keys(OFF_ATLAS_MICROSTATES)[0];
    const markers = computeMicroMarkers(WORLD, [
      { iso_numeric: singapore, name: 'Singapore', sources: 2, policies: 0 },
    ]);
    expect(markers[0].polyWidth).toBeNull();
  });
});

describe('pathBoundingWidth', () => {
  it('finds the x-axis bounding width from a straight-segment path', () => {
    expect(pathBoundingWidth('M10,10L30,12L28,30L9,28Z')).toBeCloseTo(21, 5);
  });

  it('returns 0 for a single-point path', () => {
    expect(pathBoundingWidth('M2,2Z')).toBe(0);
  });

  it('returns null for an empty or missing path', () => {
    expect(pathBoundingWidth('')).toBeNull();
    expect(pathBoundingWidth(undefined)).toBeNull();
  });
});

describe('microMarkerRadius', () => {
  it('is the base radius at the full-world viewBox width', () => {
    expect(microMarkerRadius(960)).toBeCloseTo(MICRO_MARKER_BASE_RADIUS, 5);
  });

  it('scales down proportionally to viewBox width as the map zooms in', () => {
    expect(microMarkerRadius(480)).toBeCloseTo(MICRO_MARKER_BASE_RADIUS * 0.5, 5);
    expect(microMarkerRadius(240)).toBeCloseTo(MICRO_MARKER_BASE_RADIUS * 0.25, 5);
  });
});

describe('isMarkerHidden', () => {
  const onAtlasMarker = { id: '074', polyWidth: 21 };
  const offAtlasMarker = { id: '702', polyWidth: null };

  it('hides an on-atlas marker once its polygon is comfortably clickable on screen', () => {
    // 21 world units * 1000 screen px / 200 viewBox width = 105px > 48px
    expect(isMarkerHidden(onAtlasMarker, 200, 1000)).toBe(true);
  });

  it('keeps an on-atlas marker visible while its polygon is still too small to click', () => {
    // 21 * 800 / 960 = 17.5px < 48px
    expect(isMarkerHidden(onAtlasMarker, 960, 800)).toBe(false);
  });

  it('sits right at the threshold boundary correctly', () => {
    // polyWidth * svgPxWidth / viewBoxWidth == MARKER_HIDE_THRESHOLD_PX exactly
    const viewBoxWidth = 100;
    const svgPxWidth = (MARKER_HIDE_THRESHOLD_PX * viewBoxWidth) / onAtlasMarker.polyWidth;
    expect(isMarkerHidden(onAtlasMarker, viewBoxWidth, svgPxWidth)).toBe(false);
  });

  it('never hides an off-atlas marker (polyWidth null), at any zoom', () => {
    expect(isMarkerHidden(offAtlasMarker, 120, 2000)).toBe(false);
    expect(isMarkerHidden(offAtlasMarker, 960, 300)).toBe(false);
  });

  it('does not hide anything before the svg has measured a real pixel width', () => {
    expect(isMarkerHidden(onAtlasMarker, 200, 0)).toBe(false);
  });
});

describe('joinAdmin1', () => {
  const UNITS = [
    { code: 'BE-BRU', name: 'Brussels', d: 'M0,0Z', cx: 1, cy: 1, area: 100 },
    { code: 'BE-VLG', name: 'Flanders', d: 'M1,1Z', cx: 2, cy: 2, area: 200 },
    { code: 'BE-WAL', name: 'Wallonia', d: 'M2,2Z', cx: 3, cy: 3, area: 300 },
  ];

  it('keeps every geometry unit, tagging children with no data as untracked rather than dropping them', () => {
    const joined = joinAdmin1(UNITS, [
      { slug: 'belgium-bru', name: 'Brussels', kind: 'subnational', code: 'BE-BRU', sources: 1, policies: 3 },
    ]);
    expect(joined).toHaveLength(3);
    expect(joined.find((j) => j.unit.code === 'BE-BRU').bin).toBe('b1');
    expect(joined.find((j) => j.unit.code === 'BE-VLG').bin).toBe('untracked');
    expect(joined.find((j) => j.unit.code === 'BE-VLG').cov).toBeNull();
  });

  it('joins on the ISO 3166-2 code, not name or slug', () => {
    const joined = joinAdmin1(UNITS, [
      { slug: 'belgium-wal', name: 'Wallonia (region)', kind: 'subnational', code: 'BE-WAL', sources: 2, policies: 4 },
    ]);
    expect(joined.find((j) => j.unit.code === 'BE-WAL').bin).toBe('b1');
    expect(joined.find((j) => j.unit.code === 'BE-WAL').cov.name).toBe('Wallonia (region)');
  });

  it('handles an empty children list without dropping any unit', () => {
    const joined = joinAdmin1(UNITS, []);
    expect(joined).toHaveLength(3);
    expect(joined.every((j) => j.bin === 'untracked')).toBe(true);
  });
});

describe('pluralize', () => {
  it('picks the singular for exactly one', () => {
    expect(pluralize(1, 'policy', 'policies')).toBe('policy');
  });

  it('picks the plural otherwise, including zero', () => {
    expect(pluralize(0, 'policy', 'policies')).toBe('policies');
    expect(pluralize(2, 'policy', 'policies')).toBe('policies');
  });

  it('defaults the plural to singular + s', () => {
    expect(pluralize(2, 'source')).toBe('sources');
  });
});
