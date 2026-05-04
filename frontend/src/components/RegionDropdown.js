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
        <option value="nordic">Nordics</option>
        <option value="us">US</option>
        <option value="asia">Asia</option>  
        <option value="other">Other</option> 
      </select>
    </label>
  );
}

export default RegionDropdown;
