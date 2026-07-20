import React from 'react';
import { pluralize } from '../utils/mapCoverage';

// Hover previews, click commits: a name, counts, and one sample policy -
// enough to decide whether to click, never enough to replace the panel.
function MapTooltip({ hover }) {
  if (!hover) return null;
  const { x, y, name, cov } = hover;

  return (
    <div className="wm-tooltip" role="status" style={{ left: x, top: y }}>
      <div className="wm-tooltip-name">{name}</div>
      {cov ? (
        <>
          <div className="wm-tooltip-stats">
            {cov.sources} {pluralize(cov.sources, 'source')}
            {' · '}
            {cov.policies} {pluralize(cov.policies, 'policy', 'policies')} found
          </div>
          {cov.top_policy_names?.length > 0 ? (
            <div className="wm-tooltip-sample">&ldquo;{cov.top_policy_names[0]}&rdquo;</div>
          ) : (
            <div className="wm-tooltip-sample">Sources watched - nothing surfaced yet.</div>
          )}
          {hover.drillable && (
            <div className="wm-tooltip-drill">Double-click to see state and province detail.</div>
          )}
        </>
      ) : (
        <>
          <div className="wm-tooltip-stats">Not yet tracked</div>
          <div className="wm-tooltip-sample">
            Search still works for it - finding sources here is how coverage grows.
          </div>
        </>
      )}
    </div>
  );
}

export default MapTooltip;
