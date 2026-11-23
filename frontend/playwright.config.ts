import { defineConfig } from '@playwright/test'

// Runs the real API in fixture mode (recorded TomTom and Open-Meteo data) and the Vite dev server.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  webServer: [
    {
      command: 'uv run python manage.py runserver 8000 --noreload',
      cwd: '../backend',
      url: 'http://localhost:8000/api/v1/health',
      reuseExistingServer: !process.env.CI,
      env: {
        DEBUG: 'True',
        PROVIDERS_MODE: 'fixtures',
        CACHE_BACKEND: 'locmem',
        DATABASE_URL: '',
      },
    },
    {
      command: 'npm run dev -- --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
