// §2.2 Project: section header (Scenarios · Agents · Runs · Skills · Config); project navigation is in the sidebar (Shell).
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { enc, useApi } from "../api";
import { PageHeader } from "../components/PageHeader";
import { btn, ErrorList, ErrorText, Loading, Skeleton, StatusChip, usePopoverPosition, type MenuItem } from "../components/ui";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { ErrorItem, Project } from "../types";
import { AgentsTab, SkillsTab } from "./Agents";
import { ConfigTab } from "./Config";
import { RunsTab } from "./Runs";
import { ScenariosTab } from "./Scenarios";

/** All project validation errors (project + files). */
export const allErrors = (p: Project): ErrorItem[] => {
  // a file error also arrives in `p.errors` (invalid agent) → take each one once
  const all = [...p.errors, ...[...p.scenarios, ...p.agents, ...p.skills].flatMap((x) => x.errors)];
  const key = (e: ErrorItem) => JSON.stringify([e.file, e.step, e.field, e.line, e.message]);
  return all.filter((e, i) => all.findIndex((f) => key(f) === key(e)) === i);
};

/** Link from an error to a file and step (`file` = path under `workflows/`). */
export function errorHref(project: string, e: ErrorItem): string | undefined {
  const m = /^(scenarios|agents|skills)\/([^/]+?)(?:\.yaml|\.md|\/SKILL\.md)$/.exec(e.file ?? "");
  if (m?.[1] === "scenarios") return href(project, "scenarios", m[2], { step: e.step });
  if (m?.[1] === "agents") return href(project, "agents", m[2]);
  if (m?.[1] === "skills") return href(project, "skills", m[2]);
  if (e.file === "config.yaml" || e.file === "mcp.yaml") return href(project, "config");
  return undefined;
}

function ValidationPopover({ errors, project }: { errors: ErrorItem[]; project: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  usePopoverPosition(open, popup, trigger);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => (trigger.current?.contains(e.target as Node) || popup.current?.contains(e.target as Node)) || setOpen(false);
    const blur = (e: FocusEvent) => (trigger.current?.contains(e.target as Node) || popup.current?.contains(e.target as Node)) || setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("focusin", blur);
    popup.current?.focus();
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("focusin", blur); };
  }, [open]);
  return <>
    <button ref={trigger} type="button" data-testid="validation-popover-trigger" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
      <StatusChip status="failed">{t("validation.count", { n: errors.length })}</StatusChip>
    </button>
    {open && createPortal(<div ref={popup} id={id} role="dialog" tabIndex={-1} aria-label={t("validation.count", { n: errors.length })}
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); trigger.current?.focus(); } }}
      className="popover pop-enter fixed z-[60] w-[36rem] max-w-[calc(100vw-24px)] scroll-quiet overflow-y-auto p-4 focus:outline-none">
      <ErrorList errors={errors} hrefFor={(e) => errorHref(project, e)} />
    </div>, document.body)}
  </>;
}

/** Section header (G1): the tab adds actions, ⋯ and a second row; "Reload" is always first in ⋯. */
export type SectionHeader = (x?: {
  description?: ReactNode; meta?: ReactNode; actions?: ReactNode; compact?: MenuItem[]; menu?: MenuItem[]; menuLabel?: string; children?: ReactNode;
}) => ReactNode;

export function ProjectPage({ project, tab, item }: { project: string; tab: Tab; item?: string }) {
  const [gen, setGen] = useState(0);
  const detail = useApi<Project>(`/projects/${enc(project)}`);
  const reload = () => (detail.reload(), setGen(gen + 1));
  const p = detail.data;
  const errors = p ? allErrors(p) : [];
  // nonexistent / unavailable project: no section title, with a way back (like the 404 page)
  if (detail.error?.status === 404)
    return (
      <>
        <PageHeader title={project} actions={<a className={btn.secondary} href="#/">{t("projects.title")}</a>} />
        <ErrorText error={detail.error} />
      </>
    );
  const header: SectionHeader = (x = {}) => (
    <>
      <PageHeader title={t(`project.tab.${tab}`)} description={x.description} actions={x.actions} compact={x.compact} menuLabel={x.menuLabel}
        // until the project loads, the page draws the header and after loading the tab takes it over (a new node) → an open ⋯
        // would close by itself; so there is no ⋯ while loading (Runs does not pass a header, it always has one)
        menu={p || detail.error || tab === "runs" ? [{ label: t("common.reload"), onSelect: reload }, ...(x.menu ?? [])] : undefined}
        meta={<>{x.meta}{errors.length > 0 && <ValidationPopover errors={errors} project={project} />}</>}>
        {x.children}
      </PageHeader>
      {detail.error?.status === 422 && (
        <div role="alert" className="mb-6 space-y-2 rounded-card bg-surface p-4">
          <p className="text-sm text-error">{t("server.config", { error: detail.error.message })}</p>
          <ul className="list-inside list-disc font-mono text-[13px] text-fg-secondary">
            {detail.error.details.map((d) => <li key={d}>{d}</li>)}
          </ul>
          {tab !== "config" && <a className="text-sm underline" href={href(project, "config")}>{t("server.openConfig")}</a>}
        </div>
      )}
      {detail.error && detail.error.status !== 422 && detail.error.status !== 0 && <ErrorText error={detail.error} />}
    </>
  );
  // The tab draws the header once it has data (for Save and the toggle); until then the page draws it.
  const tabOwnsHeader = tab === "config" ? !!(p || detail.error) : tab === "runs" || !!p;
  return (
    <div key={gen}>
      {!tabOwnsHeader && header()}
      {tab === "config" && (p || detail.error) && <ConfigTab name={project} project={p} header={header} onChanged={detail.reload} />}
      {tab === "runs" && <RunsTab project={project} header={header} />}
      {!p ? (
        tab !== "runs" && !detail.error && (tab === "scenarios"
          // same grid and height as the scenario cards, so the page does not jump after loading
          ? <div role="status" aria-label={t("common.loading")} className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-4">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-52 rounded-card" />)}
            </div>
          : <Loading rows={4} />)
      ) : (
        <>
          {tab === "scenarios" && <ScenariosTab project={p} header={header} onChanged={detail.reload} />}
          {tab === "agents" && <AgentsTab project={p} header={header} selected={item} onChanged={detail.reload} />}
          {tab === "skills" && <SkillsTab project={p} header={header} selected={item} onChanged={detail.reload} />}
        </>
      )}
    </div>
  );
}
