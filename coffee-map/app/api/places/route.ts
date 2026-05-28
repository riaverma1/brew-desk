export const maxDuration = 60

export async function POST(request: Request): Promise<Response> {
  const backendUrl = process.env.BACKEND_URL
  if (!backendUrl) {
    return Response.json({ error: 'BACKEND_URL not configured' }, { status: 500 })
  }

  try {
    const body = await request.json()
    const upstream = await fetch(`${backendUrl}/places/nearby-search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: AbortSignal.timeout(55_000),
    })

    const text = await upstream.text()
    if (!upstream.ok) {
      console.error(`[/api/places] upstream ${upstream.status}:`, text.slice(0, 500))
      return Response.json(
        { error: `Backend error ${upstream.status}`, places: [], region_status: null, region_id: null },
        { status: upstream.status }
      )
    }
    const data = JSON.parse(text)
    return Response.json(data, { status: upstream.status })
  } catch (err) {
    const isTimeout = err instanceof DOMException && err.name === 'TimeoutError'
    console.error('[/api/places] upstream fetch failed:', err)
    return Response.json(
      { error: isTimeout ? 'Backend timed out' : 'Failed to reach backend', places: [], region_status: null, region_id: null },
      { status: 502 }
    )
  }
}
