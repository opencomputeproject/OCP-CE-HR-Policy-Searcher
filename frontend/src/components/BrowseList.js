import React from 'react';
import { pluralize } from '../utils/mapCoverage';

// The map is never the only door: a plain list of every tracked place,
// sorted by policy count, so a cramped mobile viewport or a screen-reader
// user has a way in that doesn't depend on hitting a small polygon.
function BrowseList({ rows, onSelect }) {
  if (!rows.length) return null;

  return (
    <details className="wm-browse-list">
      <summary>Browse all tracked places as a list ({rows.length})</summary>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            <button type="button" onClick={() => onSelect(row.id)}>
              <span className={`wm-legend-swatch wm-swatch-${row.bin}`} aria-hidden="true" />
              {row.name}
              <span className="wm-browse-count">
                {row.policies} {pluralize(row.policies, 'policy', 'policies')}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default BrowseList;
