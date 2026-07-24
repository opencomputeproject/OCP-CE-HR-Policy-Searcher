/**
 * The production Docker build sets REACT_APP_API_BASE_URL="" (empty string)
 * so the built app calls the API on the same origin it's served from,
 * instead of the dev default. `||` treats an empty string as falsy, so a
 * naive `process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000'`
 * silently falls back to localhost even when the env var was explicitly
 * set to empty — these tests pin the intended behavior: unset means
 * localhost:8000 (dev default), explicitly empty means same-origin.
 */

describe('API_BASE_URL', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...ORIGINAL_ENV };
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  test('defaults to localhost:8000 when REACT_APP_API_BASE_URL is unset', () => {
    delete process.env.REACT_APP_API_BASE_URL;
    const { API_BASE_URL } = require('./api');
    expect(API_BASE_URL).toBe('http://localhost:8000');
  });

  test('an explicitly empty REACT_APP_API_BASE_URL means same-origin, not the localhost fallback', () => {
    process.env.REACT_APP_API_BASE_URL = '';
    const { API_BASE_URL } = require('./api');
    expect(API_BASE_URL).toBe('');
  });

  test('uses an explicit non-empty value as-is', () => {
    process.env.REACT_APP_API_BASE_URL = 'https://example.com';
    const { API_BASE_URL } = require('./api');
    expect(API_BASE_URL).toBe('https://example.com');
  });

  test('apiUrl() with a same-origin base produces a root-relative URL', () => {
    process.env.REACT_APP_API_BASE_URL = '';
    const { apiUrl } = require('./api');
    expect(apiUrl('/api/domains')).toBe('/api/domains');
  });

  test('WS_BASE_URL stays empty (same-origin) when API_BASE_URL is empty', () => {
    process.env.REACT_APP_API_BASE_URL = '';
    const { WS_BASE_URL } = require('./api');
    expect(WS_BASE_URL).toBe('');
  });
});
