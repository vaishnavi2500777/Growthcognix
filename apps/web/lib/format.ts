export function when(iso: string, tz = "Asia/Kolkata") {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: tz,
  }).format(new Date(iso));
}

export function took(start: string | null, end: string | null) {
  if (!start || !end) return null;
  const s = Math.max(0, (new Date(end).getTime() - new Date(start).getTime()) / 1000);
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export const RUN_LABEL = {
  queued: "Queued", running: "Working", succeeded: "Finished", failed: "Failed", cancelled: "Cancelled",
} as const;
export const RUN_TONE = {
  queued: "wait", running: "wait", succeeded: "done", failed: "fail", cancelled: "todo",
} as const;
