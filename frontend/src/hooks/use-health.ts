import { useQuery } from '@tanstack/react-query'

import { fetchHealth, type HealthPayload } from '@/lib/api/health'

const HEALTH_QUERY_KEY = ['health'] as const

export function useHealth() {
  return useQuery<HealthPayload>({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: fetchHealth,
    retry: false,
  })
}

export { HEALTH_QUERY_KEY }
