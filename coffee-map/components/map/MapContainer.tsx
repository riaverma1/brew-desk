'use client'

import { useEffect, useRef, useState } from 'react'
import { useMapBounds } from '@/hooks/useMapBounds'
import { usePlaces } from '@/hooks/usePlaces'
import type { PlacePin as PlacePinType } from '@/types'
import { ColdRegionBanner } from './ColdRegionBanner'
import { CrawlingIndicator } from './CrawlingIndicator'
import { InfoCard } from './InfoCard'
import { PlacePin } from './PlacePin'

// NYC fallback center (used only if geolocation is denied/unavailable)
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
  const userMarkerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const [mapReady, setMapReady] = useState(false)
  const [selectedPlace, setSelectedPlace] = useState<PlacePinType | null>(null)

  const bounds = useMapBounds(mapReady ? mapRef.current : null)
  const { places, regionStatus, isLoading } = usePlaces(bounds)

  // Initialize map, then pan to user's location if geolocation is available
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return

    const initMap = () => {
      if (!mapDivRef.current || mapRef.current) return
      if (!window.google?.maps) return

      const mapId = process.env.NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID
      if (!mapId) {
        console.warn('NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID not set — AdvancedMarkerElement may fail.')
      }

      const map = new google.maps.Map(mapDivRef.current, {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        mapId: mapId ?? '',
        disableDefaultUI: false,
        clickableIcons: false,
      })
      mapRef.current = map

      // Request location — browser will prompt the user for permission
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            const { lat, lng } = { lat: pos.coords.latitude, lng: pos.coords.longitude }
            map.panTo({ lat, lng })
            map.setZoom(14)

            // Green dot for current location
            const { AdvancedMarkerElement } = await google.maps.importLibrary('marker') as google.maps.MarkerLibrary
            const dot = document.createElement('div')
            dot.style.cssText = `
              width: 16px; height: 16px; border-radius: 50%;
              background: #22c55e; border: 2.5px solid white;
              box-shadow: 0 0 0 2px #22c55e;
            `
            userMarkerRef.current = new AdvancedMarkerElement({ map, position: { lat, lng }, content: dot })
          },
          () => {
            // Permission denied or unavailable — stay on NYC default
          },
          { timeout: 8000, maximumAge: 60_000 }
        )
      }

      setMapReady(true)
    }

    if (window.google?.maps) {
      initMap()
    } else {
      const script = document.querySelector<HTMLScriptElement>('script[src*="maps.googleapis.com"]')
      script?.addEventListener('load', initMap)
      return () => script?.removeEventListener('load', initMap)
    }
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

      {/* Status indicators */}
      <CrawlingIndicator visible={regionStatus === 'crawling'} />
      <ColdRegionBanner visible={regionStatus === 'cold'} />
    </div>
  )
}
