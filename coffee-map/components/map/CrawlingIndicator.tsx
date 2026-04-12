'use client'

interface CrawlingIndicatorProps {
  visible: boolean
}

/**
 * Persistent pill shown while the backend is crawling a region (status = 'crawling').
 * Unlike ColdRegionBanner, this does NOT auto-dismiss — it stays until regionStatus
 * changes to 'seeded'. No close button either; the user can't stop a crawl.
 */
export function CrawlingIndicator({ visible }: CrawlingIndicatorProps) {
  if (!visible) return null

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-white border border-gray-200 shadow-md rounded-full px-4 py-2 text-sm text-gray-700 flex items-center gap-2 pointer-events-none select-none">
      <svg
        className="w-3.5 h-3.5 text-blue-500 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle
          className="opacity-25"
          cx="12" cy="12" r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
        />
      </svg>
      <span>Finding spots in this area&hellip;</span>
    </div>
  )
}
