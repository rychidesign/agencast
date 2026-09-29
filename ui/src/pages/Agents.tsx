// §2.7 Agents and §2.9 Skills — list on the left, editor on the right (below 1100 px cards and the editor in a bottom sheet). Agent: frontmatter form + instructions
// (`PUT …/agents/<a>`), or the whole file as Markdown (`files/`). Skill: the whole SKILL.md (`PUT …/skills/<n>`).
import { ArrowUpRight, BookOpen, Bot, CircleX, CodeXml, Plus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ApiError, enc, send } from "../api";
import { FormField, inputCls, Modal, NameDialog } from "../components/form";
import { ConflictBar, DiffModal, YamlEditor } from "../components/YamlEditor";
import { Markdown } from "../components/Markdown";
import { PanelShell } from "../components/StepPanel";
import { btn, EmptyState, ErrorList, ErrorText, Loading, Menu, SheetContext, StatusChip, Toggle, useMedia, type Status } from "../components/ui";
import { isObj, mergePatch } from "../edit";
import { t } from "../i18n";
import { href, navigate } from "../router";
import { draftKey, useFileDraft, useLeaveGuard, useTextFile, type FileDraft, type SaveState } from "../textfile";
import type { ErrorItem, Project } from "../types";
import type { SectionHeader } from "./Project";

type Obj = Record<string, unknown>;

/** Below 1100 px the section is only a grid of cards and the editor opens in a bottom sheet (instead of horizontally scrolling chips). */
const NARROW = "(max-width: 1099px)";

/** Agent / skill cards below 1100 px: description, model "alias — id" from config.yaml (agent) and meta "skills · MCP · scenarios"
  *  (agent), "N agents" (skill). */
function FileCards({ project, tab, current }: { project: Project; tab: "agents" | "skills"; current?: string }) {
  const cards = tab === "agents"
    ? project.agents.map((a) => {
        const mcp = Array.isArray(a.mcp) ? a.mcp.length : 0;
        const scenarios = new Set(project.links.scenario_agent.filter(([, ag]) => ag === a.name).map(([s]) => s)).size;
        return { ...a, model: a.model_id ? `${a.model} — ${a.model_id}` : a.model, meta: [a.skills.length ? t("count.skills", { n: a.skills.length }) : "", mcp ? t("count.servers", { n: mcp }) : "",
          scenarios ? t("count.scenarios", { n: scenarios }) : ""] };
      })
    : project.skills.map((s) => {
        const agents = project.links.agent_skill.filter(([, sk]) => sk === s.name).length;
        return { ...s, model: "", meta: [agents ? t("count.agents", { n: agents }) : ""] };
      });
  const Icon = tab === "agents" ? Bot : BookOpen;
  return (
    <ul aria-label={t(`project.tab.${tab}`)} className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-4">
      {cards.map((c) => (
        <li key={c.name} data-testid={`file-card-${c.name}`} className={`relative space-y-2 rounded-tile p-5 ${c.name === current ? "bg-surface-active" : "bg-surface hover:bg-surface-hover"}`}>
          <div className="flex items-center gap-3">
            <Icon className="size-[22px] shrink-0 text-type" aria-hidden />
            <a href={href(project.name, tab, c.name)} aria-current={c.name === current ? "page" : undefined}
              className="min-w-0 flex-1 font-mono text-base leading-6 font-semibold [overflow-wrap:anywhere] after:absolute after:inset-0 after:rounded-tile">{c.name}</a>
            {c.errors.length > 0 && <StatusChip status="failed">{t("validation.count", { n: c.errors.length })}</StatusChip>}
          </div>
          {c.description && <p className="line-clamp-2 text-sm text-fg-secondary">{c.description}</p>}
          {c.model && <p className="truncate font-mono text-xs leading-4 text-fg" title={c.model}>{c.model}</p>}
          {c.meta.some(Boolean) && <p className="font-mono text-[11px] leading-4 text-fg-secondary">{c.meta.filter(Boolean).join(" · ")}</p>}
        </li>
      ))}
    </ul>
  );
}

/** File list of the section on the left, editor on the right; below 1100 px cards and the editor in a bottom sheet (`actions` in its header). */
function MasterDetail({ project, tab, current, sheet, actions, children }: {
  project: Project; tab: "agents" | "skills"; current?: string; sheet: boolean; actions?: ReactNode; children?: ReactNode;
}) {
  const items = tab === "agents" ? project.agents : project.skills;
  const card = `${tab === "agents" ? "agent" : "skill"}-editor-card`;
  if (sheet) return (
    <>
      <FileCards project={project} tab={tab} current={current} />
      {current && children && (
        <SheetContext.Provider value>
          <PanelShell id="file-sheet-title" eyebrow={t(`project.tab.${tab}`)} title={<span className="font-mono">{current}</span>} actions={actions}
            onClose={() => navigate(href(project.name, tab))}>
            <div className="space-y-[18px] [&>section]:pt-2.5" data-testid={card}>{children}</div>
          </PanelShell>
        </SheetContext.Provider>
      )}
    </>
  );
  return (
    // design 06 (measured from .pen): list 240 px, `surface` items r14 p16 gap 14, icon 22, selection = `surface-active`
    <div className="grid grid-cols-[240px_minmax(0,1fr)] gap-6">
      <nav aria-label={t(`project.tab.${tab}`)}>
        <ul className="space-y-2">
          {items.map((it) => (
            <li key={it.name}>
              <a href={href(project.name, tab, it.name)} aria-current={it.name === current ? "page" : undefined}
                className={`flex items-center gap-3.5 rounded-tile p-4 font-mono text-sm font-semibold text-fg ${it.name === current ? "bg-surface-active" : "bg-surface hover:bg-surface-hover"}`}>
                {tab === "agents" ? <Bot className="size-[22px] shrink-0 text-type" aria-hidden /> : <BookOpen className="size-[22px] shrink-0 text-type" aria-hidden />}
                <span className="min-w-0 flex-1 space-y-[3px]">
                  <span className="block truncate leading-5" title={it.name}>{it.name}</span>
                  {it.errors.length > 0 && <span className="block text-[11px] leading-4 font-normal text-error">{t("validation.count", { n: it.errors.length })}</span>}
                </span>
                {it.errors.length > 0 && <CircleX className="size-4 shrink-0 text-error" aria-hidden />}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <section className="min-w-0">
        <div className="space-y-4">
          <h2 className="font-mono text-2xl leading-9 [overflow-wrap:anywhere]">{current}</h2>
          <div className="space-y-[18px] rounded-panel bg-surface p-6 [&>section]:pt-2.5" data-testid={card}>{children}</div>
        </div>
      </section>
    </div>
  );
}

/** Save state with `aria-live` (Saved ✓ / Unsaved / error); with `onJump` the error count is a button that jumps to the first error. */
export function SaveNote({ dirty, state, errors = 0, onJump }: { dirty: boolean; state: SaveState; errors?: number; onJump?: () => void }) {
  const text =
    state.kind === "saving" ? t("save.saving")
    : state.kind === "failed" ? state.message
    : dirty ? t("save.unsaved")
    : state.kind === "saved" ? t("save.saved", { at: state.at })
    : state.kind === "reloaded" ? t("save.reloaded", { at: state.at })
    : t("save.clean");
  // chip as in design 05 ("Saved ✓ 14:02" in green, "Unsaved" in yellow); color and icon by state
  const status: Status = state.kind === "failed" ? "failed" : dirty ? "warning" : state.kind === "saving" ? "none" : "succeeded";
  return (
    <span className="inline-flex items-center gap-2" aria-live="polite">
      <StatusChip status={status}><span data-testid="save-status">{text}</span></StatusChip>
      {errors > 0 && (onJump
        ? <button type="button" onClick={onJump} className="hover:underline"><StatusChip status="failed">{t("validation.count", { n: errors })}</StatusChip></button>
        : <StatusChip status="failed">{t("validation.count", { n: errors })}</StatusChip>)}
    </span>
  );
}

/** Conflict bar, diff and overwrite confirmation for one in-progress file (`markdown` = agent or skill). */
export function useConflictUi(f: Pick<FileDraft<unknown>, "conflict" | "reloadFromDisk" | "keepMine" | "diskText" | "overwrite" | "save">, mine: () => string, markdown = false) {
  const [modal, setModal] = useState<ReactNode>(null);
  const close = () => setModal(null);
  const bar = f.conflict && (
    <ConflictBar conflict={f.conflict} onReload={f.reloadFromDisk} onKeep={f.keepMine}
      onDiff={async () => {
        const disk = await f.diskText();
        setModal(<DiffModal title={t("conflict.diffTitle")} before={mine()} after={disk} onClose={close} note={t("conflict.diffNote")} markdown={markdown} />);
      }} />
  );
  const save = async () => {
    if (!f.overwrite) return f.save();
    return new Promise<boolean>((resolve) =>
      setModal(
        <Modal title={t("conflict.overwriteTitle")} onCancel={() => (close(), resolve(false))}
          actions={[{ label: t("conflict.overwrite"), danger: true, onSelect: async () => (close(), resolve(await f.save())) }]}>
          <p>{t("conflict.overwriteText")}</p>
        </Modal>,
      ));
  };
  return { bar, modal, save, setModal, close };
}

/** File editor header (G1–G4): "+ New …" and Save; ⋯ Rename, Delete. In the sheet the page header has
  *  only "+ New …"; Save and ⋯ are in the sheet header (`actions`). */
function editorBar({ header, sheet, name, tab, onNew, ready, canSave, onSave, onRename, onDelete }: {
  header: SectionHeader; sheet: boolean; name: string; tab: "agents" | "skills"; onNew: () => void; ready: boolean;
  canSave: boolean; onSave: () => void; onRename?: () => void; onDelete: () => void;
}) {
  // without the file etag (still loading) rename and delete are not possible
  const wait = ready ? undefined : t("common.loading");
  const save = <button type="button" className={btn.primary} onClick={onSave} disabled={!canSave} title="Ctrl+S">{t("common.save")}</button>;
  const menuLabel = t("common.menuFor", { name });
  const menu = [
    ...(onRename ? [{ label: t("rename.button"), onSelect: onRename, disabled: wait }] : []),
    { label: t("common.delete"), onSelect: onDelete, disabled: wait, danger: true },
  ];
  if (sheet) return { header: header({ actions: <NewButton tab={tab} primary onClick={onNew} /> }), actions: <>{save}<Menu ghost items={menu} label={menuLabel} /></> };
  return {
    header: header({
      actions: <>
        <span className="contents max-md:hidden"><NewButton tab={tab} onClick={onNew} /></span>
        {save}
      </>,
      compact: [{ label: t(`${tab}.new`), onSelect: onNew }],
      menuLabel,
      menu,
    }),
  };
}

/** "+ New agent" / "+ New skill" in the header: secondary next to Save, primary in an empty section. */
function NewButton({ tab, primary, onClick }: { tab: "agents" | "skills"; primary?: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={primary ? btn.primary : btn.secondary}>
      <Plus className="size-4" aria-hidden />{t(`${tab}.new`)}
    </button>
  );
}

/** Deleting through the API: 422 = protection (used by a scenario / agent), the reason comes from the message. */
export async function deleteFile(url: string, etag: string): Promise<string | null> {
  try {
    await send("DELETE", url, { etag });
    return null;
  } catch (e) {
    const err = e as ApiError;
    return err.errors.map((x) => x.message).join("\n") || err.message;
  }
}

export function DeleteDialog({ what, name, run, onDone, onCancel }: {
  what: string; name: string; run: () => Promise<string | null>; onDone: () => void; onCancel: () => void;
}) {
  const [reason, setReason] = useState<string | null>(null);
  return (
    <Modal title={t("delete.title", { what, name })} onCancel={onCancel}
      actions={reason ? [] : [{ label: t("common.delete"), danger: true, onSelect: async () => {
        const r = await run();
        if (r) setReason(r);
        else onDone();
      } }]}>
      {reason ? <p role="alert" className="font-mono text-xs whitespace-pre-wrap text-error">{reason}</p> : <p>{t("delete.text")}</p>}
    </Modal>
  );
}

// --- agent -------------------------------------------------------------------------------------

interface AgentForm {
  fm: Obj;
  body: string;
}

function AgentEditor({ project, name, header, sheet, onNew, onChanged }: {
  project: Project; name: string; header: SectionHeader; sheet: boolean; onNew: () => void; onChanged: () => void;
}) {
  const path = `agents/${name}.md`;
  const url = `/projects/${enc(project.name)}/agents/${enc(name)}`;
  const [mode, setMode] = useState<"form" | "text">("form");
  const [deleting, setDeleting] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const noticeKey = `agencast.rename.${project.name}/${name}`;
  const [renamedFiles] = useState(() => {
    const files = sessionStorage.getItem(noticeKey);
    if (!files) return [];
    sessionStorage.removeItem(noticeKey);
    return files.split("\n");
  });
  const form = useFileDraft<AgentForm>(project.name, mode === "form" ? path : null, {
    fromDoc: (d) => ({ fm: d.frontmatter ?? {}, body: d.body ?? "" }),
    request: (d, v) => {
      const frontmatter = mergePatch(d.frontmatter ?? {}, v.fm);
      const body = v.body !== d.body ? v.body : undefined;
      return frontmatter || body !== undefined ? { method: "PUT", url, body: { frontmatter, body } } : null;
    },
  }, "agent");
  const text = useTextFile(project.name, mode === "text" ? path : null);
  const active = mode === "form" ? form : text;
  const ui = useConflictUi(active, () => active.doc?.text ?? "", true);
  useLeaveGuard(form.dirty || text.dirty);
  const summary = project.agents.find((a) => a.name === name);
  const usedBy = project.links.scenario_step_agent.filter(([, , ag]) => ag === name);
  const errors = active.state.kind === "failed" || active.dirty || mode === "text" ? active.errors : summary?.errors ?? [];
  const save = async () => {
    const ok = await ui.save();
    if (ok) onChanged();
    return ok;
  };
  const requestRename = () => {
    if (!active.dirty) return setRenaming(true);
    ui.setModal(
      <Modal title={t("mode.title")} onCancel={ui.close} actions={[
        { label: t("mode.save"), primary: true, onSelect: async () => {
          ui.close();
          if (await save()) setRenaming(true);
        } },
        { label: t("mode.discard"), danger: true, onSelect: () => (ui.close(), active.discard(), setRenaming(true)) },
      ]}><p>{t("mode.fileDirty")}</p></Modal>,
    );
  };
  const bar = editorBar({ header, sheet, name, tab: "agents", onNew, ready: !!active.doc,
    canSave: active.dirty && !active.conflict && !(mode === "text" && (text.validating || text.errors.some((e) => e.line))),
    onSave: () => void save(), onRename: requestRename, onDelete: () => setDeleting(true) });
  const switchMode = (m: "form" | "text") => {
    if (!active.dirty) return setMode(m);
    ui.setModal(
      <Modal title={t("mode.title")} onCancel={ui.close} actions={[
        { label: t("mode.save"), primary: true, onSelect: async () => (ui.close(), (await save(), setMode(m))) },
        { label: t("mode.discard"), danger: true, onSelect: () => (ui.close(), active.discard(), setMode(m)) },
      ]}><p>{t("mode.fileDirty")}</p></Modal>,
    );
  };

  return (
    <div onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (active.dirty) void save();
      }
    }}>
      {bar.header}
      <MasterDetail project={project} tab="agents" current={name} sheet={sheet} actions={bar.actions}>
      <div className="flex flex-wrap items-center gap-4">
        <Toggle label={t("code.mode")} value={mode} onChange={switchMode}
          options={[{ key: "form", label: t("code.form"), disabled: mode === "text" && text.errors.some((e) => e.line) ? t("code.fixYaml", { n: text.errors.find((e) => e.line)!.line! }) : undefined },
            { key: "text", label: <><CodeXml className="size-3.5" aria-hidden />{t("code.markdown")}</> }]} />
        <SaveNote dirty={active.dirty} state={active.state} errors={errors.length} />
      </div>
      {ui.bar}
      {renamedFiles.length > 1 && <p role="status" className="text-sm text-fg-muted">{t("rename.changed", { files: renamedFiles.join(", ") })}</p>}
      {active.loadError && <ErrorText error={active.loadError} />}
      {!active.doc && !active.loadError && <Loading rows={5} />}
      {mode === "text" && text.doc && <YamlEditor text={text.text} onChange={text.setText} file={path} errors={text.errors} />}
      {mode === "form" && form.doc && form.value && (
        <AgentFields project={project} name={name} value={form.value} onChange={form.setValue} errors={errors} usedBy={usedBy} />
      )}
      </MasterDetail>
      {ui.modal}
      {renaming && active.doc && (
        <NameDialog title={t("rename.title", { what: t("delete.agent"), name })} initialName={name} submitLabel={t("rename.confirm")}
          pattern={/^[a-z][a-z0-9-]*$/} taken={project.agents.map((a) => a.name).filter((n) => n !== name)} onCancel={() => setRenaming(false)}
          onSubmit={async (newName) => {
            let result: { changed: string[] };
            try {
              result = await send("POST", `${url}/rename`, { etag: active.doc!.etag, name: newName });
            } catch (e) {
              const err = e as ApiError;
              throw new Error(err.errors.map((x) => x.message).join("\n") || err.message);
            }
            localStorage.removeItem(draftKey(project.name, path, "agent"));
            localStorage.removeItem(draftKey(project.name, path));
            if (result.changed.length > 1) sessionStorage.setItem(`agencast.rename.${project.name}/${newName}`, result.changed.join("\n"));
            onChanged();
            navigate(href(project.name, "agents", newName));
          }} />
      )}
      {deleting && active.doc && (
        <DeleteDialog what={t("delete.agent")} name={name} onCancel={() => setDeleting(false)}
          run={() => deleteFile(url, active.doc!.etag)}
          onDone={() => (setDeleting(false), onChanged(), navigate(href(project.name, "agents")))} />
      )}
    </div>
  );
}

function AgentFields({ project, name, value, onChange, errors, usedBy }: {
  project: Project; name: string; value: AgentForm; onChange: (v: AgentForm) => void; errors: ErrorItem[]; usedBy: [string, string, string][];
}) {
  const fm = value.fm;
  const setFm = (k: string, v: unknown) => {
    const next = { ...fm };
    if (v === undefined || v === "" || (Array.isArray(v) && !v.length) || (isObj(v) && !Object.keys(v).length)) delete next[k];
    else next[k] = v;
    onChange({ ...value, fm: next });
  };
  const fe = (p: string) => errors.filter((e) => e.field === p || e.field?.startsWith(`${p}.`));
  const skills = Array.isArray(fm.skills) ? (fm.skills as string[]) : [];
  const mcp = Array.isArray(fm.mcp) ? (fm.mcp as string[]) : [];
  const tools: Record<string, string[]> = isObj(fm.tools) ? (fm.tools as Record<string, string[]>) : {};
  const limits: Obj = isObj(fm.limits) ? fm.limits : {};
  const setLimit = (k: string, v: unknown) => setFm("limits", { ...limits, [k]: v === "" ? undefined : v });
  const needTurns = mcp.length > 0;
  const toggleServer = (srv: string, on: boolean, all: string[] | null) => {
    const nextMcp = on ? [...mcp, srv] : mcp.filter((x) => x !== srv);
    const nextTools = { ...tools };
    if (on) nextTools[srv] = all ?? [];
    else delete nextTools[srv];
    const next = { ...fm };
    for (const [k, v] of [["mcp", nextMcp], ["tools", nextTools]] as const) {
      if ((Array.isArray(v) && v.length) || (!Array.isArray(v) && Object.keys(v).length)) next[k] = v;
      else delete next[k];
    }
    onChange({ ...value, fm: next });
  };
  const known = ["description", "model", "skills", "mcp", "tools", "limits"];
  return (
    // fields 18 px apart, section headings 16 semibold with 10 px padding above (design 06, measured from .pen)
    <div className="space-y-[18px] [&>section]:pt-2.5">
      <ErrorList errors={errors.filter((e) => !e.field || !known.some((k) => e.field === k || e.field!.startsWith(`${k}.`)))} />
      <FormField label={t("agent.description")} errors={fe("description")} required>
        {(a) => <input {...a} className={inputCls} value={String(fm.description ?? "")} onChange={(e) => setFm("description", e.target.value)} />}
      </FormField>
      <FormField label={t("agent.model")} help={t("agent.modelHelp")} errors={fe("model")} required>
        {(a) => (
          <select {...a} className={inputCls} value={String(fm.model ?? "")} onChange={(e) => setFm("model", e.target.value)}>
            <option value="">—</option>
            {fm.model && !(String(fm.model) in project.models) ? <option value={String(fm.model)}>{String(fm.model)}</option> : null}
            {Object.entries(project.models).map(([alias, id]) => <option key={alias} value={alias}>{alias} — {id}</option>)}
          </select>
        )}
      </FormField>
      <section className="space-y-3">
        <h3 className="text-base font-semibold">{t("agent.skills")}</h3>
        <ErrorList errors={fe("skills")} />
        <ul className="rounded-[10px] bg-nested px-3.5 py-1.5" aria-label={t("agent.skills")}>
          {[...project.skills.map((s) => s.name), ...skills.filter((s) => !project.skills.some((known) => known.name === s))].map((s) => (
            <li key={s}>
              <label className="flex min-h-10 items-center gap-2.5 text-[13px] hover:text-fg">
                <input type="checkbox" checked={skills.includes(s)}
                  onChange={(e) => setFm("skills", e.target.checked ? [...skills, s] : skills.filter((x) => x !== s))} />
                <span className="min-w-0 flex-1 truncate">{s}</span><span className="font-mono text-[11px] text-fg-muted">SKILL.md</span>
              </label>
            </li>
          ))}
          {!project.skills.length && !skills.length && <li className="px-2 py-2 text-sm text-fg-muted">–</li>}
        </ul>
      </section>
      <section className="space-y-3">
        <h3 className="text-base font-semibold">{t("agent.mcp")}</h3>
        <p className="text-xs text-fg-muted">{t("agent.mcpHelp")}</p>
        <ErrorList errors={[...fe("mcp"), ...fe("tools")]} />
          <ul className="rounded-[10px] bg-nested px-3.5 py-1.5">
            {project.mcp_servers.map((s) => {
              const allowed = !!s.agents?.includes(name);
              const on = mcp.includes(s.name);
              return (
                <li key={s.name}>
                  <label className="flex min-h-10 items-center gap-2.5 text-[13px] hover:text-fg">
                    <input type="checkbox" checked={on} disabled={!allowed && !on} onChange={(e) => toggleServer(s.name, e.target.checked, s.tools)} />
                    <span className="min-w-0 flex-1 truncate">{s.name}</span>
                    {!allowed && <span className="font-sans text-xs text-fg-muted">{t("agent.mcpNotAllowed")}</span>}
                    <span className="font-mono text-[11px] text-fg-muted">{s.tools?.length ?? 0} {t("agent.toolsCount")}</span>
                  </label>
                  {on && (
                    <div className="ml-7">
                      {(s.tools ?? tools[s.name] ?? []).map((tool) => {
                        const cur = tools[s.name] ?? [];
                        return (
                          <label key={tool} className="flex min-h-10 items-center gap-2.5 text-[13px] hover:text-fg">
                            <input type="checkbox" checked={cur.includes(tool)}
                              onChange={(e) => setFm("tools", { ...tools, [s.name]: e.target.checked ? [...cur, tool] : cur.filter((x) => x !== tool) })} />
                            <span className="min-w-0 flex-1 truncate">{tool}</span>
                          </label>
                        );
                      })}
                      {!s.tools && <span className="text-xs text-fg-muted">{t("agent.toolsFree")}</span>}
                    </div>
                  )}
                </li>
              );
            })}
            {!project.mcp_servers.length && <li className="text-sm text-fg-muted">–</li>}
          </ul>
      </section>
      <section className="space-y-3">
        <h3 className="text-base font-semibold">{t("config.limits")}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="max_turns" required={needTurns} errors={fe("limits.max_turns")}
            help={needTurns ? t("agent.turnsRequired") : t("agent.turnsHelp")}>
            {(a) => (
              <input {...a} type="number" min={1} aria-required={needTurns}
                className={`${inputCls} font-mono`}
                value={typeof limits.max_turns === "number" ? limits.max_turns : ""}
                onChange={(e) => setLimit("max_turns", e.target.value === "" ? undefined : Number(e.target.value))} />
            )}
          </FormField>
          <FormField label="budget_usd" errors={fe("limits.budget_usd")} required>
            {(a) => <input {...a} type="number" step={0.01} min={0} className={`${inputCls} font-mono`} value={typeof limits.budget_usd === "number" ? limits.budget_usd : ""}
              onChange={(e) => setLimit("budget_usd", e.target.value === "" ? undefined : Number(e.target.value))} />}
          </FormField>
          <FormField label="timeout" errors={fe("limits.timeout")}>
            {(a) => <input {...a} className={`${inputCls} font-mono`} placeholder="5m" value={String(limits.timeout ?? "")} onChange={(e) => setLimit("timeout", e.target.value)} />}
          </FormField>
        </div>
      </section>
      <section className="space-y-3">
        <div className="[&_label]:text-base [&_label]:font-semibold">
          <FormField label={t("agent.instructions")} errors={fe("body")} required>
            {(a) => <div className="overflow-hidden rounded-[10px] bg-nested"><textarea {...a} rows={Math.min(24, Math.max(12, value.body.split("\n").length + 1))} className={`${inputCls.replace("bg-nested", "bg-transparent")} resize-y rounded-none font-mono text-[13px] leading-5`}
              value={value.body} onChange={(e) => onChange({ ...value, body: e.target.value })} /><p className="border-t border-line px-3 py-2 text-xs text-fg-muted">{t("agent.markdownHelp")}</p></div>}
          </FormField>
        </div>
      </section>
      <section className="space-y-3">{usedBy.length > 0 && <h3 className="text-base font-semibold">{t("agent.usedBy")}</h3>}
        {usedBy.length ? usedBy.map(([s, step]) => <a key={`${s}/${step}`} className="flex min-h-11 items-center justify-between gap-3 rounded-control bg-nested px-3 font-mono text-[13px] text-fg-secondary hover:text-fg" href={href(project.name, "scenarios", s, { step })}>{s} / {step}<ArrowUpRight className="size-4 shrink-0" aria-hidden /></a>) : <p className="text-sm text-fg-muted">{t("agent.usedBy")}: –</p>}
      </section>
    </div>
  );
}

export function AgentsTab({ project, header, selected, onChanged }: { project: Project; header: SectionHeader; selected?: string; onChanged: () => void }) {
  const [creating, setCreating] = useState(false);
  const sheet = useMedia(NARROW);
  // in the sheet nothing is opened without a selection, only cards
  const current = selected ?? (sheet ? undefined : project.agents[0]?.name);
  return (
    <>
      {current ? (
        <AgentEditor key={current} project={project} name={current} header={header} sheet={sheet} onChanged={onChanged}
          onNew={() => setCreating(true)} />
      ) : (
        <>
          {header({ actions: <NewButton tab="agents" primary onClick={() => setCreating(true)} /> })}
          {project.agents.length ? <MasterDetail project={project} tab="agents" sheet /> : <EmptyState text={t("agents.empty")} />}
        </>
      )}
      {creating && (
        <NameDialog title={t("agents.new")} withDescription models={Object.keys(project.models)} taken={project.agents.map((a) => a.name)}
          onCancel={() => setCreating(false)}
          onSubmit={async (name, description, model) => {
            await send("POST", `/projects/${enc(project.name)}/agents`, { name, ...(description ? { description } : {}), ...(model ? { model } : {}) });
            setCreating(false);
            onChanged();
            navigate(href(project.name, "agents", name));
          }} />
      )}
    </>
  );
}

// --- skill -------------------------------------------------------------------------------------

function SkillEditor({ project, name, header, sheet, onNew, onChanged }: {
  project: Project; name: string; header: SectionHeader; sheet: boolean; onNew: () => void; onChanged: () => void;
}) {
  const path = `skills/${name}/SKILL.md`;
  const url = `/projects/${enc(project.name)}/skills/${enc(name)}`;
  const text = useTextFile(project.name, path, url);
  const ui = useConflictUi(text, () => text.doc?.text ?? "", true);
  const [deleting, setDeleting] = useState(false);
  useLeaveGuard(text.dirty);
  const usedBy = project.links.agent_skill.filter(([, sk]) => sk === name).map(([a]) => a);
  const syntax = text.errors.find((e) => e.line);
  const save = async () => {
    if (await ui.save()) onChanged();
  };
  const bar = editorBar({ header, sheet, name, tab: "skills", onNew, ready: !!text.doc,
    canSave: text.dirty && !text.conflict && !text.validating && !syntax, onSave: () => void save(), onDelete: () => setDeleting(true) });
  return (
    <div onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (text.dirty) void save();
      }
    }}>
      {bar.header}
      <MasterDetail project={project} tab="skills" current={name} sheet={sheet} actions={bar.actions}>
      <div className="flex flex-wrap items-center gap-4"><span className="font-mono text-sm text-fg-secondary">Markdown · SKILL.md</span><SaveNote dirty={text.dirty} state={text.state} errors={text.errors.length} /></div>
      {ui.bar}
      {text.loadError && <ErrorText error={text.loadError} />}
      {text.doc ? <YamlEditor text={text.text} onChange={text.setText} file={path} errors={text.errors} /> : !text.loadError && <Loading rows={5} />}
      {/* preview of the body without frontmatter (design 07 "Preview") */}
      {text.doc && (
        <section className="space-y-3"><h3 className="text-base font-semibold">{t("files.preview")}</h3>
          <div className="rounded-panel bg-nested p-6"><Markdown text={text.text.replace(/^---\n[\s\S]*?\n---\n?/, "")} /></div>
        </section>
      )}
      <section className="space-y-3"><h3 className="text-base font-semibold">{t("skill.usedBy")}</h3>
        {usedBy.length ? usedBy.map((a) => <a key={a} className="flex min-h-11 items-center justify-between gap-3 rounded-control bg-nested px-3 font-mono text-[13px] text-fg-secondary hover:text-fg" href={href(project.name, "agents", a)}>{a}<ArrowUpRight className="size-4 shrink-0" aria-hidden /></a>) : <p className="text-sm text-fg-muted">–</p>}
      </section>
      </MasterDetail>
      {ui.modal}
      {deleting && text.doc && (
        <DeleteDialog what={t("delete.skill")} name={name} onCancel={() => setDeleting(false)} run={() => deleteFile(url, text.doc!.etag)}
          onDone={() => (setDeleting(false), onChanged(), navigate(href(project.name, "skills")))} />
      )}
    </div>
  );
}

/** New SKILL.md: frontmatter with only a name and description (the description as a JSON string = a valid YAML scalar). */
export const skillTemplate = (name: string, description: string) =>
  `---\nname: ${name}\ndescription: ${JSON.stringify(description || name)}\n---\n${t("skill.templateBody")}\n`;

export function SkillsTab({ project, header, selected, onChanged }: { project: Project; header: SectionHeader; selected?: string; onChanged: () => void }) {
  const [creating, setCreating] = useState(false);
  const sheet = useMedia(NARROW);
  // in the sheet nothing is opened without a selection, only cards
  const current = selected ?? (sheet ? undefined : project.skills[0]?.name);
  return (
    <>
      {current ? (
        <SkillEditor key={current} project={project} name={current} header={header} sheet={sheet} onChanged={onChanged}
          onNew={() => setCreating(true)} />
      ) : (
        <>
          {header({ actions: <NewButton tab="skills" primary onClick={() => setCreating(true)} /> })}
          {project.skills.length ? <MasterDetail project={project} tab="skills" sheet /> : <EmptyState text={t("skills.empty")} />}
        </>
      )}
      {creating && (
        <NameDialog title={t("skills.new")} withDescription taken={project.skills.map((s) => s.name)} onCancel={() => setCreating(false)}
          onSubmit={async (name, description) => {
            await send("PUT", `/projects/${enc(project.name)}/skills/${enc(name)}`, { etag: null, text: skillTemplate(name, description) });
            setCreating(false);
            onChanged();
            navigate(href(project.name, "skills", name));
          }} />
      )}
    </>
  );
}
