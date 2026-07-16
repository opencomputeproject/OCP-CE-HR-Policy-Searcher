import { filterByLifecycle } from './PolicyList';

const policies = [
  { policy_name: 'A', lifecycle_stage: 'proposed' },
  { policy_name: 'B', lifecycle_stage: 'consultation' },
  { policy_name: 'C', lifecycle_stage: 'in_committee' },
  { policy_name: 'D', lifecycle_stage: 'passed' },
  { policy_name: 'E', lifecycle_stage: 'transposition_notified' },
  { policy_name: 'F', lifecycle_stage: 'enacted' },
  { policy_name: 'G', lifecycle_stage: 'amended' },
  { policy_name: 'H', lifecycle_stage: 'unknown' },
  { policy_name: 'I' },
];

describe('filterByLifecycle', () => {
  it('returns every policy for mode "all"', () => {
    expect(filterByLifecycle(policies, 'all')).toEqual(policies);
  });

  it('returns only upcoming-stage policies for mode "upcoming"', () => {
    const result = filterByLifecycle(policies, 'upcoming');
    expect(result.map((policy) => policy.policy_name)).toEqual(['A', 'B', 'C', 'D', 'E']);
  });

  it('returns only enacted-stage policies for mode "enacted"', () => {
    const result = filterByLifecycle(policies, 'enacted');
    expect(result.map((policy) => policy.policy_name)).toEqual(['F', 'G']);
  });

  it('excludes unknown or missing stages from upcoming and enacted modes', () => {
    const upcomingNames = filterByLifecycle(policies, 'upcoming').map((policy) => policy.policy_name);
    const enactedNames = filterByLifecycle(policies, 'enacted').map((policy) => policy.policy_name);

    expect(upcomingNames).not.toEqual(expect.arrayContaining(['H', 'I']));
    expect(enactedNames).not.toEqual(expect.arrayContaining(['H', 'I']));
  });
});
