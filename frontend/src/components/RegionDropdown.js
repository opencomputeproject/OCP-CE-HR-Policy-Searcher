import React from 'react';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';

const regions = [
  { value: 'eu', label: 'EU' },
  { value: 'nordic', label: 'Nordics' },
  { value: 'us', label: 'US' },
  { value: 'asia', label: 'Asia' },
  { value: 'other', label: 'Other' },
];

function RegionDropdown({ value, onChange }) {
  return (
    <FormControl className="region-field" size="small">
      <InputLabel id="region-select-label">Region</InputLabel>
      <Select
        labelId="region-select-label"
        id="region-select"
        value={value}
        label="Region"
        onChange={onChange}
      >
        {regions.map((region) => (
          <MenuItem key={region.value} value={region.value}>
            {region.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

export default RegionDropdown;
