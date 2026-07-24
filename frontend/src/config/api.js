// A `typeof` string-check (not `||`) so an explicitly empty
// REACT_APP_API_BASE_URL ("" — what the production Docker build sets)
// means same-origin, not the localhost dev default. Only a truly unset
// (undefined) env var falls back to localhost. Written this way — rather
// than `?? 'http://localhost:8000'` — so that once webpack's DefinePlugin
// inlines the build-time env value, the ternary's condition is a
// plain compile-time-constant comparison Terser folds away, dropping the
// unreachable 'http://localhost:8000' literal entirely from a production
// build that set the env var to "".
export const API_BASE_URL =
  typeof process.env.REACT_APP_API_BASE_URL === 'string'
    ? process.env.REACT_APP_API_BASE_URL
    : 'http://localhost:8000';
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}
