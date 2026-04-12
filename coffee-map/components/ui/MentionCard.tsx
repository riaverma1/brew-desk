import type { MentionCard as MentionCardType } from '@/types'
import { PlatformPill } from './PlatformPill'

interface MentionCardProps {
  mention: MentionCardType
}

export function MentionCard({ mention }: MentionCardProps) {
  // evidence_snippet can be null — show fallback, not an empty element
  const snippet = mention.evidence_snippet || 'Mentioned this place'

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
      <p className="text-sm text-gray-700 italic line-clamp-3">&ldquo;{snippet}&rdquo;</p>
    </div>
  )
}
