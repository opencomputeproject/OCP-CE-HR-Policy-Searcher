import React, { useEffect, useState } from 'react';
import { isMarkerHidden, microMarkerRadius } from '../utils/mapCoverage';

function countryLabel(geo, cov) {
  if (!cov) return `${geo.name}: not yet tracked`;
  return `${geo.name}: ${cov.sources} sources, ${cov.policies} policies`;
}

function CountryPath({
  item, isHit, isDimmed, isDrillable, onHover, onHoverEnd, onSelect, onDrillOrZoom,
}) {
  const { geo, cov, bin } = item;
  const tracked = bin !== 'untracked';
  const classes = ['wm-country', `wm-bin-${bin}`];
  if (isHit) classes.push('wm-hit');
  if (isDimmed) classes.push('wm-dim');
  if (isDrillable) classes.push('wm-drillable');

  return (
    <path
      d={geo.d}
      className={classes.join(' ')}
      data-bin={bin}
      aria-label={countryLabel(geo, cov)}
      tabIndex={tracked ? 0 : undefined}
      role={tracked ? 'button' : undefined}
      vectorEffect="non-scaling-stroke"
      onPointerMove={(event) => onHover(geo.id, event)}
      onPointerLeave={onHoverEnd}
      onClick={() => onSelect(geo.id)}
      onDoubleClick={() => onDrillOrZoom(geo.id)}
      onKeyDown={tracked ? (event) => {
        if (event.key === 'Enter' && event.shiftKey && isDrillable) {
          event.preventDefault();
          onDrillOrZoom(geo.id);
          return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(geo.id);
        }
      } : undefined}
    />
  );
}

function MicroMarker({ marker, radius, isHit, isDimmed, onHover, onHoverEnd, onSelect }) {
  const classes = ['wm-micro', `wm-bin-${marker.bin}`];
  if (isHit) classes.push('wm-hit');
  if (isDimmed) classes.push('wm-dim');

  return (
    <circle
      cx={marker.cx}
      cy={marker.cy}
      r={radius}
      className={classes.join(' ')}
      data-bin={marker.bin}
      aria-label={`${marker.name}: tracked, too small to show on the map outline`}
      tabIndex={0}
      role="button"
      vectorEffect="non-scaling-stroke"
      onPointerMove={(event) => onHover(marker.id, event)}
      onPointerLeave={onHoverEnd}
      onClick={() => onSelect(marker.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(marker.id);
        }
      }}
    />
  );
}

// Inline SVG choropleth: precomputed Equal Earth paths (world-atlas 110m),
// styled entirely by CSS class so bins/hover/dim/hit states are one class
// list each, no per-element style computation.
//
// Pan/zoom is driven by the viewBox itself (see hooks/usePanZoom) rather
// than a CSS/<g> transform, so every <path>/<circle>'s own coordinates -
// and therefore hit-testing - never change.
function WorldMapSvg({
  svgRef, joined, microMarkers, activeBin, hitIds, viewBox, panZoomHandlers,
  drillableIds, onHover, onHoverEnd, onSelect, onDrillOrZoom,
}) {
  // Rendered <svg> pixel width, kept current via ResizeObserver so
  // isMarkerHidden's screen-width estimate tracks window resizes and
  // container layout changes, not just viewBox zoom. Guarded for jsdom
  // (no ResizeObserver): svgPxWidth then stays 0 and isMarkerHidden's own
  // falsy-width guard keeps every marker visible, same as before this
  // feature existed.
  const [svgPxWidth, setSvgPxWidth] = useState(0);

  useEffect(() => {
    const node = svgRef.current;
    if (!node || typeof ResizeObserver !== 'function') return undefined;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setSvgPxWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [svgRef]);

  const radius = microMarkerRadius(viewBox.w);

  return (
    <svg
      ref={svgRef}
      className="wm-svg"
      viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
      role="group"
      aria-label="World map of PolicyPulse coverage"
      {...panZoomHandlers}
    >
      {joined.map((item) => (
        <CountryPath
          key={item.geo.id}
          item={item}
          isHit={hitIds.has(item.geo.id)}
          isDimmed={activeBin !== null && item.bin !== activeBin}
          isDrillable={Boolean(drillableIds?.has(item.geo.id))}
          onHover={onHover}
          onHoverEnd={onHoverEnd}
          onSelect={onSelect}
          onDrillOrZoom={onDrillOrZoom}
        />
      ))}
      {microMarkers
        .filter((marker) => !isMarkerHidden(marker, viewBox.w, svgPxWidth))
        .map((marker) => (
          <MicroMarker
            key={marker.id}
            marker={marker}
            radius={radius}
            isHit={hitIds.has(marker.id)}
            isDimmed={activeBin !== null && marker.bin !== activeBin}
            onHover={onHover}
            onHoverEnd={onHoverEnd}
            onSelect={onSelect}
          />
        ))}
    </svg>
  );
}

export default WorldMapSvg;
