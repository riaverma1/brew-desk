'use client'

import { useEffect, useRef, useState } from 'react'
import { useMapBounds } from '@/hooks/useMapBounds'
import { usePlaces } from '@/hooks/usePlaces'
import type { PlacePin as PlacePinType } from '@/types'
import { ColdRegionBanner } from './ColdRegionBanner'
import { InfoCard } from './InfoCard'
import { PlacePin } from './PlacePin'

// NYC default center, zoom 13
const DEFAULT_CENTER = { lat: 40.7128, lng: -74.006 }
const DEFAULT_ZOOM = 13

/**
 * Central "use client" component. Owns the Google Maps instance, all map state,
 * and orchestrates data fetching on pan.
 *
 * Uses plain useRef + useEffect (not @googlemaps/react-wrapper) for App Router.
 * AdvancedMarkerElement requires mapId to be set at init time.
 */
export function MapContainer() {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<google.maps.Map | null>(null)
  const [mapReady, setMapReady] = useState(false)
  const [selectedPlace, setSelectedPlace] = useState<PlacePinType | null>(null)

  const bounds = useMapBounds(mapReady ? mapRef.current : null)
  const { places, regionStatus, isLoading } = usePlaces(bounds)

  // Initialize map
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return
    if (typeof window === 'undefined' || !window.google?.maps) return

    const mapId = process.env.NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID
    if (!mapId) {
      console.warn('NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID not set — AdvancedMarkerElement may fail.')
    }

    mapRef.current = new google.maps.Map(mapDivRef.current, {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      mapId: mapId ?? '',
      disableDefaultUI: false,
      clickableIcons: false,
    })

    setMapReady(true)
  }, [])

  const handlePinClick = (placeId: string) => {
    const place = places.find((p) => p.place_id === placeId) ?? null
    setSelectedPlace(place)
  }

  const handleCloseCard = () => setSelectedPlace(null)

  return (
    <div className="relative w-full h-full">
      <div ref={mapDivRef} className="w-full h-full" />

      {/* Place pins */}
      {mapReady && mapRef.current &&
        places.map((place) => (
          <PlacePin
            key={place.place_id}
            map={mapRef.current!}
            place={place}
            onClick={handlePinClick}
          />
        ))}

      {/* InfoCard */}
      {selectedPlace && (
        <InfoCard
          placeId={selectedPlace.place_id}
          place={selectedPlace}
          onClose={handleCloseCard}
        />
      )}

      {/* Cold region banner */}
      <ColdRegionBanner visible={regionStatus === 'cold'} />
    </div>
  )
}
