import { expect, test } from '@playwright/test'

// The production bundle (vite preview), not the dev server.
test.use({ baseURL: 'http://localhost:4173' })

const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e5e7eb' } }],
}

test('the built app loads its map worker and runs a whole journey without errors', async ({
  page,
}) => {
  const problems: string[] = []
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console: ${message.text()}`)
  })
  const workers: { status: number; type: string }[] = []
  page.on('response', (response) => {
    if (/maplibre-gl-worker/.test(response.url())) {
      workers.push({ status: response.status(), type: response.headers()['content-type'] ?? '' })
    }
  })
  await page.route(/openfreemap/, (route) => route.fulfill({ json: BLANK_STYLE }))

  await page.goto('/')
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
  await expect(page.getByTestId('recommendation')).toBeVisible()
  await page.getByRole('slider').fill('12')
  await page.getByRole('radio', { name: 'Wind' }).click()
  await page
    .getByRole('region', { name: /^Checkpoints on Route/ })
    .getByRole('button')
    .nth(2)
    .click()
  await expect(page.locator('.maplibregl-popup')).toContainText(/CP 3 · Mile/)

  // The worker file was fetched as a script. Without it nothing but the basemap is drawn.
  expect(workers.length).toBeGreaterThan(0)
  for (const worker of workers) {
    expect(worker.status).toBe(200)
    expect(worker.type).toMatch(/javascript/)
  }
  expect(problems).toEqual([])
})
