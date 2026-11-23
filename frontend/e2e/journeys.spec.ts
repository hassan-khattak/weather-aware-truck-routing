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

interface MapProject {
  queryRenderedFeatures(options: { layers: string[] }): { geometry: unknown }[]
  isMoving(): boolean
  project(lngLat: [number, number]): { x: number; y: number }
  getCanvas(): { getBoundingClientRect(): { left: number; top: number } }
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

test('a checkpoint dot opens a tooltip with its level and reason', async ({ page }) => {
  await runSample(page)
  await expect(page.getByTestId('recommendation')).toBeVisible()

  // Wait for the dots, then click the first High-or-worse one (or any) where it is drawn.
  const target = await page.waitForFunction(() => {
    const map = (window as unknown as { __truckMap: TestMap & MapProject }).__truckMap
    if (map.isMoving()) return null // still fitting the routes
    const features = map.queryRenderedFeatures({ layers: ['checkpoint-dots'] })
    if (features.length === 0) return null
    const geometry = features[0].geometry as { coordinates: [number, number] }
    const point = map.project(geometry.coordinates)
    const box = map.getCanvas().getBoundingClientRect()
    return { x: box.left + point.x, y: box.top + point.y }
  })
  const { x, y } = (await target.jsonValue()) as { x: number; y: number }
  await page.mouse.click(x, y)

  const popup = page.locator('.maplibregl-popup')
  await expect(popup).toContainText(/CP \d+ · Mile \d+/)
  await expect(popup).toContainText(/(LOW|MODERATE|HIGH|SEVERE|NO TRAVEL|NO FORECAST)/)
  await expect(popup).toContainText('ETA')
})

test('clicking a checkpoint row pins its tooltip', async ({ page }) => {
  await runSample(page)
  const list = page.getByRole('region', { name: /^Checkpoints on Route/ })
  await list.getByRole('button').nth(2).click()
  await expect(page.locator('.maplibregl-popup')).toContainText(/CP 3 · Mile \d+/)
  await page.keyboard.press('Escape')
  await expect(page.locator('.maplibregl-popup')).toHaveCount(0)
})

async function truckPosition(page: Page) {
  return page.evaluate(() => {
    const map = (window as unknown as { __truckMap: TruckMap }).__truckMap
    const feature = map.querySourceFeatures('truck')[0]
    return feature ? (feature.geometry as { coordinates: number[] }).coordinates : null
  })
}

interface TruckMap {
  querySourceFeatures(source: string): { geometry: unknown }[]
}

test('moving the slider to +12h updates the label and moves the truck, with no network calls', async ({
  page,
}) => {
  await runSample(page)
  const slider = page.getByRole('slider', { name: 'Hours after departure' })
  await expect(slider).toBeVisible()
  await expect(page.getByText(/^\+0h · /)).toBeVisible()
  await expect.poll(() => truckPosition(page)).not.toBeNull()
  const before = await truckPosition(page)

  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))

  await slider.fill('12')
  await expect(page.getByText(/^\+12h · /)).toBeVisible()
  await expect.poll(() => truckPosition(page)).not.toEqual(before)

  // Keyboard: Shift+Right is six hours.
  await slider.focus()
  await page.keyboard.press('Shift+ArrowRight')
  await expect(page.getByText(/^\+18h · /)).toBeVisible()

  expect(requests).toEqual([]) // dragging the slider never touches the network
})

test('Play advances the hour, can be paused, and uses no network or long frames', async ({
  page,
}) => {
  await runSample(page)
  await expect(page.getByRole('slider')).toBeVisible()
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))

  // Record the time between animation frames while Play runs.
  await page.evaluate(() => {
    const w = window as unknown as { __frames: number[] }
    w.__frames = []
    let last = performance.now()
    const loop = () => {
      const now = performance.now()
      w.__frames.push(now - last)
      last = now
      requestAnimationFrame(loop)
    }
    requestAnimationFrame(loop)
  })
  await page.getByRole('button', { name: /play/i }).click()
  await expect(page.getByText(/^\+[3-9]h · /)).toBeVisible()
  await page.getByRole('button', { name: /pause/i }).click()
  await expect(page.getByRole('button', { name: /play/i })).toBeVisible()

  const frames = await page.evaluate(() => (window as unknown as { __frames: number[] }).__frames)
  const sorted = [...frames].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  const p95 = sorted[Math.floor(sorted.length * 0.95)]
  const longest = sorted[sorted.length - 1]
  console.log(
    `Play frames: ${frames.length}, median ${median.toFixed(1)} ms, p95 ${p95.toFixed(1)} ms, longest ${longest.toFixed(0)} ms (software rendering)`,
  )
  // Headless Chrome on a shared CI runner renders in software, so exact frame times are noisy
  // (p95 ranged 18 to 146 ms). This only catches gross regressions: a slow typical frame, or the
  // main thread being blocked for seconds. The 60 fps claim is measured by hand on real hardware.
  expect(median).toBeLessThan(100)
  expect(longest).toBeLessThan(1500)
  expect(requests).toEqual([])
})
