import { expect, test, type Page } from '@playwright/test'

// A blank style keeps the tests independent of external tile servers.
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e5e7eb' } }],
}

test.beforeEach(async ({ page }) => {
  await page.route(/openfreemap/, (route) => route.fulfill({ json: BLANK_STYLE }))
})

/** Make the next call to `path` fail with `code` (the API honours this in fixture mode only). */
async function forceError(page: Page, path: string, code: string) {
  await page.route(`**/api/v1/${path}`, (route) =>
    route.continue({ headers: { ...route.request().headers(), 'x-force-error': code } }),
  )
}

const MESSAGES: [string, RegExp, boolean][] = [
  ['PROVIDER_UNAVAILABLE', /temporarily unavailable/i, true],
  ['RATE_LIMITED', /too many searches/i, true],
  ['NO_ROUTE', /no truck route found/i, false],
  ['OUT_OF_COVERAGE', /continental US/i, false],
]

for (const [code, message, canRetry] of MESSAGES) {
  test(`${code} from /routes shows a friendly message${canRetry ? ' and Try again' : ''}`, async ({
    page,
  }) => {
    await forceError(page, 'routes', code)
    await page.goto('/')
    await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
    await expect(page.getByRole('alert')).toContainText(message)
    await expect(page.getByRole('button', { name: /try again/i })).toHaveCount(canRetry ? 1 : 0)
    // The form is open again so the search can be changed.
    await expect(page.getByRole('combobox', { name: 'Origin' })).toBeVisible()
  })
}

test('a failed weather step keeps the routes and says the risk is unknown', async ({ page }) => {
  await forceError(page, 'risk', 'PROVIDER_UNAVAILABLE')
  await page.goto('/')
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
  await expect(page.getByRole('alert')).toContainText('weather risk is unknown')
  await expect(page.getByText('Weather risk unavailable').first()).toBeVisible()
  await expect(page.getByTestId('recommendation')).toHaveCount(0) // nothing is called safe
})

test('an expired trip is repeated silently', async ({ page }) => {
  let forced = false
  await page.route('**/api/v1/risk', (route) => {
    if (forced) return route.continue()
    forced = true
    return route.continue({
      headers: { ...route.request().headers(), 'x-force-error': 'TRIP_EXPIRED' },
    })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
  await expect(page.getByTestId('recommendation')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('going offline shows "can\'t reach the server" with Try again, and recovers', async ({
  page,
}) => {
  await page.goto('/')
  await page.context().setOffline(true)
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
  await expect(page.getByRole('alert')).toContainText(/can't reach the server/i)
  await page.context().setOffline(false)
  await page.getByRole('button', { name: /try again/i }).click()
  await expect(page.getByTestId('recommendation')).toBeVisible()
})

test('invalid input shows a friendly validation message (scenario 6)', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /find the safest route/i }).click()
  await expect(page.getByText(/choose an origin/i).first()).toBeVisible()
  await page.getByLabel(/cargo weight/i).fill('5')
  await page.getByRole('button', { name: /find the safest route/i }).click()
  await expect(page.getByText(/load must be between/i)).toBeVisible()
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('the slider is reachable above the sheet and nothing scrolls sideways', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
    const slider = page.getByRole('slider', { name: 'Hours after departure' })
    await expect(slider).toBeVisible()

    const sheet = await page.getByRole('complementary', { name: 'Trip planner' }).boundingBox()
    const track = await slider.boundingBox()
    expect(track!.y + track!.height).toBeLessThanOrEqual(sheet!.y + 1) // above the sheet

    await slider.fill('12')
    await expect(page.getByText(/^\+12h · /)).toBeVisible()

    const widths = await page.evaluate(() => [
      document.documentElement.scrollWidth,
      window.innerWidth,
    ])
    expect(widths[0]).toBeLessThanOrEqual(widths[1])

    // Folding the sheet leaves the title, gives the map room, and the slider drops with it.
    await page.getByRole('button', { name: /hide trip details/i }).click()
    const folded = await page.getByRole('complementary', { name: 'Trip planner' }).boundingBox()
    expect(folded!.height).toBeLessThan(sheet!.height)
    await expect.poll(async () => (await slider.boundingBox())!.y).toBeGreaterThan(track!.y)
  })
})
