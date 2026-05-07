import React, { useEffect, useState } from 'react';
import SavedPolicy from './SavedPolicy';

function PolicyList() {
  const [policies, setPolicies] = useState([]);
  const [tags, setTags] = useState({});
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

  if (isLoading) {
    return <div>Loading policies...</div>;
  }

  if (error) {
    return <div>Unable to load policies: {error}</div>;
  }

  return (
    <section className="policy-list">
      <h2>Policies</h2>
      {policies.length === 0 ? (
        <p>No policies found.</p>
      ) : (
        <div className="policy-list-items">
          {policies.map((policy, index) => (
            <SavedPolicy
              key={`${policy.scan_id}-${policy.domain_id}-${index}`}
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
