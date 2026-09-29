// Numbers, costs and times for humans in the GUI locale (English output matches the CLI, framework record.py `format_usd`).
import { locale, nf, t } from "./i18n";
import type { RunListItem, RunState } from "./types";

/** Exactly `digits` decimal places, no thousands grouping (`0.0812`, cs `0,0812`). */
const fixed = (n: number, digits: number) =>
  n.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false });

/** Run and step cost (fidelity §8): always four decimal places, `0.0000`, `0.0812`. */
export function formatCost(usd: number | null | undefined): string {
  if (usd == null) return "–";
  return fixed(usd, 4);
}

/** Daily spend (project card, sidebar, run panel): always two places (`0.00`, `1.20`); run and step costs have four. */
export const formatSpend = (usd: number) => fixed(usd, 2);

/** Limit or budget from the config (not a run cost): two to four decimal places. */
export const formatMoney = (usd: number) =>
  new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(usd);

/** `17.5 s`, `1 min 12 s`, `1 h 5 min`. */
export function formatDuration(s: number | null | undefined): string {
  if (s == null) return "–";
  if (s < 60) return `${fixed(s, 1)} s`;
  const total = Math.round(s);
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`;
  return `${Math.floor(total / 3600)} h ${Math.floor((total % 3600) / 60)} min`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Time since a running run started, `00:42`, `12:05` (fidelity §8, DURATION column). */
export function formatElapsed(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "–";
  const s = Math.max(0, Math.floor((now - Date.parse(iso)) / 1000));
  return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}
const clock = (d: Date) => d.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
const dayStart = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Local event time: `12 min ago`, `today 9:15 AM`, `yesterday 2:03 PM`, `9/25 2:03 PM` (cs `25. 9. 14:03`). */
export function formatWhen(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const mins = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (mins < 1 && mins > -1) return t("time.now");
  if (mins > 0 && mins < 60) return t("time.minutesAgo", { n: mins });
  const days = Math.round((dayStart(now) - dayStart(d)) / 86400000);
  if (days === 0) return t("time.today", { time: clock(d) });
  if (days === 1) return t("time.yesterday", { time: clock(d) });
  const year = d.getFullYear() === now.getFullYear() ? undefined : "numeric";
  return `${d.toLocaleDateString(locale, { day: "numeric", month: "numeric", year })} ${clock(d)}`;
}

/** UTC for the tooltip (§6: times are local, with UTC in the tooltip). */
export const utcTitle = (iso: string | null | undefined) => (iso ? `${iso.replace("T", " ").slice(0, 19)} UTC` : undefined);

/** `run_id` = `YYYYMMDD-HHMMSS-<scenario>-<4 hex>` (run-record.md) — for `last_run` (no `started_at`) and a folder without a record. */
export function runIdParts(runId: string): { scenario: string; startedAt: string } | null {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-(.+)-[0-9a-f]{4}$/.exec(runId);
  if (!m) return null;
  return { scenario: m[7], startedAt: `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` };
}

export const runScenario = (r: RunListItem) => r.scenario ?? runIdParts(r.run_id)?.scenario ?? "";
export const runStartedAt = (r: RunListItem) => r.started_at ?? runIdParts(r.run_id)?.startedAt ?? null;

export const isLive = (state: RunState) => state === "queued" || state === "running";

/** `failed (fail in stop)` → `fail in stop`. */
export const failReason = (status: string) => /^failed \((.*)\)$/.exec(status)?.[1] ?? "";

export { nf };
