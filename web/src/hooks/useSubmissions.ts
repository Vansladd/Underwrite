import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/schema'

export type Submission = components['schemas']['SubmissionListItem']
export type SubmissionStatus = NonNullable<Submission['status']>
export type SubmissionDetail = components['schemas']['SubmissionDetail']

// Approve/decline change the row's status and premium, so the queue, tabs, and this submission
// all go stale — invalidate the three query families the drawer and queue read from.
function invalidateSubmission(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  queryClient.invalidateQueries({ queryKey: ['submission', id] })
  queryClient.invalidateQueries({ queryKey: ['submissions'] })
  queryClient.invalidateQueries({ queryKey: ['submission-stats'] })
}

// Surface the server's reason (FastAPI 409/422 detail) so the operator sees "already has a quote"
// or "no bound premium to quote" instead of a generic retry prompt on a permanent failure.
function actionError(error: unknown): Error {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  return new Error(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.')
}

export function useApproveSubmission(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/submissions/{submission_id}/approve', {
        params: { path: { submission_id: id } },
      })
      if (error) throw actionError(error)
      return data
    },
    onSuccess: () => invalidateSubmission(queryClient, id),
  })
}

export function useDeclineSubmission(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (reason: string) => {
      const { data, error } = await api.POST('/api/submissions/{submission_id}/decline', {
        params: { path: { submission_id: id } },
        body: { reason },
      })
      if (error) throw actionError(error)
      return data
    },
    onSuccess: () => invalidateSubmission(queryClient, id),
  })
}

export function useSubmissions(status?: SubmissionStatus) {
  return useQuery({
    queryKey: ['submissions', status ?? 'all'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/submissions', {
        params: { query: status ? { status } : {} },
      })
      if (error) throw new Error('could not load submissions')
      return data
    },
  })
}

export function useSubmission(id: string | null) {
  return useQuery({
    queryKey: ['submission', id],
    enabled: id != null,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/submissions/{submission_id}', {
        params: { path: { submission_id: id! } },
      })
      if (error) throw new Error('could not load submission')
      return data
    },
  })
}

export function useSubmissionStats() {
  return useQuery({
    queryKey: ['submission-stats'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/submissions/stats')
      if (error) throw new Error('could not load stats')
      return data
    },
  })
}
