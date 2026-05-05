import * as React from 'react';
import { styled, alpha } from '@mui/material/styles';
import Box from '@mui/material/Box';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';
import { TreeItem, treeItemClasses } from '@mui/x-tree-view/TreeItem';

const regionData = [
  {
    id: 'europe',
    label: 'Europe',
    children: [
      {
        id: 'eu',
        label: 'EU',
        children: [
          {
            id: 'germany',
            label: 'Germany',
            children: [
              { id: 'bayern', label: 'Bavaria' },
              { id: 'hessen', label: 'Hesse' },
              { id: 'nordrhein_westfalen', label: 'North Rhine-Westphalia' },
              { id: 'baden_wuerttemberg', label: 'Baden-Württemberg' },
              { id: 'berlin', label: 'Berlin' },
              { id: 'hamburg', label: 'Hamburg' },
              { id: 'niedersachsen', label: 'Lower Saxony' },
              { id: 'sachsen', label: 'Saxony' },
            ],
          },
          { id: 'france', label: 'France' },
          { id: 'netherlands', label: 'Netherlands' },
          { id: 'ireland', label: 'Ireland' },
          { id: 'austria', label: 'Austria' },
          { id: 'belgium', label: 'Belgium' },
          { id: 'spain', label: 'Spain' },
          { id: 'italy', label: 'Italy' },
          { id: 'poland', label: 'Poland' },
          { id: 'portugal', label: 'Portugal' },
          { id: 'czech_republic', label: 'Czech Republic' },
          { id: 'greece', label: 'Greece' },
          { id: 'hungary', label: 'Hungary' },
          { id: 'romania', label: 'Romania' },
          { id: 'finland', label: 'Finland' },
          { id: 'iceland', label: 'Iceland' },
          { id: 'denmark', label: 'Denmark' },
          { id: 'sweden', label: 'Sweden' },
        ],
      },
      {
        id: 'uk',
        label: 'United Kingdom',
        children: [
          { id: 'scotland', label: 'Scotland' },
          { id: 'wales', label: 'Wales' },
          { id: 'northern_ireland', label: 'Northern Ireland' },
        ],
      },
      {
        id: 'switzerland',
        label: 'Switzerland',
        children: [
          { id: 'zurich', label: 'Zurich' },
        ],
      },
      { id: 'norway', label: 'Norway' },
    ],
  },
  {
    id: 'north_america',
    label: 'North America',
    children: [
      {
        id: 'us',
        label: 'United States',
        children: [
          {
            id: 'us_states',
            label: 'US States',
            children: [
              { id: 'alabama', label: 'Alabama' },
              { id: 'alaska', label: 'Alaska' },
              { id: 'arizona', label: 'Arizona' },
              { id: 'arkansas', label: 'Arkansas' },
              { id: 'california', label: 'California' },
              { id: 'colorado', label: 'Colorado' },
              { id: 'connecticut', label: 'Connecticut' },
              { id: 'delaware', label: 'Delaware' },
              { id: 'florida', label: 'Florida' },
              { id: 'georgia', label: 'Georgia' },
              { id: 'hawaii', label: 'Hawaii' },
              { id: 'idaho', label: 'Idaho' },
              { id: 'illinois', label: 'Illinois' },
              { id: 'indiana', label: 'Indiana' },
              { id: 'iowa', label: 'Iowa' },
              { id: 'kansas', label: 'Kansas' },
              { id: 'kentucky', label: 'Kentucky' },
              { id: 'louisiana', label: 'Louisiana' },
              { id: 'maine', label: 'Maine' },
              { id: 'maryland', label: 'Maryland' },
              { id: 'massachusetts', label: 'Massachusetts' },
              { id: 'michigan', label: 'Michigan' },
              { id: 'minnesota', label: 'Minnesota' },
              { id: 'mississippi', label: 'Mississippi' },
              { id: 'missouri', label: 'Missouri' },
              { id: 'montana', label: 'Montana' },
              { id: 'nebraska', label: 'Nebraska' },
              { id: 'nevada', label: 'Nevada' },
              { id: 'new_hampshire', label: 'New Hampshire' },
              { id: 'new_jersey', label: 'New Jersey' },
              { id: 'new_mexico', label: 'New Mexico' },
              { id: 'new_york', label: 'New York' },
              { id: 'north_carolina', label: 'North Carolina' },
              { id: 'north_dakota', label: 'North Dakota' },
              { id: 'ohio', label: 'Ohio' },
              { id: 'oklahoma', label: 'Oklahoma' },
              { id: 'oregon', label: 'Oregon' },
              { id: 'pennsylvania', label: 'Pennsylvania' },
              { id: 'rhode_island', label: 'Rhode Island' },
              { id: 'south_carolina', label: 'South Carolina' },
              { id: 'south_dakota', label: 'South Dakota' },
              { id: 'tennessee', label: 'Tennessee' },
              { id: 'texas', label: 'Texas' },
              { id: 'utah', label: 'Utah' },
              { id: 'vermont', label: 'Vermont' },
              { id: 'virginia', label: 'Virginia' },
              { id: 'washington', label: 'Washington' },
              { id: 'west_virginia', label: 'West Virginia' },
              { id: 'wisconsin', label: 'Wisconsin' },
              { id: 'wyoming', label: 'Wyoming' },
            ],
          },
        ],
      },
      {
        id: 'canada',
        label: 'Canada',
        children: [
          { id: 'ontario', label: 'Ontario' },
          { id: 'british_columbia', label: 'British Columbia' },
          { id: 'quebec', label: 'Quebec' },
          { id: 'alberta', label: 'Alberta' },
        ],
      },
      { id: 'mexico', label: 'Mexico' },
    ],
  },
  {
    id: 'south_america',
    label: 'South America',
    children: [
      { id: 'brazil', label: 'Brazil' },
    ],
  },
  {
    id: 'asia_pacific',
    label: 'Asia-Pacific',
    children: [
      {
        id: 'apac',
        label: 'APAC',
        children: [
          { id: 'singapore', label: 'Singapore' },
          { id: 'japan', label: 'Japan' },
          { id: 'south_korea', label: 'South Korea' },
          {
            id: 'australia',
            label: 'Australia',
            children: [
              { id: 'new_south_wales', label: 'New South Wales' },
              { id: 'south_australia', label: 'South Australia' },
            ],
          },
          {
            id: 'india',
            label: 'India',
            children: [
              { id: 'karnataka', label: 'Karnataka' },
              { id: 'tamil_nadu', label: 'Tamil Nadu' },
              { id: 'telangana', label: 'Telangana' },
              { id: 'maharashtra', label: 'Maharashtra' },
            ],
          },
        ],
      },
      {
    id: 'middle_east',
    label: 'Middle East',
    children: [
      {
        id: 'uae',
        label: 'United Arab Emirates',
        children: [
          { id: 'abu_dhabi', label: 'Abu Dhabi' },
          { id: 'dubai', label: 'Dubai' },
        ],
      },
      { id: 'saudi_arabia', label: 'Saudi Arabia' },
    ],
  },
    ],
  },
  
  {
    id: 'africa',
    label: 'Africa',
    children: [
      { id: 'south_africa', label: 'South Africa' },
    ],
  },
  {
    id: 'scan_groups',
    label: 'Scan groups',
    children: [
      { id: 'all', label: 'All' },
      { id: 'quick', label: 'Quick' },
      { id: 'federal', label: 'Federal' },
      { id: 'leaders', label: 'Leaders' },
      { id: 'emerging', label: 'Emerging' },
      { id: 'pending_legislation', label: 'Pending legislation' },
      { id: 'sample_nordic', label: 'Sample Nordic' },
      { id: 'sample_apac', label: 'Sample APAC' },
      { id: 'test', label: 'Test' },
      { id: 'test_new', label: 'Test new' },
      { id: 'test_new_zh', label: 'Test new zh' },
      { id: 'test_new_de', label: 'Test new de' },
      { id: 'test_new_eu', label: 'Test new EU' },
      { id: 'test_new_us', label: 'Test new US' },
      { id: 'test_eu_expansion', label: 'Test EU expansion' },
      { id: 'test_us_expansion', label: 'Test US expansion' },
      { id: 'germany_laender', label: 'Germany Länder' },
    ],
  },
];

// 1. Create a Custom Tree Item with your specific styling
const StyledTreeItem = styled(TreeItem)(({ theme }) => ({
  color: theme.palette.text.secondary,
  [`& .${treeItemClasses.content}`]: {
    padding: theme.spacing(0.5, 1),
    margin: theme.spacing(0.2, 0),
    borderRadius: theme.shape.borderRadius,
  },
  [`& .${treeItemClasses.groupTransition}`]: {
    marginLeft: 15,
    paddingLeft: 18,
    borderLeft: `1px dashed ${alpha(theme.palette.text.primary, 0.4)}`,
  },
}));

// 2. Build the actual Component
function renderTreeItems(items) {
  return items.map((item) => (
    <StyledTreeItem key={item.id} itemId={item.id} label={item.label}>
      {item.children ? renderTreeItems(item.children) : null}
    </StyledTreeItem>
  ));
}

export default function RegionTreeView({ selectedItems, onSelectionChange }) {
  return (
    <Box sx={{ minHeight: 200, flexGrow: 1, width: '100%' }}>
      <SimpleTreeView
        checkboxSelection
        selectionPropagation
        multiSelect
        selectedItems={selectedItems}
        onSelectedItemsChange={onSelectionChange}
      >
        {renderTreeItems(regionData)}
      </SimpleTreeView>
    </Box>
  );
}
