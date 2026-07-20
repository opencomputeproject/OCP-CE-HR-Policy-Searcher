import React from 'react';
import { binForCoverage, pluralize } from '../utils/mapCoverage';

// Not every tracked jurisdiction has a renderable shape: the EU is
// member-based, a future global IGO bucket has no members, and contested
// territories (Kosovo, N. Cyprus, Somaliland) resolve with no iso_numeric.
// Every one of them gets a chip here rather than being silently dropped.
function OffMapTray({ entries, activeBin, activeId, hitSlugs, onSelect }) {
  if (!entries.length) return null;

  return (
    <div className="wm-offmap-tray" aria-label="Coverage without a map shape">
      <span className="wm-offmap-label">Not shown on the map:</span>
      <div className="wm-offmap-chips">
        {entries.map((entry) => {
          const bin = binForCoverage(entry);
          const classes = ['wm-offmap-chip'];
          if (activeBin !== null && bin !== activeBin) classes.push('wm-dim');
          if (hitSlugs?.has(entry.slug)) classes.push('wm-hit');
          return (
            <button
              key={entry.slug}
              type="button"
              className={classes.join(' ')}
              data-bin={bin}
              aria-pressed={activeId === `sup:${entry.slug}`}
              onClick={() => onSelect(entry)}
            >
              <span className={`wm-legend-swatch wm-swatch-${bin}`} aria-hidden="true" />
              {entry.name}
              <span className="wm-offmap-count">
                {entry.policies} {pluralize(entry.policies, 'policy', 'policies')}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default OffMapTray;
