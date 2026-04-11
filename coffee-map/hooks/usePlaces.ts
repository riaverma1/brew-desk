'use client'

import { useEffect, useRef, useState } from 'react'
import { fetchNearbyPlaces } from '@/lib/api-client'
import { boundsToCenter } from '@/lib/map-utils'
import type { MapBounds, PlacePin } from '@/types'

/**
 * Fetches PlacePin[] from /api/places whenever bounds changes.
 * AbortController per fetch — aborts on every new bounds change to prevent
 * stale-response pin flicker.
 * Uses JSON.stringify(bounds) as dep key to avoid infinite loops from
 * object reference changes.
 */
export function usePlaces(bounds: MapBounds | null): {
  places: PlacePin[]
  regionStatus: string | null
  isLoading: boolean
} {
  const [places, setPlaces] = useState<PlacePin[]>([])
  const [regionStatus, setRegionStatus] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const boundsKey = bounds ? JSON.stringify(bounds) : null

  useEffect(() => {
    if (!bounds) return

    // Abort any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const center = boundsToCenter(bounds)
    setIsLoading(true)

    fetchNearbyPlaces(
      { lat: center.lat, lng: center.lng, bounds },
      controller.signal
    )
      .then((data) => {
        if (controller.signal.aborted) return
        setPlaces((prev) => {
          const existingIds = new Set(prev.map((p) => p.place_id))
          const newPlaces = data.places.filter((p) => !existingIds.has(p.place_id))
          return newPlaces.length > 0 ? [...prev, ...newPlaces] : prev
        })
        setRegionStatus(data.region_status)
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundsKey])

  return { places, regionStatus, isLoading }
}
