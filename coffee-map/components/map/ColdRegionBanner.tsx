'use client'

import { useEffect, useState } from 'react'

interface ColdRegionBannerProps {
  visible: boolean
}

/**
 * Non-blocking banner shown when a cold region is detected.
 * Auto-dismisses after 8 seconds.
 * Does NOT imply the user should wait — it's a background process.
 */
export function ColdRegionBanner({ visible }: ColdRegionBannerProps) {
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!visible) {
      setDismissed(false)
    }
  }, [visible])

  if (!visible || dismissed) return null

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 bg-white border border-amber-200 shadow-lg rounded-lg px-4 py-3 max-w-sm text-sm text-gray-700 flex items-center gap-3">
      <span className="text-lg">🎉</span>
      <span>This is a new region! Thank you for joining the expansion! Please wait 3&ndash;5 minutes for pins to appear.</span>
      <button
        onClick={() => setDismissed(true)}
        className="ml-auto text-gray-400 hover:text-gray-600 shrink-0"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}
