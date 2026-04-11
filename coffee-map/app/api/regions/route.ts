/**
 * GET /api/regions — proxies to FastAPI admin regions list.
 * Requires X-Admin-Key header.
 */
export async function GET(request: Request): Promise<Response> {
  const backendUrl = process.env.BACKEND_URL
  if (!backendUrl) {
    return Response.json({ error: 'BACKEND_URL not configured' }, { status: 500 })
  }

  const adminKey = request.headers.get('x-admin-key') ?? ''

  try {
    const upstream = await fetch(`${backendUrl}/regions/`, {
      headers: { 'X-Admin-Key': adminKey },
      cache: 'no-store',
    })
    const data = await upstream.json()
    return Response.json(data, { status: upstream.status })
  } catch {
    return Response.json({ error: 'Failed to reach backend' }, { status: 502 })
  }
}
