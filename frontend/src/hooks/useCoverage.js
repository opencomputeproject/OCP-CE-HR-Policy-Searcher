import { useEffect, useState } from 'react';
import { apiUrl } from '../config/api';

const EMPTY_COVERAGE = { countries: [], supranational: [], totals: { sources: 0, policies: 0 } };

// Coverage powers the world map's colors, so it needs to be as fresh as the
// policy list: refetch on the same 'policy-data-changed' event a completed
// scan already dispatches, not just on mount.
function useCoverage() {
  const [coverage, setCoverage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isCurrent = true;

    const load = () => {
      fetch(apiUrl('/api/coverage'))
        .then((res) => {
          if (!res.ok) throw new Error(`coverage fetch failed (${res.status})`);
          return res.json();
        })
        .then((data) => {
          if (isCurrent) {
            setCoverage(data);
            setError(null);
          }
        })
        .catch((loadError) => {
          if (isCurrent) setError(loadError);
        });
    };

    load();
    window.addEventListener('policy-data-changed', load);
    return () => {
      isCurrent = false;
      window.removeEventListener('policy-data-changed', load);
    };
  }, []);

  return { coverage: coverage || EMPTY_COVERAGE, isLoading: coverage === null, error };
}

export default useCoverage;
