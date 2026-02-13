const UNITS: [number, string, string][] = [
  [60, "second", "seconds"],
  [60, "minute", "minutes"],
  [24, "hour", "hours"],
  [30, "day", "days"],
  [12, "month", "months"],
  [Infinity, "year", "years"],
];

export function formatRelativeTime(iso: string): string {
  const now = Date.now();
  const target = new Date(iso).getTime();
  let diff = Math.round((target - now) / 1000);
  const isFuture = diff > 0;
  diff = Math.abs(diff);

  if (diff < 10) return "just now";

  for (const [threshold, singular, plural] of UNITS) {
    if (diff < threshold) {
      const label = diff === 1 ? singular : plural;
      return isFuture ? `in ${diff} ${label}` : `${diff} ${label} ago`;
    }
    diff = Math.floor(diff / threshold);
  }

  return iso;
}
