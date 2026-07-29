// Surface the server's reason (FastAPI's `detail`) so a permanent failure — "already has a quote",
// "that PDF has no selectable text" — reads as an instruction rather than a generic retry prompt.
export function apiError(error: unknown): Error {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  return new Error(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.')
}
