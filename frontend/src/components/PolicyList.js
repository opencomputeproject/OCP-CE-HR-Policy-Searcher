import React, { useEffect, useMemo, useRef, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import TextField from '@mui/material/TextField';
import FilterListIcon from '@mui/icons-material/FilterList';
import { apiUrl } from '../config/api';
import SavedPolicy, { formatTagLabel, getPolicyTags } from './SavedPolicy';

const UPCOMING_LIFECYCLE_STAGES = ['proposed', 'consultation', 'in_committee', 'passed', 'transposition_notified'];
const ENACTED_LIFECYCLE_STAGES = ['enacted', 'amended'];

const LIFECYCLE_FILTER_MODES = [
  { id: 'all', label: 'All' },
  { id: 'upcoming', label: 'Upcoming' },
  { id: 'enacted', label: 'Enacted' },
];

export function filterByLifecycle(policies, mode) {
  if (mode === 'upcoming') {
    return policies.filter((policy) => UPCOMING_LIFECYCLE_STAGES.includes(policy.lifecycle_stage));
  }
  if (mode === 'enacted') {
    return policies.filter((policy) => ENACTED_LIFECYCLE_STAGES.includes(policy.lifecycle_stage));
  }
  return policies;
}

function getPolicyKey(policy, index) {
  return `${policy.scan_id}-${policy.domain_id}-${index}`;
}

function getPolicyDateValue(policy) {
  const dateValue = policy.discovered_at || policy.created_at || policy.updated_at || '';
  const timestamp = Date.parse(dateValue);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function compareText(firstValue, secondValue) {
  return String(firstValue || '').localeCompare(String(secondValue || ''));
}

function PolicyList({ externalPlace = null }) {
  const [policies, setPolicies] = useState([]);
  const [tags, setTags] = useState({});
  const [selectedJurisdictions, setSelectedJurisdictions] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [nameQuery, setNameQuery] = useState('');
  const [sortBy, setSortBy] = useState('relevance');
  const [lifecycleMode, setLifecycleMode] = useState('all');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  // Place-filter mode: WorldMap/CountryView's "View {n} found policies"
  // buttons feed a place request here (mirrors SearchPanel's externalPlace
  // pattern - {slug, name, nonce}, a fresh nonce re-triggers even the same
  // place). `null` means the normal all-policies view; set means the list
  // is scoped to that place's own /api/policies?place=<slug> fetch, with
  // client-side filters (name/jurisdiction/tag/lifecycle/sort) still applied
  // on top and left intact when the filter is cleared.
  const [placeFilter, setPlaceFilter] = useState(null);
  const [isPlaceFilterLoading, setIsPlaceFilterLoading] = useState(false);
  const [placeFilterError, setPlaceFilterError] = useState(null);
  const sectionRef = useRef(null);

  useEffect(() => {
    const loadSavedPolicies = async () => {
      setError(null);
      try {
        const [policiesResponse, tagsResponse] = await Promise.all([
          fetch(apiUrl('/api/policies')),
          fetch(apiUrl('/api/tags')),
        ]);

        if (!policiesResponse.ok) {
          throw new Error(`Failed to load policies (${policiesResponse.status})`);
        }

        if (!tagsResponse.ok) {
          throw new Error(`Failed to load tags (${tagsResponse.status})`);
        }

        const data = await policiesResponse.json();
        const tagData = await tagsResponse.json();

        setPolicies(Array.isArray(data.policies) ? data.policies : []);
        setTags(tagData && typeof tagData === 'object' ? tagData : {});
      } catch (loadError) {
        console.error(loadError);
        setError('Could not load data. Check that the backend is running, then refresh.');
      } finally {
        setIsLoading(false);
      }
    };

    loadSavedPolicies();
    window.addEventListener('policy-data-changed', loadSavedPolicies);

    return () => {
      window.removeEventListener('policy-data-changed', loadSavedPolicies);
    };
  }, []);

  useEffect(() => {
    if (!externalPlace) return undefined;
    let cancelled = false;

    setIsPlaceFilterLoading(true);
    setPlaceFilterError(null);

    const loadPlacePolicies = async () => {
      try {
        const params = new URLSearchParams({ place: externalPlace.slug });
        const response = await fetch(apiUrl(`/api/policies?${params.toString()}`));
        if (!response.ok) {
          throw new Error(`Failed to load policies for ${externalPlace.name} (${response.status})`);
        }
        const data = await response.json();
        if (!cancelled) {
          setPlaceFilter({
            slug: externalPlace.slug,
            name: externalPlace.name,
            policies: Array.isArray(data.policies) ? data.policies : [],
          });
        }
      } catch (loadError) {
        console.error(loadError);
        if (!cancelled) setPlaceFilterError(`Could not load policies for ${externalPlace.name}.`);
      } finally {
        if (!cancelled) setIsPlaceFilterLoading(false);
      }
    };

    loadPlacePolicies();
    return () => {
      cancelled = true;
    };
  }, [externalPlace]);

  // Scrolling requires the real list markup to be mounted (not the "Loading
  // policies..." placeholder returned while the baseline fetch is still in
  // flight), so this waits on both the place fetch landing AND isLoading
  // clearing, rather than firing the moment the place request arrives.
  useEffect(() => {
    if (placeFilter && !isLoading) {
      sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [placeFilter, isLoading]);

  const clearPlaceFilter = () => {
    setPlaceFilter(null);
    setPlaceFilterError(null);
  };

  // The place-filter fetch's own results when active, otherwise the normal
  // all-policies view - everything downstream (tag map, name/jurisdiction/tag/
  // lifecycle filters, sort) runs the same either way.
  const sourcePolicies = placeFilter ? placeFilter.policies : policies;

  const policyTagsByKey = useMemo(() => {
    return sourcePolicies.reduce((tagMap, policy, index) => {
      tagMap.set(getPolicyKey(policy, index), getPolicyTags(policy, tags));
      return tagMap;
    }, new Map());
  }, [sourcePolicies, tags]);

  const tagOptions = useMemo(() => {
    const optionSet = new Set(Object.keys(tags));

    policyTagsByKey.forEach((policyTags) => {
      policyTags.forEach((tag) => optionSet.add(tag));
    });

    return [...optionSet].sort((firstTag, secondTag) =>
      formatTagLabel(firstTag).localeCompare(formatTagLabel(secondTag))
    );
  }, [policyTagsByKey, tags]);

  const jurisdictionOptions = useMemo(() => {
    return [...new Set(policies.map((policy) => policy.jurisdiction).filter(Boolean))]
      .sort((firstJurisdiction, secondJurisdiction) =>
        firstJurisdiction.localeCompare(secondJurisdiction)
      );
  }, [policies]);

  const lifecycleAllowedPolicies = useMemo(
    () => new Set(filterByLifecycle(sourcePolicies, lifecycleMode)),
    [sourcePolicies, lifecycleMode],
  );

  const filteredPolicyEntries = useMemo(() => {
    const normalizedNameQuery = nameQuery.trim().toLowerCase();

    return sourcePolicies
      .map((policy, index) => ({ policy, policyKey: getPolicyKey(policy, index) }))
      .filter(({ policy, policyKey }) => {
        const matchesLifecycle = lifecycleAllowedPolicies.has(policy);
        const matchesName = normalizedNameQuery
          ? String(policy.policy_name || '').toLowerCase().includes(normalizedNameQuery)
          : true;
        const matchesJurisdictions = selectedJurisdictions.length > 0
          ? selectedJurisdictions.includes(policy.jurisdiction)
          : true;
        const policyTags = policyTagsByKey.get(policyKey) || [];
        const matchesTags = selectedTags.length > 0
          ? selectedTags.every((tag) => policyTags.includes(tag))
          : true;

        return matchesLifecycle && matchesName && matchesJurisdictions && matchesTags;
      })
      .sort((firstEntry, secondEntry) => {
        const firstPolicy = firstEntry.policy;
        const secondPolicy = secondEntry.policy;

        if (sortBy === 'name') {
          return compareText(firstPolicy.policy_name, secondPolicy.policy_name);
        }
        if (sortBy === 'jurisdiction') {
          return compareText(firstPolicy.jurisdiction, secondPolicy.jurisdiction);
        }
        if (sortBy === 'relevance') {
          return (Number(secondPolicy.relevance_score) || 0) - (Number(firstPolicy.relevance_score) || 0);
        }
        return getPolicyDateValue(secondPolicy) - getPolicyDateValue(firstPolicy);
      });
  }, [
    sourcePolicies,
    policyTagsByKey,
    lifecycleAllowedPolicies,
    selectedJurisdictions,
    selectedTags,
    nameQuery,
    sortBy,
  ]);

  const clearFilters = () => {
    setNameQuery('');
    setSelectedJurisdictions([]);
    setSelectedTags([]);
    setSortBy('relevance');
    setLifecycleMode('all');
  };

  if (isLoading) {
    return <div role="status">Loading policies...</div>;
  }

  if (error) {
    return <div>{error}</div>;
  }

  return (
    <section className="policy-list" ref={sectionRef}>
      <div className="policy-list-header">
        <div className="policy-list-title">
          <h2>Discovered Policies</h2>
          <p className="policy-list-count">
            Showing {filteredPolicyEntries.length} of {sourcePolicies.length} policies
          </p>
        </div>
        <div className="policy-list-filters">
          <div className="policy-filter-label">
            <FilterListIcon fontSize="small" />
            <span>Filters:</span>
          </div>
          <TextField
            className="policy-list-filter policy-list-search"
            label="Filter by name"
            placeholder="Filter by name..."
            size="small"
            value={nameQuery}
            onChange={(event) => setNameQuery(event.target.value)}
            sx={{ width: 200 }}
          />
          <Autocomplete
            multiple
            limitTags={1}
            disablePortal
            className="policy-list-filter"
            options={jurisdictionOptions}
            value={selectedJurisdictions}
            onChange={(_, value) => setSelectedJurisdictions(value)}
            disabled={jurisdictionOptions.length === 0}
            sx={{ width: 200 }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Jurisdiction"
                placeholder={selectedJurisdictions.length === 0 ? 'All jurisdictions' : ''}
                size="small"
              />
            )}
          />
          <Autocomplete
            multiple
            limitTags={1}
            disablePortal
            className="policy-list-filter"
            options={tagOptions}
            value={selectedTags}
            onChange={(_, value) => setSelectedTags(value)}
            getOptionLabel={(tag) => formatTagLabel(tag)}
            disabled={tagOptions.length === 0}
            sx={{ width: 200 }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Tag"
                placeholder={selectedTags.length === 0 ? 'All tags' : ''}
                size="small"
              />
            )}
          />
          <FormControl className="policy-list-filter policy-list-sort" size="small" sx={{ width: 250 }}>
            <InputLabel id="policy-sort-label">Sort by</InputLabel>
            <Select
              id="policy-sort"
              labelId="policy-sort-label"
              label="Sort by"
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value)}
            >
              <MenuItem value="relevance">Relevance (High)</MenuItem>
              <MenuItem value="name">Name (A-Z)</MenuItem>
              <MenuItem value="jurisdiction">Jurisdiction (A-Z)</MenuItem>
              <MenuItem value="date">Date added (Newest)</MenuItem>
            </Select>
          </FormControl>
          <button type="button" className="policy-clear-button" onClick={clearFilters}>
            Clear
          </button>
        </div>
      </div>
      {isPlaceFilterLoading && (
        <p role="status">Loading policies for {externalPlace?.name}...</p>
      )}
      {placeFilterError && (
        <p className="ask-box-error" role="alert">{placeFilterError}</p>
      )}
      {placeFilter && !isPlaceFilterLoading && (
        <div className="policy-list-place-filter">
          <span className="policy-place-chip">
            {placeFilter.name} - {placeFilter.policies.length}{' '}
            {placeFilter.policies.length === 1 ? 'policy' : 'policies'}
            <button
              type="button"
              className="policy-place-chip-clear"
              aria-label={`Clear ${placeFilter.name} filter`}
              onClick={clearPlaceFilter}
            >
              &times;
            </button>
          </span>
        </div>
      )}
      <div className="lifecycle-filter-chips" role="group" aria-label="Lifecycle stage filter">
        {LIFECYCLE_FILTER_MODES.map((modeOption) => (
          <button
            key={modeOption.id}
            type="button"
            className={`lifecycle-chip ${lifecycleMode === modeOption.id ? 'active' : ''}`}
            aria-pressed={lifecycleMode === modeOption.id}
            onClick={() => setLifecycleMode(modeOption.id)}
          >
            {modeOption.label}
          </button>
        ))}
      </div>
      {sourcePolicies.length === 0 ? (
        <p>No policies discovered yet. Select a region in the scanner and press Scan, or ask the agent in the chat.</p>
      ) : filteredPolicyEntries.length === 0 ? (
        <p className="text-block">
          No policies match the selected filters in our current database. Use the agent to find policies within your requirements.
        </p>
      ) : (
        <div className="policy-list-items">
          {filteredPolicyEntries.map(({ policy, policyKey }) => (
            <SavedPolicy
              key={policyKey}
              policy={policy}
              tags={tags}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default PolicyList;
