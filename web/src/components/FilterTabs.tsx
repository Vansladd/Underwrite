export type Tab = { key: string; label: string; count: number }

export function FilterTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Tab[]
  active: string
  onChange: (key: string) => void
}) {
  return (
    <div role="tablist" aria-label="Filter submissions by status" className="mt-6 flex gap-6 border-b border-border">
      {tabs.map((tab) => {
        const isActive = tab.key === active
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={`relative flex items-center gap-1.5 pb-3 text-[13px] font-medium transition-colors ${
              isActive ? 'text-ink' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {tab.label}
            <span
              className={`tnum rounded-full border px-1.5 py-px text-[11px] ${
                isActive
                  ? 'border-accent-text text-accent-text'
                  : 'border-border bg-surface-2 text-ink-subtle'
              }`}
            >
              {tab.count}
            </span>
            {isActive && (
              <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent" />
            )}
          </button>
        )
      })}
    </div>
  )
}
