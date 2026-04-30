export type CalendarStatusPayload = {
  configured: boolean
}

export type CalendarEventCreatedPayload = {
  id: string
  htmlLink: string
  summary: string
  start: string
  end: string
}

export async function fetchCalendarStatus(): Promise<CalendarStatusPayload> {
  const res = await fetch('/api/calendar/status')
  if (!res.ok) throw new Error('無法取得行事曆連線狀態')
  return res.json() as Promise<CalendarStatusPayload>
}

function detailMessage(data: unknown): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d))
      return d.map((x) => (typeof x === 'object' && x && 'msg' in x ? String((x as { msg: unknown }).msg) : String(x))).join('; ')
  }
  return '建立失敗'
}

export async function createCalendarEventFromText(
  text: string,
): Promise<CalendarEventCreatedPayload> {
  const res = await fetch('/api/calendar/events/from-text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  const data: unknown = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(detailMessage(data))
  return data as CalendarEventCreatedPayload
}
