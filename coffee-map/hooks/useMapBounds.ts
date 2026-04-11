'use client'

import { useEffect, useRef, useState } from 'react'
import type { MapBounds } from '@/types'

/**
 * Attaches a debounced bounds_changed listener to the Maps instance.
 * Accepts the map instance directly (not a ref) so the effect re-runs
 * when the map becomes available. Returns null until the first bounds fire.
 * 800ms debounce to avoid firing on every pixel of a pan gesture.
 */
export function useMapBounds(map: google.maps.Map | null): MapBounds | null {
  const [bounds, setBounds] = useState<MapBounds | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!map) return

    const listener = map.addListener('bounds_changed', () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        const b = map.getBounds()
        if (!b) return
        const ne = b.getNorthEast()
        const sw = b.getSouthWest()
        setBounds({
          north: ne.lat(),
          south: sw.lat(),
          east: ne.lng(),
          west: sw.lng(),
        })
      }, 800)
    })

    return () => {
      google.maps.event.removeListener(listener)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [map])

  return bounds
}
