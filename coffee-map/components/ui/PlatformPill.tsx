import type { Platform } from '@/types'

const PLATFORM_COLORS: Record<Platform, string> = {
  reddit: 'bg-orange-500 text-white',
  instagram: 'bg-pink-500 text-white',
  blog: 'bg-blue-500 text-white',
  tiktok: 'bg-black text-white',
  google_review: 'bg-green-500 text-white',
}

interface PlatformPillProps {
  platform: Platform
}

export function PlatformPill({ platform }: PlatformPillProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${PLATFORM_COLORS[platform]}`}
    >
      {platform.replace('_', ' ')}
    </span>
  )
}
