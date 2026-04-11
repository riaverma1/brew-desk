interface ScoreBadgeProps {
  score: number
}

export function ScoreBadge({ score }: ScoreBadgeProps) {
  const color =
    score >= 8.0
      ? 'bg-green-500 text-white'
      : score >= 6.0
        ? 'bg-amber-500 text-white'
        : 'bg-gray-400 text-white'

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-sm font-semibold ${color}`}>
      {score.toFixed(1)}
    </span>
  )
}
