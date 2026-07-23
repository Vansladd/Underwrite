import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/schema'

export type Operator = components['schemas']['UserRead']

// Distinguishes "not logged in" (401) from a transport failure — App renders the login on null.
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    retry: false,
    queryFn: async (): Promise<Operator | null> => {
      const { data, response } = await api.GET('/api/auth/me')
      if (response.status === 401) return null
      if (!data) throw new Error('could not load the current operator')
      return data
    },
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['LoginRequest']) => {
      const { data, error } = await api.POST('/api/auth/login', { body })
      if (error || !data) throw new Error('invalid username or password')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries(),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.POST('/api/auth/logout')
    },
    onSuccess: () => queryClient.invalidateQueries(),
  })
}
