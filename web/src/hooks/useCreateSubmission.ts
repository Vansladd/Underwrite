import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/schema'
import { apiError } from '../lib/apiError'

export type FormApplication = components['schemas']['FormApplication']
export type SubmissionDetail = components['schemas']['SubmissionDetail']

export type NewSubmission =
  | { mode: 'form'; application: FormApplication }
  | { mode: 'paste'; text: string }
  | { mode: 'pdf'; file: File }

async function uploadPdf(file: File): Promise<SubmissionDetail> {
  // Plain fetch: openapi-fetch types the binary field as a string, so the typed client would
  // need a cast to send a File. Same-origin, so the session cookie rides along either way.
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/submissions/pdf', { method: 'POST', body })
  const payload = await response.json().catch(() => null)
  // A 2xx that did not parse is a failure too — returning null here would throw past the
  // mutation's error handling and leave the button stuck on "Submitting…".
  if (!response.ok || payload === null) throw apiError(payload)
  return payload as SubmissionDetail
}

async function create(submission: NewSubmission): Promise<SubmissionDetail> {
  if (submission.mode === 'pdf') return uploadPdf(submission.file)

  const body =
    submission.mode === 'form'
      ? { input_mode: 'form' as const, application: submission.application }
      : { input_mode: 'paste' as const, raw_input: submission.text }
  const { data, error } = await api.POST('/api/submissions', { body })
  if (error) throw apiError(error)
  return data
}

export function useCreateSubmission() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submissions'] })
      queryClient.invalidateQueries({ queryKey: ['submission-stats'] })
    },
  })
}
