import React from 'react';
import { pluralize } from '../utils/mapCoverage';
import CityChips from './CityChips';

// Country view's unit/federal panel - mirrors CountryPanel exactly (name,
// "{sources} sources · {policies} policies", top policy names, a primary
// "View {n} found policies" CTA via `onViewPlacePolicies({ slug, name })`,
// and the demoted/optional "Scan {name} for new policies" scan action
// gated by `showScanAction`), plus two things a state/province panel needs
// that the world panel does not: a federal badge (so a nationwide law is
// never read as a single-region one) and optional city chips.
function RegionPanel({
  selection, onClose, onSearchPlace, onViewPlacePolicies, showScanAction = true,
}) {
  const isOpen = Boolean(selection);
  const tracked = selection && (selection.sources > 0 || selection.policies > 0);
  const hasFoundPolicies = selection && selection.policies > 0;
  const classes = ['wm-panel'];
  if (isOpen) classes.push('wm-panel-open');
  if (selection?.isFederal) classes.push('wm-panel-federal');

  return (
    <aside
      className={classes.join(' ')}
      aria-label="Region details"
      aria-hidden={!isOpen}
    >
      <button type="button" className="wm-panel-close" aria-label="Close panel" onClick={onClose}>
        &times;
      </button>
      {selection && (
        <div className="wm-panel-body">
          {selection.isFederal && (
            <span className="wm-federal-badge">Federal / nationwide</span>
          )}
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
              <CityChips cities={selection.cities} />
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
            </>
          ) : (
            <>
              <p className="wm-panel-empty">
                No tracked sources yet. Searching still works - finding sources here
                is how coverage grows.
              </p>
              <CityChips cities={selection.cities} />
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

export default RegionPanel;
