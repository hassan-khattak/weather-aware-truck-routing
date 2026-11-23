import { expect, test, type Browser } from '@playwright/test'

// A blank style keeps the test independent of external tile servers.
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e5e7eb' } }],
}

/** Everything the page shows that is a time or a duration, from one run of the sample trip. */
async function timesShown(browser: Browser, timezoneId: string, now: number) {
  const context = await browser.newContext({ timezoneId, baseURL: 'http://localhost:5173' })
  const page = await context.newPage()
  await page.clock.install({ time: now }) // the same instant in both browsers
  await page.route(/openfreemap/, (route) => route.fulfill({ json: BLANK_STYLE }))
  await page.goto('/')
  await page.getByRole('button', { name: /Chicago → Dallas/ }).click()
  await expect(page.getByTestId('recommendation')).toBeVisible()
  const slider = page.getByRole('slider', { name: 'Hours after departure' })
  await expect(slider).toBeVisible()

  const summary = await page.getByText(/^Chicago → Dallas · /).textContent()
  const cards = await page
    .getByRole('region', { name: 'Routes' })
    .getByRole('button', { name: /^Route/ })
    .allTextContents()
  const rows = await page
    .getByRole('region', { name: /^Checkpoints on Route/ })
    .getByRole('button')
    .allTextContents()
  const labels: string[] = []
  for (const hour of ['0', '12', '30']) {
    await slider.fill(hour)
    await expect(page.getByText(new RegExp(`^\\+${hour}h · `))).toBeVisible()
    labels.push((await page.getByText(new RegExp(`^\\+${hour}h · `)).textContent()) ?? '')
  }
  await context.close()
  return { summary, cards, rows, labels }
}

test('every time shown is the same whatever time zone the browser is in (scenario 5)', async ({
  browser,
}) => {
  const now = Date.now()
  const karachi = await timesShown(browser, 'Asia/Karachi', now)
  const newYork = await timesShown(browser, 'America/New_York', now)

  expect(karachi.rows.length).toBeGreaterThan(10)
  expect(karachi.summary).toMatch(/CST|CDT/) // the origin's zone, not the browser's
  expect(karachi).toEqual(newYork)
})
