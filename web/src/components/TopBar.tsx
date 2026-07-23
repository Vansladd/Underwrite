import { type Operator, useLogout } from '../hooks/useAuth'
import { BrandMark } from './BrandMark'
import { ThemeToggle } from './ThemeToggle'

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function TopBar({ operator }: { operator: Operator }) {
  const logout = useLogout()
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-surface-2 px-6">
      <div className="flex items-center gap-2.5 font-semibold tracking-tight">
        <BrandMark />
        Underwrite
      </div>
      <div className="flex items-center gap-4 text-[13px]">
        <ThemeToggle />
        <div className="flex items-center gap-2">
          <span className="grid h-[26px] w-[26px] place-items-center rounded-full border border-border-strong bg-surface text-[11px] font-medium text-ink-muted">
            {initials(operator.display_name)}
          </span>
          <span className="text-ink-muted">{operator.display_name}</span>
        </div>
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="text-ink-subtle transition-colors hover:text-ink"
        >
          Sign out
        </button>
      </div>
    </header>
  )
}
