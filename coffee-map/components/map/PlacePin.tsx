'use client'

import { useEffect, useRef } from 'react'
import type { PlacePin as PlacePinType } from '@/types'

interface PlacePinProps {
  map: google.maps.Map
  place: PlacePinType
  onClick: (placeId: string) => void
}

/**
 * AdvancedMarkerElement wrapper for a single enriched place pin.
 * All pins are red — indicates a WFH-mentioned place.
 * Requires mapId to be set on the Map instance at init time.
 * Cleanup: marker.map = null on unmount.
 */
export function PlacePin({ map, place, onClick }: PlacePinProps) {
  const markerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)

  useEffect(() => {
    const pin = new google.maps.marker.PinElement({
      background: '#ef4444',
      borderColor: '#b91c1c',
      glyphColor: '#ffffff',
      scale: 1.1,
    })

    const marker = new google.maps.marker.AdvancedMarkerElement({
      map,
      position: { lat: place.lat, lng: place.lng },
      title: place.name,
      content: pin,
    })

    marker.addListener('gmp-click', () => onClick(place.place_id))
    markerRef.current = marker

    return () => {
      if (markerRef.current) {
        markerRef.current.map = null
        markerRef.current = null
      }
    }
  }, [map, place, onClick])

  return null
}
