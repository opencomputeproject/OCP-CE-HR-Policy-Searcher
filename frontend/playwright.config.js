// Real-input e2e smoke tests for the world map. These exist because synthetic
// pointer events (fireEvent/jsdom) cannot exercise pointer capture: a
// capture-on-press bug once made every real click dead while the entire unit
// suite stayed green. Run against a live dev stack (backend :8000 + frontend
// :3000, e.g. `npm run dev` from the repo root):
//
//   npx playwright install chromium   # once
//   npm run e2e
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    browserName: 'chromium',
  },
  reporter: [['list']],
});
