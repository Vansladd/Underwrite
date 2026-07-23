import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/schema'

export type Submission = components['schemas']['SubmissionListItem']

export function useSubmissions() {
  return useQuery({
    queryKey: ['submissions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/submissions')
      if (error) throw new Error('could not load submissions')
      return data
    },
  })
}
