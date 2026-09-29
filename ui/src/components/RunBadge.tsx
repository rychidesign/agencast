import { formatWhen, runIdParts, utcTitle } from "../format";
import { t } from "../i18n";
import type { LastRunRef, RunState } from "../types";
import { StatusChip, type Status } from "./ui";

export const RUN_STATUS: Record<RunState, Status> = {
  queued: "queued", running: "running", interrupted: "interrupted", succeeded: "succeeded", failed: "failed",
  cancelled: "cancelled", dry_run: "dry-run",
};

/** Status chip of the last run from `last_run`: "✓ 12 min ago", "✗ error", "◌ running", "no runs" (§2.2). */
export function LastRun({ run }: { run: LastRunRef | null | undefined }) {
  if (!run) return <StatusChip status="none">{t("runs.none")}</StatusChip>;
  const { state } = run;
  const when = run.finished_at ?? run.started_at ?? runIdParts(run.run_id)?.startedAt;
  const text = state === "running" || state === "queued" ? t(`run.state.${state}`) : formatWhen(when);
  return (
    <span title={utcTitle(when)}>
      <StatusChip status={RUN_STATUS[state]}>
        <span className="sr-only">{t(`run.state.${state}`)} · </span>{text}
      </StatusChip>
    </span>
  );
}
