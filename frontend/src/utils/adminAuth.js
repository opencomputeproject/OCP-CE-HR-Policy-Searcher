const ADMIN_TOKEN_STORAGE_KEY = 'admin-token';

export function getAdminToken() {
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function setAdminToken(token) {
  try {
    if (token) {
      window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    } else {
      window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    }
  } catch {
    // sessionStorage can be unavailable in private or restricted browser modes.
  }
}

export function adminHeaders() {
  const token = getAdminToken();
  return token ? { 'X-Admin-Token': token } : {};
}
