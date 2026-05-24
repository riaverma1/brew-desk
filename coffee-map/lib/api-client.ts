/**
 * Centralized fetch helpers for all hooks.
 * On 4xx/5xx: returns empty state — map degrades gracefully, never throws.
 */
import type {
  MentionsResponse,
  NearbySearchRequest,
  NearbySearchResponse,
} from '@/types'

const EMPTY_NEARBY: NearbySearchResponse = { places: [], region_status: null, region_id: null }

export async function fetchNearbyPlaces(
  req: NearbySearchRequest,
  signal?: AbortSignal
): Promise<NearbySearchResponse> {
  const maxAttempts = 4
  const baseDelay = 2000

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) return EMPTY_NEARBY

    try {
      const resp = await fetch('/api/places', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
        signal,
        cache: 'no-store',
      })

      if (resp.ok) return resp.json()

      // Don't retry on client errors
      if (resp.status < 500) return EMPTY_NEARBY
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return EMPTY_NEARBY
    }

    if (attempt < maxAttempts - 1) {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, baseDelay * 2 ** attempt)
        signal?.addEventListener('abort', () => { clearTimeout(timer); reject() }, { once: true })
      }).catch(() => null)
    }
  }

  return EMPTY_NEARBY
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
