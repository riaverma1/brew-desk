/**
 * POST /api/places — proxies nearby-search to FastAPI.
 * BACKEND_URL is server-only (no NEXT_PUBLIC_ prefix).
 * cache: 'no-store' prevents Next.js from caching map responses.
 */
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
    })

    const data = await upstream.json()
    return Response.json(data, { status: upstream.status })
  } catch {
    return Response.json(
      { error: 'Failed to reach backend', places: [], region_status: null, region_id: null },
      { status: 502 }
    )
  }
}
