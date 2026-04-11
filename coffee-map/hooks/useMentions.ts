'use client'

import { useEffect, useRef, useState } from 'react'
import { fetchMentions } from '@/lib/api-client'
import type { MentionCard } from '@/types'

/**
 * Fetches MentionCard[] for a place_id when a pin is clicked.
 * Resets on placeId change. No-ops when placeId is null.
 */
export function useMentions(placeId: string | null): {
  mentions: MentionCard[]
  isLoading: boolean
} {
  const [mentions, setMentions] = useState<MentionCard[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!placeId) {
      setMentions([])
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setIsLoading(true)

    fetchMentions(placeId, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setMentions(data.mentions)
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
  }, [placeId])

  return { mentions, isLoading }
}
