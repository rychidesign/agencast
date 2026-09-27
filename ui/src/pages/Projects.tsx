// §2.1 Seznam projektů (karty); přidání a odebrání projektu z registru (api.md 0.9.0).
import { CircleSlash, FolderPlus, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { FormField, inputCls, Modal, submitOnEnter } from "../components/form";
import { PageHeader, type HeaderMenuItem } from "../components/PageHeader";
import { btn, CliLine, ErrorText, Menu, Skeleton, Toggle } from "../components/ui";
import { formatCost } from "../format";
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
      <PageHeader title={t("projects.title")}
        description={list.data && <span className="font-mono text-[13px] text-fg-muted">{t("projects.registry", { path: list.data.registry })}</span>}
        actions={<>
          <button type="button" className={btn.icon} onClick={reload} aria-label={t("common.reload")} title={t("common.reload")}>
            <RefreshCw className="size-4" aria-hidden />
          </button>
          <button type="button" className={btn.primary} onClick={() => setAdding(true)} disabled={!list.data}>
            <Plus className="size-4" aria-hidden />{t("projects.add")}
          </button>
        </>} />
      {list.error && list.error.status !== 0 && <ErrorText error={list.error} />}
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-4">
        {list.loading && !list.data && [0, 1].map((i) => <li key={i}><Skeleton className="h-44 rounded-card" /></li>)}
        {list.data?.projects.map((p) => (
          <ProjectCard key={`${p.name}-${gen}`} project={p} onRemove={writable ? () => setRemoving(p) : undefined} />
        ))}
        {list.data && !list.data.projects.length && (
          <li className="col-span-full">
            <button type="button" onClick={() => setAdding(true)}
              className="flex min-h-44 w-full flex-col items-center justify-center gap-3 rounded-card border border-dashed border-line p-5 text-fg-secondary hover:bg-surface-hover hover:text-fg">
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
  const menu: HeaderMenuItem[] = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("projects.copyPath"), onSelect: () => navigator.clipboard.writeText(project.root) },
    ...(onRemove ? [{ label: t("projects.remove"), onSelect: onRemove, danger: true }] : []),
  ];
  return (
    <li data-testid={`project-card-${project.name}`}
      className={`relative flex min-h-44 flex-col rounded-card p-5 ${project.available ? "bg-surface hover:bg-surface-hover" : "border border-dashed border-line opacity-50"}`}>
      <div className="flex items-start justify-between gap-2">
        <h2 className="min-w-0 pt-1 text-lg font-semibold break-words">
          <a href={open} className="after:absolute after:inset-0 after:rounded-card">{project.name}</a>
        </h2>
        <div className="relative z-10 -mt-1 -mr-2"><Menu items={menu} label={t("common.menuFor", { name: project.name })} /></div>
      </div>
      <p className="truncate font-mono text-[13px] text-fg-muted" title={project.root}>{project.root}</p>
      <div className="mt-auto pt-4 text-[13px] text-fg-secondary">
        {!project.available ? (
          <p className="space-y-1">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-nested px-2 py-0.5 text-xs">
              <CircleSlash className="size-3.5" aria-hidden />{t("projects.unavailable")}
            </span>
            <span className="block">{project.reason ?? t("projects.unavailable")}</span>
          </p>
        ) : (
          <div className="space-y-3">
            <p>{t("count.scenarios", { n: project.counts.scenarios })} · {t("count.agents", { n: project.counts.agents })}</p>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
              <LastRun run={project.last_run} />
              <span className="font-mono">{t("spend.today", { usd: formatCost(project.spend_today_usd) })}</span>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

const PROJECT_NAME = /^[a-z][a-z0-9-]*$/;
/** Jméno z poslední složky cesty (jako `default_name` v CLI): malá písmena, jinak pomlčka. */
export const nameFromPath = (path: string) =>
  (path.replace(/\/+$/, "").split("/").pop() ?? "").toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^[^a-z]+/, "");

/** „Přidat projekt“: založit nový (`POST /projects/new`), nebo přidat existující (`POST /projects`).
 *  Bez práva zápisu registru (`writable: false`) jen příkaz pro CLI. */
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
        <CliLine cmd="agencast projects add <cesta>" />
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
          {(a) => <input {...a} data-autofocus value={shownName} onChange={(e) => setName(e.target.value)} className={`${inputCls} font-mono text-[13px]`} autoComplete="off" />}
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
