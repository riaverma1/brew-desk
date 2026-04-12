import type { MapBounds } from '@/types'

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
