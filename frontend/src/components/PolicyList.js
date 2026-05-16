import React, { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import SavedPolicy, { formatTagLabel, getPolicyTags } from './SavedPolicy';

function getPolicyKey(policy, index) {
  return `${policy.scan_id}-${policy.domain_id}-${index}`;
}

function PolicyList() {
  const [policies, setPolicies] = useState([]);
  const [tags, setTags] = useState({});
  const [selectedJurisdictions, setSelectedJurisdictions] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';

    /*
    const loadMockPolicies = async () => {
      try {
        const response = await fetch('/mock-policies.json');

        if (!response.ok) {
          throw new Error(`Failed to load policies (${response.status})`);
        }

        const data = await response.json();
        setPolicies(Array.isArray(data.policies) ? data.policies : []);
      } catch (loadError) {
        setError(loadError.message);
      } finally {
        setIsLoading(false);
      }
    };
    */

    const loadSavedPolicies = async () => {
      try {
        const [policiesResponse, tagsResponse] = await Promise.all([
          fetch(`${apiUrl}/api/policies`),
          fetch(`${apiUrl}/api/tags`),
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
        setError(loadError.message);
      } finally {
        setIsLoading(false);
      }
    };

    loadSavedPolicies();
  }, []);

  const policyTagsByKey = useMemo(() => {
    return policies.reduce((tagMap, policy, index) => {
      tagMap.set(getPolicyKey(policy, index), getPolicyTags(policy, tags));
      return tagMap;
    }, new Map());
  }, [policies, tags]);

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

  const filteredPolicyEntries = useMemo(() => {
    return policies
      .map((policy, index) => ({ policy, policyKey: getPolicyKey(policy, index) }))
      .filter(({ policy, policyKey }) => {
        const matchesJurisdictions = selectedJurisdictions.length > 0
          ? selectedJurisdictions.includes(policy.jurisdiction)
          : true;
        const policyTags = policyTagsByKey.get(policyKey) || [];
        const matchesTags = selectedTags.length > 0
          ? selectedTags.some((tag) => policyTags.includes(tag))
          : true;

        return matchesJurisdictions && matchesTags;
      });
  }, [policies, policyTagsByKey, selectedJurisdictions, selectedTags]);

  if (isLoading) {
    return <div>Loading policies...</div>;
  }

  if (error) {
    return <div>Unable to load policies: {error}</div>;
  }

  return (
    <section className="policy-list">
      <div className="policy-list-header">
        <div>
          <h2>Policies</h2>
          <p className="policy-list-count">
            {filteredPolicyEntries.length} of {policies.length} policies shown
          </p>
        </div>
        <div className="policy-list-filters">
          <Autocomplete
            multiple
            limitTags={1}
            disablePortal
            className="policy-list-filter"
            options={jurisdictionOptions}
            value={selectedJurisdictions}
            onChange={(_, value) => setSelectedJurisdictions(value)}
            disabled={jurisdictionOptions.length === 0}
            sx={{ width: 260 }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Filter by jurisdictions"
                placeholder="Jurisdictions"
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
            sx={{ width: 260 }}
            renderInput={(params) => (
              <TextField {...params} label="Filter by tags" placeholder="Tags" size="small" />
            )}
          />
        </div>
      </div>
      {policies.length === 0 ? (
        <p>No policies found.</p>
      ) : filteredPolicyEntries.length === 0 ? (
        <p>No policies match the selected tag.</p>
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
