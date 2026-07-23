import { type FormEvent, useState } from 'react'

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
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg bg-white p-8 ring-1 ring-slate-200"
      >
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Underwrite</h1>
        <p className="mt-1 text-sm text-slate-500">Sign in to the operator console.</p>

        <label className="mt-6 block text-sm font-medium text-slate-700">
          Username
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
          />
        </label>

        <label className="mt-4 block text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
          />
        </label>

        {login.isError && (
          <p className="mt-4 text-sm text-rose-600">Invalid username or password.</p>
        )}

        <button
          type="submit"
          disabled={login.isPending || !username || !password}
          className="mt-6 w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
