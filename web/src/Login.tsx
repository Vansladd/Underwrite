import { type FormEvent, useState } from 'react'

import { BrandMark } from './components/BrandMark'
import { ThemeToggle } from './components/ThemeToggle'
import { useLogin } from './hooks/useAuth'

export function Login() {
  const login = useLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    login.mutate({ username, password })
  }

  return (
    <div className="grid min-h-screen place-items-center bg-bg px-6">
      <div className="fixed right-5 top-5">
        <ThemeToggle />
      </div>

      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg border border-border bg-surface p-8"
      >
        <div className="flex items-center gap-2.5">
          <BrandMark size={24} />
          <span className="text-base font-semibold tracking-tight">Underwrite</span>
        </div>
        <p className="mt-1.5 text-[13px] text-ink-muted">Sign in to the operator console.</p>

        <label className="mt-6 block text-[13px] font-medium text-ink">
          Username
          <input
            type="text"
            autoComplete="username"
            placeholder="you@insurer"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1.5 h-9 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
          />
        </label>

        <label className="mt-4 block text-[13px] font-medium text-ink">
          Password
          <input
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1.5 h-9 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
          />
        </label>

        {login.isError && (
          <p className="mt-4 text-[13px] text-[color:var(--dc-fg)]">Invalid username or password.</p>
        )}

        <button
          type="submit"
          disabled={login.isPending || !username || !password}
          className="mt-6 h-10 w-full rounded-md bg-accent text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
