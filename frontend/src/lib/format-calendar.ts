const CAL_FALLBACK_LOCALES = ['zh-TW', 'en-US'] as const

function calendarLocales(): string[] {
  if (typeof navigator === 'undefined' || !navigator.language) {
    return [...CAL_FALLBACK_LOCALES]
  }
  const primary = navigator.language
  const out: string[] = []
  const seen = new Set<string>()
  const add = (l: string) => {
    if (l && !seen.has(l)) {
      seen.add(l)
      out.push(l)
    }
  }
  add(primary)
  for (const l of CAL_FALLBACK_LOCALES) add(l)
  return out
}

/** Formats an ISO instant in the given IANA zone (matches backend NLP / list API). */
export function formatCalendarInstant(iso: string, timeZone: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const locales = calendarLocales()
  const options: Intl.DateTimeFormatOptions = {
    timeZone,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }
  try {
    return new Intl.DateTimeFormat(locales, options).format(d)
  } catch {
    try {
      return new Intl.DateTimeFormat(locales, {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }).format(d)
    } catch {
      return iso
    }
  }
}
