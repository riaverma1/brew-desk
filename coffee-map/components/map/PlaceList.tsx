'use client'

import type { PlacePin } from '@/types'
import { isOpenNow } from '@/lib/map-utils'
import { AttributePills } from './AttributePills'

interface PlaceListProps {
  places: PlacePin[]
  selectedId: string | null
  onSelect: (placeId: string) => void
}

function todaysHoursShort(place: PlacePin): string | null {
  const descriptions = place.regular_opening_hours?.weekdayDescriptions
  if (!descriptions?.length) return null
  const todayIndex = (new Date().getDay() + 6) % 7
  const entry = descriptions[todayIndex] ?? null
  if (!entry) return null
  return entry.replace(/^[^:]+:\s*/, '')
}

export function PlaceList({ places, selectedId, onSelect }: PlaceListProps) {
  const sorted = [...places].sort((a, b) => b.mention_count - a.mention_count)

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-gray-100 shrink-0 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">
          {places.length} spot{places.length !== 1 ? 's' : ''} in view
        </span>
        <span className="text-xs text-gray-400">by mentions ↓</span>
      </div>

      <div className="overflow-y-auto flex-1" style={{ scrollbarWidth: 'none' }}>
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-400 text-sm gap-1">
            <span>No spots found</span>
            <span className="text-xs">Try panning the map</span>
          </div>
        ) : (
          sorted.map((place) => (
            <PlaceCard
              key={place.place_id}
              place={place}
              selected={place.place_id === selectedId}
              onClick={() => onSelect(place.place_id)}
            />
          ))
        )}
      </div>
    </div>
  )
}

function PlaceCard({
  place,
  selected,
  onClick,
}: {
  place: PlacePin
  selected: boolean
  onClick: () => void
}) {
  const hours = todaysHoursShort(place)
  const isOpen = isOpenNow(place)
  const photo = place.photos[0] ?? null

  const badgeClass =
    place.mention_count >= 15
      ? 'text-amber-900 bg-amber-50 border-amber-300'
      : place.mention_count >= 8
      ? 'text-amber-800 bg-orange-50 border-orange-200'
      : 'text-gray-600 bg-gray-100 border-gray-200'

  return (
    <button
      onClick={onClick}
      className={[
        'w-full text-left px-4 py-3.5 border-b border-gray-100 transition-colors flex gap-3 items-start border-l-[3px]',
        selected ? 'bg-amber-50 border-l-amber-900' : 'border-l-transparent hover:bg-gray-50',
      ].join(' ')}
    >
      <div className="w-16 h-16 rounded-xl shrink-0 overflow-hidden bg-stone-100 flex items-center justify-center text-2xl">
        {photo ? (
          <img
            src={photo}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
            }}
          />
        ) : (
          '☕'
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-gray-900 text-sm leading-tight truncate">
            {place.name}
          </h3>
          <span className={`shrink-0 text-xs font-bold rounded-full px-2 py-0.5 border ${badgeClass}`}>
            {place.mention_count}
          </span>
        </div>

        {place.address && (
          <p className="text-xs text-gray-400 mt-0.5 truncate">{place.address}</p>
        )}

        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          {isOpen != null && (
            <span
              className={`text-xs font-medium flex items-center gap-1 ${
                isOpen ? 'text-green-600' : 'text-red-500'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isOpen ? 'bg-green-500' : 'bg-red-400'
                }`}
              />
              {isOpen ? 'Open' : 'Closed'}
            </span>
          )}
          {hours && isOpen != null && (
            <span className="text-gray-300 text-xs">·</span>
          )}
          {hours && (
            <span className="text-xs text-gray-400 truncate">{hours}</span>
          )}
        </div>

        {place.top_mention_snippet && (
          <p className="text-xs text-gray-500 mt-1 line-clamp-2 italic">
            &ldquo;{place.top_mention_snippet}&rdquo;
          </p>
        )}

        <AttributePills place={place} />
      </div>
    </button>
  )
}
