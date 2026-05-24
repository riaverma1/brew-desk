import type { PlacePin } from '@/types'

interface AttributePillsProps {
  place: PlacePin
}

export function AttributePills({ place }: AttributePillsProps) {
  const pills: { label: string; color: string }[] = []

  // Render null for unknown attrs — do NOT show "unknown" pills
  if (place.has_wifi === true) pills.push({ label: 'WiFi', color: 'bg-blue-100 text-blue-800' })
  if (place.has_outlets === true) pills.push({ label: 'Outlets', color: 'bg-purple-100 text-purple-800' })
  if (place.is_laptop_friendly === true) pills.push({ label: 'Laptop friendly', color: 'bg-teal-100 text-teal-800' })

  if (pills.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {pills.map((pill) => (
        <span
          key={pill.label}
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${pill.color}`}
        >
          {pill.label}
        </span>
      ))}
    </div>
  )
}
