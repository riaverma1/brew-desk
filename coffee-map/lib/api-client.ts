/**
 * Centralized fetch helpers for all hooks.
 * On 4xx/5xx: returns empty state — map degrades gracefully, never throws.
 */
import type {
  MentionsResponse,
  NearbySearchRequest,
  NearbySearchResponse,
} from '@/types'

export async function fetchNearbyPlaces(
  req: NearbySearchRequest,
  signal?: AbortSignal
): Promise<NearbySearchResponse> {
  try {
    const resp = await fetch('/api/places', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
      cache: 'no-store',
    })
    if (!resp.ok) return { places: [], region_status: null, region_id: null }
    return resp.json()
  } catch {
    return { places: [], region_status: null, region_id: null }
  }
}

export async function fetchMentions(
  placeId: string,
  signal?: AbortSignal
): Promise<MentionsResponse> {
  try {
    const resp = await fetch(`/api/places/${placeId}/mentions`, {
      signal,
      cache: 'no-store',
    })
    if (!resp.ok) return { place_id: placeId, mentions: [] }
    return resp.json()
  } catch {
    return { place_id: placeId, mentions: [] }
  }
}
