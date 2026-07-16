import { DEFAULT_CHANNELS, buildChannels } from './scanTargets';

describe('DEFAULT_CHANNELS', () => {
  it('defaults to crawl, law_apis, and transposition', () => {
    expect(DEFAULT_CHANNELS).toEqual(['crawl', 'law_apis', 'transposition']);
  });
});

describe('buildChannels', () => {
  it('returns the selected channels when provided', () => {
    expect(buildChannels(['crawl', 'news'])).toEqual(['crawl', 'news']);
  });

  it('falls back to crawl-only when no channels are selected', () => {
    expect(buildChannels([])).toEqual(['crawl']);
  });

  it('falls back to crawl-only when channels is undefined', () => {
    expect(buildChannels(undefined)).toEqual(['crawl']);
  });
});

describe('buildScanRequests', () => {
  const domainsByGroup = {
    us_states: [
      { id: 'ca_leg', region: ['california', 'us_states'] },
      { id: 'ct_deep', region: ['connecticut', 'us_states'] },
      { id: 'legiscan_api', region: ['us', 'us_states'] },
    ],
  };

  beforeEach(() => {
    global.fetch = jest.fn(async (url) => {
      const group = decodeURIComponent(url.split('group=')[1]);
      return {
        ok: true,
        json: async () => ({ domains: domainsByGroup[group] || [] }),
      };
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('consolidates all resolved domains into ONE scan request', async () => {
    const { buildScanRequests } = require('./scanTargets');
    const requests = await buildScanRequests(['group:us_states'], {
      channels: ['crawl', 'law_apis'],
    });

    expect(requests).toHaveLength(1);
    expect(requests[0].domains).toBe('ca_leg,ct_deep,legiscan_api');
    expect(requests[0].channels).toEqual(['crawl', 'law_apis']);
  });

  it('discover mode still issues one request per target', async () => {
    const { buildScanRequests } = require('./scanTargets');
    const requests = await buildScanRequests(
      ['group:sweden', 'group:denmark'],
      { discover: true, channels: ['crawl'] },
    );

    expect(requests).toHaveLength(2);
    expect(requests.map((r) => r.domains)).toEqual(['sweden', 'denmark']);
  });
});
