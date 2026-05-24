interface HeaderProps {
  openNowOnly: boolean
  onToggleOpenNow: () => void
}

export function Header({ openNowOnly, onToggleOpenNow }: HeaderProps) {
  return (
    <header className="h-12 flex items-center px-4 bg-white/80 backdrop-blur-sm border-b border-gray-100 z-40 relative">
      <span className="font-semibold text-gray-900 text-base tracking-tight">BrewDesk</span>
      <span className="hidden sm:block ml-3 text-sm text-gray-400">
        Find your next workspace between meetings
      </span>
      <div className="ml-auto">
        <button
          onClick={onToggleOpenNow}
          className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
            openNowOnly
              ? 'bg-green-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          Open Now
        </button>
      </div>
    </header>
  )
}
