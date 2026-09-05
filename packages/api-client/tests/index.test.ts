import { describe, expect, it } from 'vitest'
import { ApiError, createApiClient } from '../src'

describe('api client', () => {
  it('sends JSON requests and returns an explicit DTO', async () => {
    const client = createApiClient({
      baseUrl: 'https://api.example.test',
      fetcher: async (input, init) => {
        expect(input).toBe('https://api.example.test/books')
        expect(init?.method).toBe('POST')
        expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' })
        expect(init?.body).toBe(JSON.stringify({ title: '测试书' }))
        return new Response(JSON.stringify({ book_no: 'BK-1', title: '测试书' }), { status: 200 })
      },
    })

    await expect(client.post('/books', { title: '测试书' })).resolves.toEqual({ book_no: 'BK-1', title: '测试书' })
  })

  it('maps API error envelopes without treating HTTP errors as successful data', async () => {
    const client = createApiClient({
      fetcher: async () => new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: '请登录', request_id: 'REQ-1' } }), { status: 401 }),
    })

    await expect(client.get('/private')).rejects.toEqual(new ApiError(401, 'UNAUTHORIZED', '请登录', 'REQ-1'))
  })

  it('propagates session and idempotency headers for protected writes', async () => {
    const client = createApiClient({
      token: 'session-token',
      fetcher: async (_input, init) => {
        expect(init?.headers).toMatchObject({
          Authorization: 'Bearer session-token',
          'Idempotency-Key': 'request-1',
        })
        return new Response(JSON.stringify({ ok: true }), { status: 200 })
      },
    })

    await expect(client.put('/wallet', { amount: 1 }, { idempotencyKey: 'request-1' })).resolves.toEqual({ ok: true })
  })
})
