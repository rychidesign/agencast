// §2.1 Seznam projektů (karty); přidání a odebrání projektu z registru (api.md 0.9.0).
import { Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { FormField, inputCls, Modal, submitOnEnter } from "../components/form";
import { CliLine, ErrorText, Menu, Skeleton, Toggle } from "../components/ui";
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
    <main className="mx-auto max-w-6xl p-4 sm:p-8">
      <header className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("projects.title")}</h1>
          <p className="text-sm text-zinc-400">{t("projects.subtitle")}</p>
          {list.data && <p className="font-mono text-[13px] text-zinc-400">{t("projects.registry", { path: list.data.registry })}</p>}
        </div>
        <button type="button" className="grid size-8 place-items-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          onClick={reload} aria-label={t("common.reload")} title={t("common.reload")}>
          <RefreshCw className="size-4" aria-hidden />
        </button>
      </header>
      {list.error && list.error.status !== 0 && <ErrorText error={list.error} />}
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-4">
        <li>
          <button type="button" onClick={() => setAdding(true)}
            className="flex min-h-44 w-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-600 p-5 text-zinc-300 hover:bg-zinc-800/40 hover:text-zinc-100">
            <Plus className="size-6" aria-hidden />
            <span className="text-sm">{t("projects.add")}</span>
          </button>
        </li>
        {list.loading && !list.data && [0, 1].map((i) => <li key={i}><Skeleton className="h-44 rounded-xl" /></li>)}
        {list.data?.projects.map((p) => (
          <ProjectCard key={`${p.name}-${gen}`} project={p} onRemove={writable ? () => setRemoving(p) : undefined} />
        ))}
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
    </main>
  );
}

function ProjectCard({ project, onRemove }: { project: ProjectRef; onRemove?: () => void }) {
  const open = href(project.name);
  const menu = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("projects.copyPath"), onSelect: () => navigator.clipboard.writeText(project.root) },
    ...(onRemove ? [{ label: t("projects.remove"), onSelect: onRemove }] : []),
  ];
  return (
    <li data-testid={`project-card-${project.name}`} className={`relative flex min-h-44 flex-col rounded-xl p-5 ${project.available ? "bg-zinc-800/60 hover:bg-zinc-800" : "border border-dashed border-zinc-600 opacity-50"}`}>
      <div className="flex items-center justify-between text-xs text-zinc-400">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className={`size-2 rounded-full ${project.available ? "bg-emerald-400" : "ring-1 ring-zinc-400"}`} />
          {project.available ? t("projects.available") : t("projects.unavailable")}
        </span>
        <div className="relative z-10"><Menu items={menu} label={t("common.menuFor", { name: project.name })} /></div>
      </div>
      <h2 className="mt-2 text-lg font-semibold">
        <a href={open} className="after:absolute after:inset-0 after:rounded-xl">{project.name}</a>
      </h2>
      <p className="truncate font-mono text-[13px] text-zinc-400" title={project.root}>{project.root}</p>
      <div className="mt-auto pt-4 text-[13px] text-zinc-300">
        {!project.available ? (
          <p className="text-zinc-300">{project.reason ?? t("projects.unavailable")}</p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {t("count.scenarios", { n: project.counts.scenarios })} · {t("count.agents", { n: project.counts.agents })}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="font-mono">{t("spend.today", { usd: formatCost(project.spend_today_usd) })}</span>
              <LastRun run={project.last_run} />
            </span>
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
          <div role="alert" className="space-y-1 font-mono text-xs whitespace-pre-wrap text-rose-400">
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
