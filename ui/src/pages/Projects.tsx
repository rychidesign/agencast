// §2.1 Project list (cards); adding and removing a project in the registry (api.md 0.9.0).
import { CircleSlash, FolderPlus, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { FormField, inputCls, Modal, slugify, slugProps, submitOnEnter } from "../components/form";
import { headerIconBtn, PageHeader } from "../components/PageHeader";
import { btn, CliLine, ErrorText, Menu, Skeleton, Toggle, type MenuItem } from "../components/ui";
import { formatSpend } from "../format";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { ProjectList, ProjectRef } from "../types";
import { LastRun } from "../components/RunBadge";

export function ProjectsPage() {
  const [gen, setGen] = useState(0);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<ProjectRef>();
  const list = useApi<ProjectList>("/projects");
  const reload = () => (list.reload(), setGen(gen + 1));
  const writable = !!list.data?.writable;
  return (
    <>
      <PageHeader title={t("projects.title")} description={t("projects.description")}
        compact={[{ label: t("common.reload"), onSelect: reload }]}
        actions={<>
          <button type="button" className={`${headerIconBtn} max-md:hidden`} onClick={reload} aria-label={t("common.reload")} title={t("common.reload")}>
            <RefreshCw aria-hidden />
          </button>
          <button type="button" className={btn.primary} onClick={() => setAdding(true)} disabled={!list.data}>
            <Plus className="size-4" aria-hidden />{t("projects.add")}
          </button>
        </>}>
        {/* registry path as a separate row under the header (design 02, measured from .pen: mono 12, gap 24) */}
        {list.data && <p className="truncate font-mono text-xs leading-[18px] text-fg-muted" title={t("projects.registry", { path: list.data.registry })}>{list.data.registry}</p>}
      </PageHeader>
      {list.error && list.error.status !== 0 && <ErrorText error={list.error} />}
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-5">
        {list.loading && !list.data && [0, 1].map((i) => <li key={i}><Skeleton className="h-[260px] rounded-tile" /></li>)}
        {list.data?.projects.map((p) => (
          <ProjectCard key={`${p.name}-${gen}`} project={p} onRemove={writable ? () => setRemoving(p) : undefined} />
        ))}
        {list.data && !list.data.projects.length && (
          <li className="col-span-full">
            <button type="button" onClick={() => setAdding(true)}
              className="flex min-h-[260px] w-full flex-col items-center justify-center gap-3 rounded-tile border border-dashed border-line p-5 text-fg-secondary hover:bg-surface-hover hover:text-fg">
              <FolderPlus className="size-6" aria-hidden />
              <span className="text-sm">{t("projects.add")}</span>
            </button>
          </li>
        )}
      </ul>
      {adding && list.data && (
        <AddProjectDialog list={list.data} onCancel={() => setAdding(false)}
          onDone={(name, created) => {
            setAdding(false);
            if (created) navigate(href(name));
            else reload();
          }} />
      )}
      {removing && <RemoveProjectDialog project={removing} onCancel={() => setRemoving(undefined)} onDone={() => (setRemoving(undefined), reload())} />}
    </>
  );
}

function ProjectCard({ project, onRemove }: { project: ProjectRef; onRemove?: () => void }) {
  const open = href(project.name);
  const menu: MenuItem[] = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("projects.copyPath"), onSelect: () => navigator.clipboard.writeText(project.root) },
    ...(onRemove ? [{ label: t("projects.remove"), onSelect: onRemove, danger: true }] : []),
  ];
  // Design 02 (measured from .pen): radius 14, padding 22, min. height 260, gaps 20; top row = unavailability chip (G6) and ⋯,
  // then name 20, path, count chips, divider, run state + spend.
  return (
    <li data-testid={`project-card-${project.name}`}
      className={`relative flex min-h-[260px] flex-col gap-5 rounded-tile p-[22px] max-md:min-h-0 max-md:p-5 ${project.available ? "bg-surface hover:bg-surface-hover" : "border border-dashed border-line"}`}>
      <div className="-my-[7px] flex min-h-11 items-center justify-between gap-2">
        {project.available ? <span /> : (
          <span className="inline-flex items-center gap-2 rounded-full bg-nested px-2.5 py-[7px] text-xs font-medium text-fg-secondary">
            <CircleSlash className="size-3.5" aria-hidden />{t("projects.unavailable")}
          </span>
        )}
        <div className="relative z-10 -mr-3"><Menu ghost items={menu} label={t("common.menuFor", { name: project.name })} /></div>
      </div>
      <div className="space-y-2">
        <h2 className="min-w-0 text-xl leading-[29px] font-semibold break-words">
          <a href={open} className="after:absolute after:inset-0 after:rounded-tile">{project.name}</a>
        </h2>
        <p className="truncate font-mono text-xs text-fg-muted" title={project.root}>{project.root}</p>
      </div>
      {!project.available ? (
        <p className="mt-auto text-[13px] break-words text-fg-secondary">{project.reason ?? t("projects.unavailable")}</p>
      ) : (
        <>
          <p className="flex flex-wrap gap-2 font-mono text-[11px] leading-4 text-fg-secondary">
            <span className="rounded-[6px] bg-nested px-[9px] py-[5px]">{t("count.scenarios", { n: project.counts.scenarios })}</span>
            <span className="rounded-[6px] bg-nested px-[9px] py-[5px]">{t("count.agents", { n: project.counts.agents })}</span>
          </p>
          <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3.5">
            <LastRun run={project.last_run} />
            <span className="font-mono text-xs text-fg-secondary">{t("spend.today", { usd: formatSpend(project.spend_today_usd) })}</span>
          </div>
        </>
      )}
    </li>
  );
}

const PROJECT_NAME = /^[a-z][a-z0-9-]*$/;
/** Name from the last path folder (like `default_name` in the CLI): lowercase letters, dash for anything else. */
export const nameFromPath = (path: string) =>
  (path.replace(/\/+$/, "").split("/").pop() ?? "").toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^[^a-z]+/, "");

/** "Add project": create a new one (`POST /projects/new`), or add an existing one (`POST /projects`).
 *  Without registry write permission (`writable: false`) only a CLI command. */
function AddProjectDialog({ list, onCancel, onDone }: {
  list: ProjectList; onCancel: () => void; onDone: (name: string, created: boolean) => void;
}) {
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [name, setName] = useState("");
  const [path, setPath] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);
  const root = list.projects_root.replace(/\/+$/, "");
  const shownPath = path ?? (mode === "new" ? `${root}/${name}` : "");
  const shownName = mode === "existing" && !name && path ? nameFromPath(path) : name;
  const taken = list.projects.map((p) => p.name);
  const problem = !shownName ? null : !PROJECT_NAME.test(shownName) ? t("form.slug") : taken.includes(shownName) ? t("form.taken", { name: shownName }) : null;
  const ready = !problem && !!shownPath && (mode === "existing" || !!shownName);
  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const r = mode === "new"
        ? await send<{ name: string }>("POST", "/projects/new", { name: shownName, root: shownPath })
        : await send<{ name: string }>("POST", "/projects", { root: shownPath, ...(shownName ? { name: shownName } : {}) });
      onDone(r.name, mode === "new");
    } catch (e) {
      setError(e as ApiError);
      setBusy(false);
    }
  };
  if (!list.writable)
    return (
      <Modal title={t("projects.add")} onCancel={onCancel} actions={[]} cancelLabel={t("common.close")}>
        <p>{t("projects.addCli")}</p>
        <CliLine cmd="agencast projects add <path>" />
      </Modal>
    );
  return (
    <Modal title={t(mode === "new" ? "projects.newTitle" : "projects.existingTitle")} onCancel={onCancel}
      actions={[{ label: busy ? t("common.saving") : t(mode === "new" ? "common.create" : "projects.addButton"), primary: true, onSelect: submit }]}>
      <form onSubmit={(e) => (e.preventDefault(), submit())} onKeyDown={submitOnEnter(submit)} className="space-y-3">
        <Toggle label={t("projects.mode")} value={mode} onChange={(m) => (setMode(m), setPath(undefined), setError(undefined))}
          options={[{ key: "new", label: t("projects.modeNew") }, { key: "existing", label: t("projects.modeExisting") }]} />
        {mode === "existing" && pathField()}
        <FormField label={t("form.name")} help={t(mode === "new" ? "projects.nameHelp" : "projects.nameExistingHelp")} errors={problem ? [problem] : []} required={mode === "new"}>
          {(a) => <input {...a} data-autofocus value={shownName} {...slugProps(setName, slugify)} className={`${inputCls} font-mono text-[13px]`} autoComplete="off" />}
        </FormField>
        {mode === "new" && pathField()}
        {error && (
          <div role="alert" className="space-y-1 font-mono text-xs whitespace-pre-wrap text-error">
            <p>{error.message}</p>
            {error.details.map((d) => <p key={d}>{d}</p>)}
          </div>
        )}
      </form>
    </Modal>
  );

  function pathField() {
    return (
      <FormField label={t("projects.path")} help={t(mode === "new" ? "projects.pathHelp" : "projects.pathExistingHelp", { root })} required>
        {(a) => <input {...a} value={shownPath} onChange={(e) => setPath(e.target.value)} className={`${inputCls} font-mono text-[13px]`} autoComplete="off" />}
      </FormField>
    );
  }
}

function RemoveProjectDialog({ project, onCancel, onDone }: { project: ProjectRef; onCancel: () => void; onDone: () => void }) {
  const [error, setError] = useState<ApiError>();
  return (
    <Modal title={t("projects.removeTitle", { name: project.name })} onCancel={onCancel}
      actions={[{ label: t("projects.removeButton"), danger: true, onSelect: async () => {
        try {
          await send("DELETE", `/projects/${enc(project.name)}`);
          onDone();
        } catch (e) {
          setError(e as ApiError);
        }
      } }]}>
      <p>{t("projects.removeText", { root: project.root })}</p>
      {error && <ErrorText error={error} />}
    </Modal>
  );
}
