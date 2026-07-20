# World Map Architecture

The five decisions a maintainer needs to understand before changing the map. Written at delivery
time (2026-07) by the team that built it; everything here is load-bearing.

## 1. The jurisdiction registry is the single source of truth for places

`config/jurisdictions.yaml` + `src/core/jurisdictions.py`. Every place the system knows -
countries, US states, subnational regions, supranational bodies - is one registry row with a
slug, kind, aliases, and join keys. Policy jurisdiction strings are free text written by an LLM;
`resolve_text()` maps that mess ("Sweden (EU)", "Minnesota, USA", "Germany (Peine, Lower
Saxony)") onto registry rows and never raises.

Two join keys matter: `iso_numeric` joins a country row to its world-atlas shape, and the ISO
3166-2 `code` joins a subnational row to its admin-1 shape. If a place is missing from the map,
the fix is almost always a registry row, not map code.

The guardrail test `test_every_domain_slug_resolves` globs every domain config and fails if a
source references a region slug with no registry row - new sources cannot silently drift from
the map.

## 2. Coverage is computed at request time from the registry; totals must reconcile

`GET /api/coverage` buckets every stored policy and configured source by registry resolution
(rolling subnational up to the country); `GET /api/coverage/children?parent=<slug>` re-buckets
one country without the roll-up, splitting `national` vs `children`. The invariant, pinned by
tests: `national + sum(children) == the country's world-view total`. Every policy lands somewhere;
jurisdictions with no shape (EU, Kosovo) go to the off-map bucket rather than vanishing.

There is no coverage table and no backfill job - the registry made them unnecessary. Do not add
one without measuring first; at current volumes the request-time computation is milliseconds.

## 3. Geometry is precomputed, projected SVG - no map library, no tiles, no keys

`frontend/src/assets/worldAtlas110m.json` (~130 KB) holds world-atlas 110m TopoJSON decoded and
projected to Equal Earth at build-tooling time; the React components render plain `<path>`
elements from it. Per-country admin-1 files live in `frontend/src/assets/admin1/<iso>.json`
(Natural Earth / US Census / geoBoundaries CC BY 4.0 - attribution is rendered in the UI footer
and must stay) and lazy-load via dynamic `import()` only when a country is drilled.

Hard-won detail: TopoJSON rings that cross the antimeridian (Russia, Fiji) must be split at
±180° during asset generation or they smear across the projection. If a country ever renders as
a horizontal band, look at the asset, not the projection.

## 4. Drillability is data-driven, not hand-picked

`frontend/src/config/drillableCountries.js` maps iso -> { slug, load } for countries that have
admin-1 geometry. A country is drillable when it appears there AND its coverage entry has
`children_with_data > 0`. Shipping geometry for a new country (Canada, UK, India, Australia,
Switzerland, UAE already have subnational data waiting) is: generate the asset, add one loader
line. No UI changes - the country lights up on its own.

## 5. The map keeps a real-pointer test, permanently

The pan/zoom layer once captured the pointer on every press, which silently swallowed all real
clicks - while every synthetic-event test passed, because `fireEvent` bypasses pointer capture.
The first real user was the first real test. The rule that came out of it: any change to the
map's pointer interactions must be verified with a real-input Playwright run (click -> panel,
double-click -> drill, drag -> pan), not only the RTL suite. Synthetic-event suites are
structurally blind to pointer-capture bugs.

## Related contracts elsewhere

- `place=<slug>` on `GET /api/policies` - descendant-inclusive for countries, exact otherwise
  (`src/api/routes/policies.py`).
- `AdminGateMiddleware` (`src/api/app.py`) - ADMIN_TOKEN gates non-GET `/api`; unset means
  loopback-only, and forwarded headers count as remote (reverse-proxy topology).
- Deployment seeding: `python -m src.output.import_sheet` populates the store from the Google
  Sheets Staging worksheet (`docs: README "Google Sheets Setup"`).
