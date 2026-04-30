import { useQuery } from '@tanstack/react-query'

import {
  CALENDAR_EVENTS_QUERY_KEY,
  fetchCalendarEvents,
  type CalendarEventsPayload,
} from '@/lib/api/calendar'

export function useCalendarEvents(enabled: boolean) {
  return useQuery<CalendarEventsPayload>({
    queryKey: CALENDAR_EVENTS_QUERY_KEY,
    queryFn: () => fetchCalendarEvents(),
    enabled,
    retry: false,
  })
}
