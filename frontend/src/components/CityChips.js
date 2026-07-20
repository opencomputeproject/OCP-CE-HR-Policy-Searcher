import React from 'react';

// Forward-compatible scaffolding: /api/coverage/children carries no `cities`
// field today. Once a bucket (national or a child) gains one, this renders
// a row of plain text chips - no polygons, no coordinates, city-level detail
// is below what the admin-1 geometry can draw. Absent or empty, it renders
// nothing, so it stays dormant until the API adds the field.
function CityChips({ cities }) {
  if (!cities || cities.length === 0) return null;

  return (
    <div className="wm-city-chips" aria-label="Cities with tracked detail">
      {cities.map((city) => (
        <span className="wm-city-chip" key={city}>{city}</span>
      ))}
    </div>
  );
}

export default CityChips;
