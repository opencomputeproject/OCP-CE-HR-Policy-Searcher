import React from 'react';
import { pluralize } from '../utils/mapCoverage';

// Honest coverage, stated up front: sets expectations before anyone clicks a
// gray country, so an untracked place reads as "not yet looked" rather than
// a broken map.
function CoverageStatStrip({ totals, placeCount }) {
  return (
    <div className="wm-stat-strip">
      <div className="wm-stat">
        <b>{totals.sources.toLocaleString()}</b>
        <span>{pluralize(totals.sources, 'tracked source')}</span>
      </div>
      <div className="wm-stat">
        <b>{placeCount.toLocaleString()}</b>
        <span>{pluralize(placeCount, 'place')} with tracked coverage</span>
      </div>
      <div className="wm-stat">
        <b>{totals.policies.toLocaleString()}</b>
        <span>{pluralize(totals.policies, 'policy', 'policies')} found so far</span>
      </div>
    </div>
  );
}

export default CoverageStatStrip;
