/**
 * GET /api/places/[place_id]/mentions — proxies to FastAPI.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ place_id: string }> }
): Promise<Response> {
  const { place_id } = await params
  const backendUrl = process.env.BACKEND_URL
  if (!backendUrl) {
    return Response.json({ error: 'BACKEND_URL not configured' }, { status: 500 })
  }

  try {
    const upstream = await fetch(
      `${backendUrl}/places/${place_id}/mentions`,
      { cache: 'no-store' }
    )
    const data = await upstream.json()
    return Response.json(data, { status: upstream.status })
  } catch {
    return Response.json(
      { place_id, mentions: [] },
      { status: 502 }
    )
  }
}
