interface HeaderProps {
  openNowOnly: boolean
  onToggleOpenNow: () => void
}

export function Header({ openNowOnly, onToggleOpenNow }: HeaderProps) {
  return (
    <header className="h-16 flex items-center px-5 gap-3 bg-white border-b border-gray-100 z-40 relative shrink-0">
      <div className="flex items-center gap-2.5 shrink-0">
        <div className="w-10 h-10 rounded-xl bg-amber-900 flex items-center justify-center">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="white" aria-hidden="true">
            <path d="M20 3H4v10c0 2.21 1.79 4 4 4h6c2.21 0 4-1.79 4-4v-3h2c1.11 0 2-.89 2-2V5c0-1.11-.89-2-2-2zm0 5h-2V5h2v3zM4 19h16v2H4z" />
          </svg>
        </div>
        <span className="font-bold text-gray-900 text-xl tracking-tight">BrewDesk</span>
      </div>

      <span className="hidden sm:block text-sm text-gray-400">
        Find your next workspace between meetings
      </span>

      <div className="ml-auto">
        <button
          onClick={onToggleOpenNow}
          className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 ${
            openNowOnly
              ? 'bg-amber-900 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {openNowOnly && (
            <span className="h-1.5 w-1.5 rounded-full bg-amber-300 animate-pulse" />
          )}
          Open Now
        </button>
      </div>
    </header>
  )
}
