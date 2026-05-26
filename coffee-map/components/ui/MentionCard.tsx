import type { MentionCard as MentionCardType } from '@/types'
import { PlatformPill } from './PlatformPill'

interface MentionCardProps {
  mention: MentionCardType
  placeName?: string
}

const WFH_KEYWORDS = [
  // wifi / connectivity
  'wifi', 'wi-fi', 'internet', 'connection', 'signal', 'bandwidth', 'hotspot',
  // power
  'outlet', 'outlets', 'plug', 'plugs', 'power', 'powers', 'charging', 'charger',
  // noise
  'noise', 'noisy', 'noise level', 'quiet', 'loud', 'volume', 'background music', 'hustle', 'chill',
  // seating & comfort
  'seat', 'seats', 'seating', 'comfort', 'comfortable', 'cozy', 'cosy',
  'chairs', 'tables', 'couch', 'sofa', 'ergonomic',
  // space & crowd
  'space', 'spacious', 'crowded', 'crowd', 'busy', 'packed', 'empty', 'roomy',
  // hours
  'open late', 'late night', 'hours', 'closing time', 'all day',
  // work vibe
  'laptop', 'laptops', 'work', 'working', 'workspace', 'workspaces', 'workstation',
  'wfh', 'remote', 'remote work', 'remotely',
  'study', 'studying', 'focus', 'concentrate', 'productive', 'productivity',
  'freelance', 'coding',
  // environment
  'atmosphere', 'ambiance', 'vibe', 'ac', 'air conditioning', 'ventilation',
  // // drinks
  // 'coffee', 'drink',
]

function isUsefulSnippet(s: string | null | undefined, placeName?: string): boolean {
  if (!s || !s.trim()) return false
  const lower = s.toLowerCase().trim()
  if (lower === 'mentioned this place') return false
  if (placeName && lower === placeName.toLowerCase().trim()) return false
  if (lower.length < 15) return false
  if (!WFH_KEYWORDS.some(k => lower.includes(k))) return false
  return true
}

function truncate(s: string, max = 60): string {
  return s.length > max ? s.slice(0, max).trimEnd() + '…' : s
}

function parseUrlContext(url: string): string | null {
  try {
    const params = new URL(url).searchParams
    // Yelp search: find_desc + optional find_loc
    const desc = params.get('find_desc')
    if (desc) {
      const loc = params.get('find_loc')
      const neighborhood = loc ? loc.split(',')[0].trim() : null
      return neighborhood
        ? `search for "${desc}" in ${neighborhood}`
        : `search for "${desc}"`
    }
    // Generic search params
    const q = params.get('q') ?? params.get('query') ?? params.get('search')
    if (q) return `search for "${q}"`
    return null
  } catch {
    return null
  }
}

function buildFallback(mention: MentionCardType): string {
  const domain = mention.handle_or_domain
  const title = mention.source_title ? truncate(mention.source_title) : null
  switch (mention.platform) {
    case 'reddit':
      return title
        ? `Mentioned in a Reddit thread: "${title}"`
        : `Mentioned in a Reddit thread on r/${domain}`
    case 'instagram':
      return `Featured by @${domain} on Instagram`
    case 'blog': {
      if (title) return `Listed on ${domain} under "${title}"`
      const urlContext = parseUrlContext(mention.url)
      if (urlContext) return `Listed on ${domain} — ${urlContext}`
      return `Listed on ${domain}`
    }
    case 'tiktok':
      return title
        ? `Featured by @${domain} on TikTok: "${title}"`
        : `Featured by @${domain} on TikTok`
    default: {
      if (title) return `Mentioned on ${domain}: "${title}"`
      const urlContext = parseUrlContext(mention.url)
      if (urlContext) return `Mentioned on ${domain} — ${urlContext}`
      return `Mentioned on ${domain}`
    }
  }
}

export function MentionCard({ mention, placeName }: MentionCardProps) {
  const snippet = isUsefulSnippet(mention.evidence_snippet, placeName)
    ? mention.evidence_snippet!
    : null
  const fallback = buildFallback(mention)

  return (
    <div className="flex flex-col gap-1 py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2">
        <PlatformPill platform={mention.platform} />
        <span className="text-xs text-gray-500 truncate">{mention.handle_or_domain}</span>
        <a
          href={mention.url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-gray-400 hover:text-gray-700 text-xs"
          aria-label="Open source"
        >
          ↗
        </a>
      </div>
      {snippet ? (
        <p className="text-sm text-gray-700 italic line-clamp-3">&ldquo;{snippet}&rdquo;</p>
      ) : (
        <p className="text-sm text-gray-500">{fallback}</p>
      )}
    </div>
  )
}
