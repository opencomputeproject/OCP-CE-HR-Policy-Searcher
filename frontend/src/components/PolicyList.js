import React, { useEffect, useState } from 'react';

function PolicyList() {
  const [policies, setPolicies] = useState([]);

  /*useEffect(() => {
    fetch('/api/policies')
      .then((res) => res.json())
      .then(setPolicies)
      .catch(console.error);
  }, []);
*/
  return (
    <div>
      <h2>Policies</h2>
      <pre>{JSON.stringify(policies, null, 2)}</pre>
    </div>
  );
}

export default PolicyList;