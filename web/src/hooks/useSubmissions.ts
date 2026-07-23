import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/schema'

export type Submission = components['schemas']['SubmissionListItem']
export type SubmissionStatus = NonNullable<Submission['status']>
export type SubmissionDetail = components['schemas']['SubmissionDetail']

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
