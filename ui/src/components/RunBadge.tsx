import { formatWhen, runStartedAt, runState, utcTitle, type RunState } from "../format";
import { t } from "../i18n";
import type { RunListItem } from "../types";
import { StatusChip, type Status } from "./ui";

export const RUN_STATUS: Record<RunState, Status> = {
  queued: "queued", running: "running", succeeded: "succeeded", failed: "failed", "dry-run": "dry-run", unknown: "none",
};

/** Stavový čip posledního běhu: „✓ před 12 min“, „✗ chyba“, „◌ běží“, „bez běhů“ (§2.2). */
export function LastRun({ run }: { run: RunListItem | undefined }) {
  if (!run) return <StatusChip status="none">{t("runs.none")}</StatusChip>;
  const state = runState(run.status);
  const when = runStartedAt(run);
  const text = state === "running" || state === "queued" ? t(`run.state.${state}`) : formatWhen(run.finished_at ?? when);
  return (
    <span title={utcTitle(run.finished_at ?? when)}>
      <StatusChip status={RUN_STATUS[state]}>
        <span className="sr-only">{t(`run.state.${state}`)} · </span>{text}
      </StatusChip>
    </span>
  );
}
