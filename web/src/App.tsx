import { Login } from './Login'
import { type Operator, useLogout, useMe } from './hooks/useAuth'
import { type Submission, useSubmissions } from './hooks/useSubmissions'

const STATUS_STYLES: Record<string, string> = {
  received: 'bg-slate-100 text-slate-700 ring-slate-200',
  auto_approved: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  referred: 'bg-amber-50 text-amber-700 ring-amber-200',
  declined: 'bg-rose-50 text-rose-700 ring-rose-200',
  quoted: 'bg-sky-50 text-sky-700 ring-sky-200',
  failed: 'bg-rose-50 text-rose-700 ring-rose-200',
}

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.received
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset ${style}`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function summarise(submission: Submission): string {
  if (submission.raw_input) return submission.raw_input.replace(/\s+/g, ' ').trim().slice(0, 80)
  return `${submission.input_mode} submission`
}

function Queue({ operator }: { operator: Operator }) {
  const { data, isPending, isError } = useSubmissions()
  const logout = useLogout()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-5xl px-6 py-10">
        <header className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Submissions</h1>
            <p className="mt-1 text-sm text-slate-500">
              Tech E&amp;O / Cyber intake — {data?.length ?? 0} in the queue
            </p>
          </div>
          <div className="text-right text-sm">
            <div className="text-slate-700">{operator.display_name}</div>
            <button
              type="button"
              onClick={() => logout.mutate()}
              className="mt-0.5 text-slate-400 hover:text-slate-700"
            >
              Sign out
            </button>
          </div>
        </header>

        {isPending && <p className="text-sm text-slate-500">Loading…</p>}
        {isError && (
          <p className="rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-200">
            Could not reach the API. Is it running behind <code>/api</code>?
          </p>
        )}

        {data && data.length === 0 && (
          <p className="rounded-md bg-white px-4 py-8 text-center text-sm text-slate-500 ring-1 ring-slate-200">
            No submissions yet. Run <code>make seed</code> to load the samples.
          </p>
        )}

        {data && data.length > 0 && (
          <div className="overflow-hidden rounded-lg bg-white ring-1 ring-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Submission</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Received</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((submission) => (
                  <tr key={submission.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <div className="truncate text-slate-800">{summarise(submission)}</div>
                      <div className="mt-0.5 font-mono text-xs text-slate-400">
                        {submission.id.slice(0, 8)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={submission.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {new Date(submission.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export function App() {
  const { data: operator, isPending } = useMe()

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        Loading…
      </div>
    )
  }
  if (!operator) return <Login />
  return <Queue operator={operator} />
}
