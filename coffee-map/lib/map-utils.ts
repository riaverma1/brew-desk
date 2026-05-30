import type { MapBounds, PlacePin } from '@/types'

// Parse "7:00 AM" / "12:00 AM" into minutes-since-midnight.
function parseTime(s: string): number {
  const m = s.match(/(\d+):(\d+)\s*(AM|PM)/i)
  if (!m) return -1
  let h = parseInt(m[1], 10)
  const min = parseInt(m[2], 10)
  const period = m[3].toUpperCase()
  if (period === 'AM' && h === 12) h = 0
  if (period === 'PM' && h !== 12) h += 12
  return h * 60 + min
}

/**
 * Computes whether a place is open right now from its stored weekdayDescriptions.
 * Returns null when hours data is unavailable.
 * Google's index: 0=Monday … 6=Sunday; JS getDay(): 0=Sunday … 6=Saturday.
 */
export function isOpenNow(place: PlacePin): boolean | null {
  const descriptions = place.regular_opening_hours?.weekdayDescriptions
  if (!descriptions?.length) return null

  const jsDay = new Date().getDay() // 0=Sun
  const googleIndex = (jsDay + 6) % 7  // 0=Mon
  const entry = descriptions[googleIndex]
  if (!entry) return null

  const hoursStr = entry.replace(/^[^:]+:\s*/, '')
  if (hoursStr === 'Closed') return false
  if (hoursStr === 'Open 24 hours') return true

  // "7:00 AM – 9:00 PM" — en-dash separator
  const parts = hoursStr.split('–')
  if (parts.length !== 2) return null

  const open = parseTime(parts[0].trim())
  const close = parseTime(parts[1].trim())
  if (open < 0 || close < 0) return null

  const now = new Date()
  const nowMin = now.getHours() * 60 + now.getMinutes()

  // close <= open means the range spans midnight (e.g. 8:00 AM – 12:00 AM)
  if (close <= open) return nowMin >= open || nowMin < close
  return nowMin >= open && nowMin < close
}

export function boundsToCenter(bounds: MapBounds): { lat: number; lng: number } {
  return {
    lat: (bounds.north + bounds.south) / 2,
    lng: (bounds.east + bounds.west) / 2,
  }
}

export function haversineDistanceMeters(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6_371_000
  const phi1 = (lat1 * Math.PI) / 180
  const phi2 = (lat2 * Math.PI) / 180
  const dphi = ((lat2 - lat1) * Math.PI) / 180
  const dlng = ((lng2 - lng1) * Math.PI) / 180
  const a =
    Math.sin(dphi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export function boundsOverlap(a: MapBounds, b: MapBounds): boolean {
  return a.south < b.north && a.north > b.south && a.west < b.east && a.east > b.west
}
