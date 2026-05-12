import * as React from 'react';
import { styled, alpha } from '@mui/material/styles';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';
import { TreeItem, treeItemClasses } from '@mui/x-tree-view/TreeItem';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

const TOP_LEVEL_IDS = new Set([
  'section:categories',
  'section:tags',
  'section:domains',
]);

const LABEL_OVERRIDES = {
  all: 'All',
  apac: 'APAC',
  eu: 'EU',
  uk: 'United Kingdom',
  us: 'United States',
  uae: 'United Arab Emirates',
  dach: 'DACH',
  nordic: 'Nordic',
};

function formatLabel(value) {
  if (!value) return '';
  if (LABEL_OVERRIDES[value]) return LABEL_OVERRIDES[value];

  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function countDomainsByValue(domains, getter) {
  const counts = new Map();

  domains.forEach((domain) => {
    const values = getter(domain);
    values.forEach((value) => {
      if (!value) return;
      counts.set(value, (counts.get(value) || 0) + 1);
    });
  });

  return counts;
}

function sortByLabel(items) {
  return [...items].sort((a, b) => a.label.localeCompare(b.label));
}

function buildCountLabel(label, count) {
  return count ? `${label} (${count})` : label;
}

function buildGroupRegionItems(groupId, domains, regionLabels) {
  const regionCounts = countDomainsByValue(domains, (domain) => domain.region || []);

  return sortByLabel(
    [...regionCounts.entries()].map(([region, count]) => ({
      id: `group:${groupId}:region:${region}`,
      value: `group:${groupId}:region:${region}`,
      label: buildCountLabel(regionLabels[region] || formatLabel(region), count),
    })),
  );
}

function buildTreeData({ groups, groupDomains, regions }) {
  const groupItems = sortByLabel(
    Object.entries(groups).map(([id, description]) => ({
      id: `group:${id}`,
      value: `group:${id}`,
      label: description && description !== 'No description'
        ? `${formatLabel(id)} - ${description}`
        : formatLabel(id),
      children: buildGroupRegionItems(id, groupDomains[id] || [], regions),
    })),
  );

  return groupItems;
}

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.status}`);
  }
  return response.json();
}

async function fetchGroupDomains(groups, signal) {
  const entries = await Promise.all(
    Object.keys(groups).map(async (groupId) => {
      const params = new URLSearchParams({ group: groupId });
      const response = await fetchJson(`/api/domains?${params.toString()}`, signal);
      return [groupId, response.domains || []];
    }),
  );

  return Object.fromEntries(entries);
}

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

function flattenTreeItems(items) {
  return items.flatMap((item) => [
    item,
    ...(item.children ? flattenTreeItems(item.children) : []),
  ]);
}

export default function RegionSelector({ selectedItems, onSelectionChange }) {
  const [treeData, setTreeData] = React.useState([]);
  const [status, setStatus] = React.useState('loading');
  const [error, setError] = React.useState('');

  const itemValueById = React.useMemo(() => {
    const entries = flattenTreeItems(treeData)
      .filter((item) => item.value)
      .map((item) => [item.id, item.value]);
    return new Map(entries);
  }, [treeData]);

  const itemIdByValue = React.useMemo(() => {
    const entries = flattenTreeItems(treeData)
      .filter((item) => item.value)
      .map((item) => [item.value, item.id]);
    return new Map(entries);
  }, [treeData]);

  const treeSelectedItems = React.useMemo(
    () => (selectedItems || []).map((value) => itemIdByValue.get(value) || value),
    [itemIdByValue, selectedItems],
  );

  React.useEffect(() => {
    const controller = new AbortController();

    async function loadDomainFilters() {
      try {
        setStatus('loading');
        setError('');

        const [groups, regions] = await Promise.all([
          fetchJson('/api/groups', controller.signal),
          fetchJson('/api/regions', controller.signal),
        ]);
        const groupDomains = await fetchGroupDomains(groups, controller.signal);

        setTreeData(buildTreeData({
          groups,
          groupDomains,
          regions,
        }));
        setStatus('ready');
      } catch (loadError) {
        if (loadError.name === 'AbortError') return;
        setError(loadError.message);
        setStatus('error');
      }
    }

    loadDomainFilters();

    return () => {
      controller.abort();
    };
  }, []);

  const handleSelectedItemsChange = React.useCallback(
    (event, itemIds) => {
      const selectedParents = new Set(
        itemIds.filter((id) => itemValueById.has(id) && itemIds.some(
          (candidateId) => candidateId.startsWith(`${id}:`),
        )),
      );
      const selectableItems = [
        ...new Set(
          itemIds
            .filter((id) => !TOP_LEVEL_IDS.has(id))
            .filter((id) => ![...selectedParents].some((parentId) => (
              id !== parentId && id.startsWith(`${parentId}:`)
            )))
            .map((id) => itemValueById.get(id) || id),
        ),
      ];
      onSelectionChange?.(event, selectableItems);
    },
    [itemValueById, onSelectionChange],
  );

  if (status === 'loading') {
    return (
      <Box sx={{ minHeight: 200, width: '100%', display: 'flex', alignItems: 'center' }}>
        <Typography color="text.secondary" variant="body2">
          Loading domains...
        </Typography>
      </Box>
    );
  }

  if (status === 'error') {
    return (
      <Box sx={{ minHeight: 200, width: '100%' }}>
        <Typography color="error" variant="body2">
          {error || 'Could not load domains.'}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: 200, flexGrow: 1, width: '100%' }}>
      <SimpleTreeView
        checkboxSelection
        selectionPropagation
        multiSelect
        selectedItems={treeSelectedItems}
        onSelectedItemsChange={handleSelectedItemsChange}
      >
        {renderTreeItems(treeData)}
      </SimpleTreeView>
    </Box>
  );
}
