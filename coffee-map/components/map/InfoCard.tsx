'use client'

import { useMentions } from '@/hooks/useMentions'
import type { PlacePin } from '@/types'
import { MentionCard } from '@/components/ui/MentionCard'
import { AttributePills } from './AttributePills'

interface InfoCardProps {
  placeId: string
  place: PlacePin
  onClose: () => void
}

function formatPrimaryType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function todaysHours(place: PlacePin): string | null {
  const descriptions = place.regular_opening_hours?.weekdayDescriptions
  if (!descriptions?.length) return null
  // Google: index 0 = Monday, index 6 = Sunday
  // JS getDay(): 0 = Sunday, 1 = Monday ... 6 = Saturday
  const todayIndex = (new Date().getDay() + 6) % 7
  return descriptions[todayIndex] ?? null
}

function googleMapsUrl(place: PlacePin): string {
  const name = encodeURIComponent(place.name)
  return `https://www.google.com/maps/search/?api=1&query=${name}&query_place_id=${place.place_id}`
}

/**
 * Side panel shown on pin click.
 * Renders static place data immediately; mentions load async.
 * Fixed overlay on mobile (bottom sheet), side panel on desktop.
 */
export function InfoCard({ placeId, place, onClose }: InfoCardProps) {
  const { mentions, isLoading } = useMentions(placeId)
  const hours = todaysHours(place)

  return (
    <div className="
      fixed bottom-0 left-0 right-0 z-30 bg-white shadow-xl rounded-t-2xl max-h-[70vh] overflow-y-auto border-t-4 border-green-600
      md:absolute md:top-4 md:right-4 md:bottom-auto md:left-auto md:w-80 md:rounded-xl md:max-h-[calc(100vh-2rem)] md:border-t-4 md:border-l-0
    ">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-gray-100">
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 truncate">{place.name}</h2>
          {place.address && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{place.address}</p>
          )}
          <AttributePills place={place} />
        </div>
        <button
          onClick={onClose}
          className="ml-2 text-gray-400 hover:text-gray-600 text-lg leading-none"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Photos */}
      {place.photos.length > 0 && (
        <div className="flex gap-2 px-4 py-3 overflow-x-auto border-b border-gray-100 scrollbar-hide">
          {place.photos.map((url, i) => (
            <img
              key={i}
              src={url}
              alt={`${place.name} photo ${i + 1}`}
              className="h-28 w-40 object-cover rounded-lg flex-shrink-0"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          ))}
        </div>
      )}

      {/* Google info row */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 border-b border-gray-100">
        {place.primary_type && (
          <span className="text-xs text-gray-500 bg-gray-100 rounded-full px-2 py-0.5">
            {formatPrimaryType(place.primary_type)}
          </span>
        )}
        <a
          href={googleMapsUrl(place)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline ml-auto"
        >
          Open in Google Maps →
        </a>
      </div>

      {/* Today's hours */}
      {hours && (
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-2 flex-wrap">
          {place.regular_opening_hours?.openNow != null && (
            <span className={`flex items-center gap-1 text-xs font-medium ${
              place.regular_opening_hours.openNow ? 'text-green-600' : 'text-red-500'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${
                place.regular_opening_hours.openNow ? 'bg-green-500' : 'bg-red-400'
              }`} />
              {place.regular_opening_hours.openNow ? 'Open' : 'Closed'}
            </span>
          )}
          <p className="text-xs text-gray-600">{hours}</p>
        </div>
      )}

      {/* Stats */}
      <div className="flex gap-4 px-4 py-3 text-xs text-gray-500 border-b border-gray-100">
        <span>{place.mention_count} mention{place.mention_count !== 1 ? 's' : ''}</span>
        <span>{place.source_count} source{place.source_count !== 1 ? 's' : ''}</span>
      </div>

      {/* Mentions */}
      <div className="px-4 py-3">
        {isLoading ? (
          <p className="text-sm text-gray-400 animate-pulse">Loading sources&hellip;</p>
        ) : mentions.length === 0 ? (
          <p className="text-sm text-gray-400">No sources found.</p>
        ) : (
          <div>
            {mentions.map((m) => (
              <MentionCard key={m.id} mention={m} placeName={place.name} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
