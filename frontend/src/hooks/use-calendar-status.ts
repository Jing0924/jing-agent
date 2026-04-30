import { useQuery } from '@tanstack/react-query'

import {
  fetchCalendarStatus,
  type CalendarStatusPayload,
} from '@/lib/api/calendar'

const CALENDAR_STATUS_QUERY_KEY = ['calendar-status'] as const

export function useCalendarStatus() {
  return useQuery<CalendarStatusPayload>({
    queryKey: CALENDAR_STATUS_QUERY_KEY,
    queryFn: fetchCalendarStatus,
    retry: false,
  })
}

export { CALENDAR_STATUS_QUERY_KEY }
