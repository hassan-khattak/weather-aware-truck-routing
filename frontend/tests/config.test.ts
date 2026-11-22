import { describe, expect, it } from 'vitest'
import { DEFAULT_MAP_STYLE_URL, readConfig } from '../src/config'

describe('readConfig', () => {
  it('defaults to the OpenFreeMap style when nothing is set', () => {
    expect(readConfig({}).mapStyleUrl).toBe(DEFAULT_MAP_STYLE_URL)
  })

  it('reads the style URL from the environment', () => {
    expect(readConfig({ VITE_MAP_STYLE_URL: 'https://example.com/style.json' }).mapStyleUrl).toBe(
      'https://example.com/style.json',
    )
  })

  it('ignores a blank value', () => {
    expect(readConfig({ VITE_MAP_STYLE_URL: '  ' }).mapStyleUrl).toBe(DEFAULT_MAP_STYLE_URL)
  })
})
