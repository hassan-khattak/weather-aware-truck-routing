import { expect, test, type Page } from '@playwright/test'

// A blank style keeps the tests independent of external tile servers.
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e5e7eb' } }],
}

interface TestMap {
  getStyle(): { sources: Record<string, { data?: { features?: unknown[] } }> }
  getLayer(id: string): unknown
}

test.beforeEach(async ({ page }) => {
  await page.route(/openfreemap/, (route) => route.fulfill({ json: BLANK_STYLE }))
})

async function runSample(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
}

test('sample trip shows routes on the map and a recommendation', async ({ page }) => {
  await runSample(page)

  await expect(page.getByTestId('recommendation')).toContainText('Recommended: Route')
  const cards = page.getByRole('region', { name: 'Routes' }).getByRole('button', { name: /^Route/ })
  expect(await cards.count()).toBeGreaterThanOrEqual(2)

  // Each route is drawn as a source with line data.
  const drawn = await page.evaluate(() => {
    const map = (window as unknown as { __truckMap: TestMap }).__truckMap
    return Object.values(map.getStyle().sources).filter((s) => s.data !== undefined).length
  })
  expect(drawn).toBeGreaterThanOrEqual(2)
})

test('choosing another route card switches the selection', async ({ page }) => {
  await runSample(page)
  const cards = page.getByRole('region', { name: 'Routes' }).getByRole('button', { name: /^Route/ })
  await expect(page.getByTestId('recommendation')).toBeVisible()

  const other = cards.filter({ hasNotText: 'Recommended' }).first()
  await other.click()
  await expect(other).toHaveAttribute('aria-pressed', 'true')
  await expect(cards.filter({ hasText: 'Recommended' }).first()).toHaveAttribute(
    'aria-pressed',
    'false',
  )
})
