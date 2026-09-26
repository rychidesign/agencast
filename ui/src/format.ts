// Čísla, ceny a časy pro člověka — stejně jako CLI (framework record.py `cz_usd`).
import { nf, t } from "./i18n";
import type { RunListItem, RunState } from "./types";

/** Cena: desetinná čárka, aspoň 4 místa, víc jen kvůli uloženým číslicím (max 10), nula = `0`. */
export function formatCost(usd: number | null | undefined): string {
  if (usd == null) return "–";
  if (!usd) return "0";
  const [whole, frac] = usd.toFixed(10).split(".");
  return `${whole},${frac.replace(/0+$/, "").padEnd(4, "0")}`;
}

/** Limit nebo rozpočet z configu (ne cena běhu): dvě desetinná místa. */
export const formatMoney = (usd: number) =>
  new Intl.NumberFormat("cs", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(usd);

/** `17,5 s`, `1 min 12 s`, `1 h 5 min`. */
export function formatDuration(s: number | null | undefined): string {
  if (s == null) return "–";
  if (s < 60) return `${s.toFixed(1).replace(".", ",")} s`;
  const total = Math.round(s);
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`;
  return `${Math.floor(total / 3600)} h ${Math.floor((total % 3600) / 60)} min`;
}

const pad = (n: number) => String(n).padStart(2, "0");
const clock = (d: Date) => `${d.getHours()}:${pad(d.getMinutes())}`;
const dayStart = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Čas události lokálně: `před 12 min`, `dnes 9:15`, `včera 14:03`, `25. 9. 14:03`. */
export function formatWhen(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const mins = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (mins < 1 && mins > -1) return t("time.now");
  if (mins > 0 && mins < 60) return t("time.minutesAgo", { n: mins });
  const days = Math.round((dayStart(now) - dayStart(d)) / 86400000);
  if (days === 0) return t("time.today", { time: clock(d) });
  if (days === 1) return t("time.yesterday", { time: clock(d) });
  const year = d.getFullYear() === now.getFullYear() ? "" : ` ${d.getFullYear()}`;
  return `${d.getDate()}. ${d.getMonth() + 1}.${year} ${clock(d)}`;
}

/** UTC do tooltipu (§6: časy lokálně s UTC v tooltipu). */
export const utcTitle = (iso: string | null | undefined) => (iso ? `${iso.replace("T", " ").slice(0, 19)} UTC` : undefined);

/** `run_id` = `RRRRMMDD-HHMMSS-<scénář>-<4 hex>` (run-record.md) — pro `last_run` (nemá `started_at`) a složku bez záznamu. */
export function runIdParts(runId: string): { scenario: string; startedAt: string } | null {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-(.+)-[0-9a-f]{4}$/.exec(runId);
  if (!m) return null;
  return { scenario: m[7], startedAt: `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` };
}

export const runScenario = (r: RunListItem) => r.scenario ?? runIdParts(r.run_id)?.scenario ?? "";
export const runStartedAt = (r: RunListItem) => r.started_at ?? runIdParts(r.run_id)?.startedAt ?? null;

export const isLive = (state: RunState) => state === "queued" || state === "running";

/** `failed (fail v stop)` → `fail v stop`. */
export const failReason = (status: string) => /^failed \((.*)\)$/.exec(status)?.[1] ?? "";

export { nf };
