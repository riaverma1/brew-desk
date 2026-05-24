// Single source of truth for all TypeScript interfaces used across the frontend.
// All boolean attrs on PlacePin are | null — newly crawled places may not have
// boolean attrs computed yet. UI must guard against null before rendering pills.

export type NoiseLevel = 'quiet' | 'moderate' | 'loud'
export type Platform = 'reddit' | 'instagram' | 'blog' | 'tiktok' | 'google_review'

export interface MapBounds {
  north: number
  south: number
  east: number
  west: number
}

export interface PlacePin {
  place_id: string
  name: string
  address: string | null
  lat: number
  lng: number
  wfh_score: number
  has_wifi: boolean | null
  has_outlets: boolean | null
  is_laptop_friendly: boolean | null
  noise_level: NoiseLevel | null
  seating_comfort: string | null
  mention_count: number
  source_count: number
  photos: string[]
  primary_type: string | null
  rating: number | null
  user_rating_count: number | null
  regular_opening_hours: { weekdayDescriptions?: string[]; openNow?: boolean } | null
}

export interface MentionCard {
  id: string
  url: string
  evidence_snippet: string | null
  platform: Platform
  handle_or_domain: string
  laptop_confidence: number
  mentioned_at: string | null
  source_title: string | null
}

export interface NearbySearchRequest {
  lat: number
  lng: number
  bounds: MapBounds
}

export interface NearbySearchResponse {
  places: PlacePin[]
  region_status: 'seeded' | 'crawling' | 'cold' | null
  region_id: string | null
}

export interface MentionsResponse {
  place_id: string
  mentions: MentionCard[]
}
