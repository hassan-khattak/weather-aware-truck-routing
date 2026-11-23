import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? sources(path) : /\.(ts|tsx)$/.test(name) ? [path] : []
  })
}

describe('heatmap rendering rule (plan section 10)', () => {
  it("never uses MapLibre's `heatmap` layer type (it draws point density, not values)", () => {
    const offenders = sources(join(process.cwd(), 'src')).filter((file) =>
      /type:\s*['"]heatmap['"]/.test(readFileSync(file, 'utf8')),
    )
    expect(offenders).toEqual([])
  })
})
