'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useMapBounds } from '@/hooks/useMapBounds'
import { usePlaces } from '@/hooks/usePlaces'
import type { PlacePin as PlacePinType } from '@/types'
import { Header } from '@/components/Header'
import { ColdRegionBanner } from './ColdRegionBanner'
import { CrawlingIndicator } from './CrawlingIndicator'
import { InfoCard } from './InfoCard'
import { MapLegend } from './MapLegend'
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
  const [openNowOnly, setOpenNowOnly] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)

  const bounds = useMapBounds(mapReady ? mapRef.current : null)
  const { places, regionStatus, isLoading } = usePlaces(bounds)

  const visiblePlaces = openNowOnly
    ? places.filter((p) => p.regular_opening_hours?.openNow === true)
    : places

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

  // Show onboarding tooltip once per browser, auto-dismiss after 6s
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('brewdesk_onboarded')) {
      setShowOnboarding(true)
      const timer = setTimeout(() => {
        setShowOnboarding(false)
        localStorage.setItem('brewdesk_onboarded', '1')
      }, 6000)
      return () => clearTimeout(timer)
    }
  }, [])

  const dismissOnboarding = () => {
    setShowOnboarding(false)
    localStorage.setItem('brewdesk_onboarded', '1')
  }

  // BUG-3: stable reference prevents PlacePin useEffect from re-running on every render
  const handlePinClick = useCallback((placeId: string) => {
    const place = places.find((p) => p.place_id === placeId) ?? null
    setSelectedPlace(place)
  }, [places])

  const handleCloseCard = () => setSelectedPlace(null)

  // BUG-6: re-anchor selectedPlace when places refresh after a pan
  useEffect(() => {
    if (!selectedPlace) return
    const found = places.find((p) => p.place_id === selectedPlace.place_id)
    setSelectedPlace(found ?? null)
  }, [places])

  return (
    <div className="flex flex-col w-full h-full">
      <Header openNowOnly={openNowOnly} onToggleOpenNow={() => setOpenNowOnly((v) => !v)} />

      <div className="relative flex-1 min-h-0">
      <div ref={mapDivRef} className="w-full h-full" />

      {/* Place pins */}
      {mapReady && mapRef.current &&
        visiblePlaces.map((place) => (
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
      {isLoading && places.length === 0 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-white border border-gray-200 shadow-md rounded-full px-4 py-2 text-sm text-gray-700 flex items-center gap-2 pointer-events-none select-none">
          <svg className="w-3.5 h-3.5 text-gray-400 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span>Connecting&hellip;</span>
        </div>
      )}
      {isLoading && places.length > 0 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-white/90 backdrop-blur-sm shadow-md rounded-full px-3 py-1 text-sm text-gray-600 flex items-center gap-2 pointer-events-none select-none">
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
          Finding spots&hellip;
        </div>
      )}
      <CrawlingIndicator visible={regionStatus === 'crawling'} />
      <ColdRegionBanner visible={regionStatus === 'cold'} />

      <MapLegend />

      {showOnboarding && (
        <button
          onClick={dismissOnboarding}
          className="absolute bottom-20 left-1/2 -translate-x-1/2 z-20 bg-white/95 backdrop-blur-sm shadow-lg rounded-xl px-4 py-2.5 text-sm text-gray-700 max-w-xs text-center"
        >
          Scores are based on community mentions from Reddit, Instagram & more. Tap to dismiss.
        </button>
      )}
      </div>
    </div>
  )
}
