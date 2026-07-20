import React from 'react';
import { pluralize } from '../utils/mapCoverage';

// Click commits: a side panel, never a modal, so the map stays explorable
// while a result is open. The primary action is "View {n} found policies" -
// jumping straight to what has already been found for this place - via
// `onViewPlacePolicies({ slug, name })`. The paid "Search {place}" scan
// action still exists but is demoted to a secondary/link-styled action
// (label: "Scan {name} for new policies"), and its visibility is controlled
// by `showScanAction` (another workstream sets it false for visitors).
// `onExplore` is optional: WorldMap only passes it for a country with
// admin-1 geometry AND state/province-level data (see DRILLABLE_COUNTRIES in
// config/drillableCountries.js), so most countries' panels render exactly
// as before.
function CountryPanel({
  selection, onClose, onSearchPlace, onExplore,
  onViewPlacePolicies, showScanAction = true,
}) {
  const isOpen = Boolean(selection);
  const tracked = selection && (selection.sources > 0 || selection.policies > 0);
  const hasFoundPolicies = selection && selection.policies > 0;

  return (
    <aside
      className={`wm-panel${isOpen ? ' wm-panel-open' : ''}`}
      aria-label="Place details"
      aria-hidden={!isOpen}
    >
      <button type="button" className="wm-panel-close" aria-label="Close panel" onClick={onClose}>
        &times;
      </button>
      {selection && (
        <div className="wm-panel-body">
          <h3>{selection.name}</h3>
          {tracked ? (
            <>
              <div className="wm-panel-stats">
                {selection.sources} tracked {pluralize(selection.sources, 'source')}
                {' · '}
                {selection.policies} {pluralize(selection.policies, 'policy', 'policies')} found
              </div>
              {selection.topPolicyNames.length > 0 ? (
                <>
                  {selection.topPolicyNames.map((name) => (
                    <div className="wm-panel-policy" key={name}>{name}</div>
                  ))}
                  {selection.policies > selection.topPolicyNames.length && (
                    <p className="wm-panel-note">
                      + {selection.policies - selection.topPolicyNames.length} more in the
                      results list below.
                    </p>
                  )}
                </>
              ) : (
                <p className="wm-panel-empty">
                  Sources are watched here, but no qualifying policy has surfaced yet.
                  A fresh scan may change that.
                </p>
              )}
              {hasFoundPolicies && (
                <button
                  type="button"
                  className="wm-panel-cta"
                  onClick={() => onViewPlacePolicies({ slug: selection.slug, name: selection.name })}
                >
                  View {selection.policies} found {pluralize(selection.policies, 'policy', 'policies')}
                </button>
              )}
              {showScanAction && (
                <button
                  type="button"
                  className="wm-panel-cta-link"
                  onClick={() => onSearchPlace(selection.name)}
                >
                  Scan {selection.name} for new policies
                </button>
              )}
              {onExplore && (
                <button
                  type="button"
                  className="wm-panel-cta wm-panel-cta-secondary"
                  onClick={onExplore}
                >
                  Explore {selection.name}&rsquo;s regions &rarr;
                </button>
              )}
            </>
          ) : (
            <>
              <p className="wm-panel-empty">
                No tracked sources yet. Searching still works - finding sources here
                is how coverage grows.
              </p>
              {showScanAction && (
                <button
                  type="button"
                  className="wm-panel-cta-link"
                  onClick={() => onSearchPlace(selection.name)}
                >
                  Scan {selection.name} for new policies
                </button>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}

export default CountryPanel;
