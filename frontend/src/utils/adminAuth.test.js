import { adminHeaders, getAdminToken, setAdminToken } from './adminAuth';

describe('adminAuth', () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  describe('getAdminToken', () => {
    it('returns an empty string when no token is stored', () => {
      expect(getAdminToken()).toBe('');
    });

    it('returns a previously stored token', () => {
      setAdminToken('secret-token');
      expect(getAdminToken()).toBe('secret-token');
    });
  });

  describe('setAdminToken', () => {
    it('clears the stored token when called with an empty string', () => {
      setAdminToken('secret-token');
      setAdminToken('');
      expect(getAdminToken()).toBe('');
    });
  });

  describe('adminHeaders', () => {
    it('returns an empty object when no token is stored', () => {
      expect(adminHeaders()).toEqual({});
    });

    it('returns the X-Admin-Token header when a token is stored', () => {
      setAdminToken('secret-token');
      expect(adminHeaders()).toEqual({ 'X-Admin-Token': 'secret-token' });
    });
  });
});
