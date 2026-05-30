'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useMapBounds } from '@/hooks/useMapBounds'
import { isOpenNow } from '@/lib/map-utils'
import { usePlaces } from '@/hooks/usePlaces'
import type { PlacePin as PlacePinType } from '@/types'
import { Header } from '@/components/Header'
import { ColdRegionBanner } from './ColdRegionBanner'
import { CrawlingIndicator } from './CrawlingIndicator'
import { InfoCard } from './InfoCard'
import { MapLegend } from './MapLegend'
import { PlacePin } from './PlacePin'
import { PlaceList } from './PlaceList'

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
  const [mobileView, setMobileView] = useState<'map' | 'list'>('map')

  const bounds = useMapBounds(mapReady ? mapRef.current : null)
  const { places, regionStatus, isLoading } = usePlaces(bounds)

  const inViewportPlaces = bounds
    ? places.filter(
        (p) =>
          p.lat <= bounds.north &&
          p.lat >= bounds.south &&
          p.lng <= bounds.east &&
          p.lng >= bounds.west
      )
    : places

  const visiblePlaces = openNowOnly
    ? inViewportPlaces.filter((p) => isOpenNow(p) === true)
    : inViewportPlaces

  const sortedVisiblePlaces = [...visiblePlaces].sort(
    (a, b) => b.mention_count - a.mention_count
  )

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

      {/* Content: sidebar + map (desktop) or map/list toggle (mobile) */}
      <div className="flex-1 min-h-0 flex overflow-hidden">

        {/* Sidebar — desktop only */}
        <aside className="hidden md:flex flex-col w-80 shrink-0 border-r border-gray-100 bg-white overflow-hidden">
          <PlaceList
            places={sortedVisiblePlaces}
            selectedId={selectedPlace?.place_id ?? null}
            onSelect={handlePinClick}
          />
        </aside>

        {/* Map — always on desktop, only in 'map' mode on mobile */}
        <div className={`flex-1 relative min-h-0 ${mobileView === 'list' ? 'hidden md:block' : ''}`}>
          <div ref={mapDivRef} className="w-full h-full" />

          {/* Place pins */}
          {mapReady && mapRef.current &&
            sortedVisiblePlaces.map((place) => (
              <PlacePin
                key={place.place_id}
                map={mapRef.current!}
                place={place}
                onClick={handlePinClick}
              />
            ))}

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
              <span className="h-2 w-2 rounded-full bg-amber-800 animate-pulse" />
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

        {/* Mobile list view — only in 'list' mode */}
        <div className={`md:hidden flex-1 overflow-y-auto bg-white ${mobileView === 'map' ? 'hidden' : ''}`}>
          <PlaceList
            places={sortedVisiblePlaces}
            selectedId={selectedPlace?.place_id ?? null}
            onSelect={handlePinClick}
          />
        </div>
      </div>

      {/* Mobile bottom tab bar */}
      <nav className="md:hidden shrink-0 border-t border-gray-100 bg-white z-20 flex">
        <button
          onClick={() => setMobileView('list')}
          className={`flex-1 flex flex-col items-center justify-center py-2.5 gap-0.5 text-xs font-medium transition-colors ${
            mobileView === 'list' ? 'text-amber-900' : 'text-gray-400'
          }`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          <span>List {sortedVisiblePlaces.length > 0 ? `(${sortedVisiblePlaces.length})` : ''}</span>
        </button>
        <button
          onClick={() => setMobileView('map')}
          className={`flex-1 flex flex-col items-center justify-center py-2.5 gap-0.5 text-xs font-medium transition-colors ${
            mobileView === 'map' ? 'text-amber-900' : 'text-gray-400'
          }`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
          </svg>
          <span>Map</span>
        </button>
      </nav>

      {/* InfoCard — fixed overlay, works on both map and list views */}
      {selectedPlace && (
        <InfoCard
          placeId={selectedPlace.place_id}
          place={selectedPlace}
          onClose={handleCloseCard}
        />
      )}
    </div>
  )
}
