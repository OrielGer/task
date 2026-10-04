// Small presentation helpers (no dependencies).

/** Format a duration in seconds as "Xh Ym" (e.g. 3725 -> "1h 2m").
 * Sub-minute durations show seconds so short timeline rows are not all "0m". */
export function formatDuration(totalSeconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Local clock time, e.g. "09:42". */
export function formatTime(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "—";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** Local date + time, e.g. "Oct 4, 09:42". */
export function formatDateTime(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A time range "09:42 – 10:15". */
export function formatTimeRange(
  start: string | null | undefined,
  end: string | null | undefined
): string {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

/** "time ago" style relative label for last-seen timestamps. */
export function formatRelative(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "never";
  const diffMs = Date.now() - d.getTime();
  const sec = Math.round(diffMs / 1000);
  if (sec < 0) return formatDateTime(value);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.round(hr / 24);
  if (days < 30) return `${days}d ago`;
  return formatDateTime(value);
}

/** Today's date as YYYY-MM-DD in local time. */
export function todayISODate(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** The day after a YYYY-MM-DD date, as YYYY-MM-DD (exclusive range end). */
export function nextISODate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map((n) => parseInt(n, 10));
  if (!y || !m || !d) return isoDate;
  const date = new Date(Date.UTC(y, m - 1, d));
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

/** Render an automation score (0..1) as a whole-number percentage. */
export function formatPercent(score: number | null | undefined): string {
  const v = Math.max(0, Math.min(1, Number(score) || 0));
  return `${Math.round(v * 100)}%`;
}

/** Split a comma-separated string (apps/domains) into trimmed, non-empty parts. */
export function splitCsv(value: string | null | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}
