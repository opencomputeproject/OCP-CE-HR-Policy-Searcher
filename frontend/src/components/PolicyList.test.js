import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PolicyList, { filterByLifecycle } from './PolicyList';

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

// --- Place-filter mode (WorldMap/CountryView "View found policies" -> here) ---

const ALL_POLICIES = [
  {
    url: 'https://a.gov/1', policy_name: 'Federal Heat Reuse Act', jurisdiction: 'US',
    relevance_score: 9, scan_id: 's1', domain_id: 'd1',
  },
  {
    url: 'https://a.gov/2', policy_name: 'Minnesota Thermal Pilot', jurisdiction: 'Minnesota, USA',
    relevance_score: 5, scan_id: 's2', domain_id: 'd2',
  },
  {
    url: 'https://a.gov/3', policy_name: 'Sweden Heat Rule', jurisdiction: 'Sweden',
    relevance_score: 6, scan_id: 's3', domain_id: 'd3',
  },
];

const US_PLACE_POLICIES = [ALL_POLICIES[0], ALL_POLICIES[1]];

function mockFetch({ placePolicies = US_PLACE_POLICIES, placeOk = true } = {}) {
  return jest.fn(async (url) => {
    const s = String(url);
    if (s.includes('/api/policies') && s.includes('place=')) {
      return placeOk
        ? { ok: true, json: async () => ({ policies: placePolicies, count: placePolicies.length }) }
        : { ok: false, status: 404, text: async () => 'not found' };
    }
    if (s.includes('/api/policies')) {
      return { ok: true, json: async () => ({ policies: ALL_POLICIES, count: ALL_POLICIES.length }) };
    }
    if (s.includes('/api/tags')) {
      return { ok: true, json: async () => ({}) };
    }
    return { ok: false, text: async () => 'not found' };
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe('PolicyList place-filter mode', () => {
  it('shows every policy in the normal all-policies view when no place is requested', async () => {
    global.fetch = mockFetch();
    render(<PolicyList />);

    expect(await screen.findByText('Federal Heat Reuse Act')).toBeInTheDocument();
    expect(screen.getByText('Sweden Heat Rule')).toBeInTheDocument();
    expect(screen.getByText('Showing 3 of 3 policies')).toBeInTheDocument();
    expect(screen.queryByText(/policies$/, { selector: '.policy-place-chip' })).not.toBeInTheDocument();
  });

  it('an external place request fetches /api/policies?place=<slug>, scopes the list, and shows the active-filter chip', async () => {
    global.fetch = mockFetch();
    render(
      <PolicyList externalPlace={{ slug: 'us', name: 'United States', nonce: 1 }} />,
    );

    expect(await screen.findByText('United States - 2 policies')).toBeInTheDocument();
    expect(screen.getByText('Federal Heat Reuse Act')).toBeInTheDocument();
    expect(screen.getByText('Minnesota Thermal Pilot')).toBeInTheDocument();
    expect(screen.queryByText('Sweden Heat Rule')).not.toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 policies')).toBeInTheDocument();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/policies?place=us'),
    );
  });

  it('scrolls the list into view when the place filter activates', async () => {
    global.fetch = mockFetch();
    const scrollSpy = jest.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollSpy;

    render(
      <PolicyList externalPlace={{ slug: 'us', name: 'United States', nonce: 1 }} />,
    );

    await screen.findByText('United States - 2 policies');
    expect(scrollSpy).toHaveBeenCalled();
  });

  it('clearing the chip returns to the all-policies view with client-side filters intact', async () => {
    global.fetch = mockFetch();
    render(
      <PolicyList externalPlace={{ slug: 'us', name: 'United States', nonce: 1 }} />,
    );

    await screen.findByText('United States - 2 policies');

    fireEvent.change(screen.getByLabelText('Filter by name'), { target: { value: 'Minnesota' } });
    expect(screen.getByText('Showing 1 of 2 policies')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear United States filter' }));

    await waitFor(() => {
      expect(screen.queryByText('United States - 2 policies')).not.toBeInTheDocument();
    });
    // The name filter ("Minnesota") is still applied to the full list.
    expect(screen.getByText('Minnesota Thermal Pilot')).toBeInTheDocument();
    expect(screen.queryByText('Federal Heat Reuse Act')).not.toBeInTheDocument();
    expect(screen.queryByText('Sweden Heat Rule')).not.toBeInTheDocument();
  });

  it('a fresh nonce for the same place re-fetches', async () => {
    global.fetch = mockFetch();
    const { rerender } = render(
      <PolicyList externalPlace={{ slug: 'us', name: 'United States', nonce: 1 }} />,
    );
    await screen.findByText('United States - 2 policies');
    const callsAfterFirst = global.fetch.mock.calls.filter((call) => String(call[0]).includes('place=us')).length;

    rerender(
      <PolicyList externalPlace={{ slug: 'us', name: 'United States', nonce: 2 }} />,
    );

    await waitFor(() => {
      const callsAfterSecond = global.fetch.mock.calls.filter((call) => String(call[0]).includes('place=us')).length;
      expect(callsAfterSecond).toBeGreaterThan(callsAfterFirst);
    });
  });

  it('surfaces an error without crashing when the place fetch fails', async () => {
    global.fetch = mockFetch({ placeOk: false });
    render(
      <PolicyList externalPlace={{ slug: 'atlantis', name: 'Atlantis', nonce: 1 }} />,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load policies for Atlantis.');
  });
});
