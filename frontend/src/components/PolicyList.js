import React, { useEffect, useState } from 'react';
import SavedPolicy from './SavedPolicy';

function PolicyList() {
  const [policies, setPolicies] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
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

    loadMockPolicies();
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
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default PolicyList;
