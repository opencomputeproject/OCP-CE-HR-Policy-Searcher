import React from 'react';

function RegionDropdown({ value, onChange }) {
  return (
    <label className="region-field">
      <span className="region-label">Region</span>
      <select
        className="region-select"
        value={value}
        onChange={onChange}
      >
        <option value="eu">EU</option>
      </select>
    </label>
  );
}

export default RegionDropdown;
