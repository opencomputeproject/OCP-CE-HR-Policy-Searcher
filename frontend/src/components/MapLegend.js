import React from 'react';
import { BIN_KEYS, BIN_LABELS } from '../utils/mapCoverage';

// The legend doubles as a filter: clicking a tier dims everything outside
// it on the map, the off-map tray, and the browse list, in one gesture.
function MapLegend({ activeBin, onToggleBin }) {
  return (
    <div className="wm-legend" role="group" aria-label="Coverage legend, click to filter">
      {BIN_KEYS.map((bin) => (
        <button
          key={bin}
          type="button"
          className="wm-legend-item"
          data-bin={bin}
          aria-pressed={activeBin === bin}
          onClick={() => onToggleBin(bin)}
        >
          <span className={`wm-legend-swatch wm-swatch-${bin}`} aria-hidden="true" />
          {BIN_LABELS[bin]}
        </button>
      ))}
    </div>
  );
}

export default MapLegend;
