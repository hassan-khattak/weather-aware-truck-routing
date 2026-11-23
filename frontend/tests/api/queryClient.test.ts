import { describe, expect, it } from 'vitest'
import { createQueryClient } from '../../src/api/queryClient'

describe('createQueryClient', () => {
  it('runs requests even when the browser reports it is offline, so failures are shown', async () => {
    const client = createQueryClient()
    expect(client.getDefaultOptions().queries?.networkMode).toBe('always')

    let calls = 0
    const failing = client.fetchQuery({
      queryKey: ['offline'],
      queryFn: () => {
        calls += 1
        throw new Error('network down')
      },
      retry: false,
    })
    await expect(failing).rejects.toThrow('network down')
    expect(calls).toBe(1)
  })
})
