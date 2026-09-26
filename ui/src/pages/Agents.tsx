// §2.7 Agenti a §2.9 Skilly — seznam vlevo, editor vpravo. Agent: formulář frontmatteru + instrukce
// (`PUT …/agents/<a>`), nebo celý soubor jako Markdown (`files/`). Skill: celý SKILL.md (`PUT …/skills/<n>`).
import { CodeXml, Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ApiError, enc, send } from "../api";
import { FormField, inputCls, Modal, NameDialog } from "../components/form";
import { ConflictBar, DiffModal, YamlEditor } from "../components/YamlEditor";
import { btn, EmptyState, ErrorList, ErrorText, Loading, StatusChip, Toggle } from "../components/ui";
import { isObj, mergePatch } from "../edit";
import { t } from "../i18n";
import { href, navigate, type Tab } from "../router";
import { useFileDraft, useLeaveGuard, useTextFile, type FileDraft, type SaveState } from "../textfile";
import type { ErrorItem, Project } from "../types";

type Obj = Record<string, unknown>;

export function MasterDetail({ project, tab, items, selected, onNew, children }: {
  project: Project; tab: Tab; items: { name: string; errors: ErrorItem[] }[]; selected?: string; onNew: () => void;
  children: (name: string) => ReactNode;
}) {
  const current = selected ?? items[0]?.name;
  return (
    <div className="grid grid-cols-[14rem_1fr] gap-8">
      <nav aria-label={t(`project.tab.${tab}`)} className="space-y-2">
        <button type="button" onClick={onNew} className={`${btn.secondary} w-full`}>
          <Plus className="size-4" aria-hidden />{t(`${tab}.new`)}
        </button>
        <ul className="space-y-0.5">
          {items.map((it) => (
            <li key={it.name}>
              <a href={href(project.name, tab, it.name)} aria-current={it.name === current ? "page" : undefined}
                className={`flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm ${it.name === current ? "bg-zinc-800 text-zinc-100" : "text-zinc-300 hover:bg-zinc-800/60"}`}>
                <span className="truncate font-mono">{it.name}</span>
                {it.errors.length > 0 && <span className="shrink-0 text-xs text-rose-400">✗ {t("validation.count", { n: it.errors.length })}</span>}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <section>{current ? children(current) : <EmptyState text={t(`${tab}.empty`)} />}</section>
    </div>
  );
}

/** Stav uložení s `aria-live` (Uloženo ✓ / Neuloženo / chyba). */
export function SaveNote({ dirty, state, errors = 0 }: { dirty: boolean; state: SaveState; errors?: number }) {
  const text =
    state.kind === "saving" ? t("save.saving")
    : state.kind === "failed" ? state.message
    : dirty ? t("save.unsaved")
    : state.kind === "saved" ? t("save.saved", { at: state.at })
    : state.kind === "reloaded" ? t("save.reloaded", { at: state.at })
    : t("save.clean");
  return (
    <span className="inline-flex items-center gap-2 text-sm" aria-live="polite">
      <span className={state.kind === "failed" ? "text-rose-400" : "text-zinc-400"}>{text}</span>
      {errors > 0 && <StatusChip status="failed">{t("validation.count", { n: errors })}</StatusChip>}
    </span>
  );
}

/** Konfliktový pruh, rozdíl a potvrzení přepsání pro jeden rozpracovaný soubor. */
export function useConflictUi(f: Pick<FileDraft<unknown>, "conflict" | "reloadFromDisk" | "keepMine" | "diskText" | "overwrite" | "save">, mine: () => string) {
  const [modal, setModal] = useState<ReactNode>(null);
  const close = () => setModal(null);
  const bar = f.conflict && (
    <ConflictBar conflict={f.conflict} onReload={f.reloadFromDisk} onKeep={f.keepMine}
      onDiff={async () => {
        const disk = await f.diskText();
        setModal(<DiffModal title={t("conflict.diffTitle")} before={mine()} after={disk} onClose={close} note={t("conflict.diffNote")} />);
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

/** Horní lišta editoru souboru: jméno, přepínač režimu, stav, Smazat, Uložit. */
function EditorBar({ title, mode, onMode, modeBlocked, dirty, state, errors, canSave, onSave, onDelete }: {
  title: string; mode: "form" | "text"; onMode: (m: "form" | "text") => void; modeBlocked?: string;
  dirty: boolean; state: SaveState; errors: number; canSave: boolean; onSave: () => void; onDelete: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <h2 className="mr-auto font-mono text-lg font-semibold">{title}</h2>
      <Toggle label={t("code.mode")} value={mode} onChange={onMode}
        options={[{ key: "form", label: t("code.form"), disabled: modeBlocked }, { key: "text", label: <><CodeXml className="size-3.5" aria-hidden />{t("code.markdown")}</> }]} />
      <SaveNote dirty={dirty} state={state} errors={errors} />
      <button type="button" className={btn.secondary} onClick={onDelete}><Trash2 className="size-4" aria-hidden />{t("common.delete")}</button>
      <button type="button" className={btn.primary} onClick={onSave} disabled={!canSave} title="Ctrl+S">{t("common.save")}</button>
    </div>
  );
}

/** Smazání přes API: 422 = ochrana (používá ho scénář / agent), důvod z hlášky. */
async function deleteFile(url: string, etag: string): Promise<string | null> {
  try {
    await send("DELETE", url, { etag });
    return null;
  } catch (e) {
    const err = e as ApiError;
    return err.errors.map((x) => x.message).join("\n") || err.message;
  }
}

function DeleteDialog({ what, name, run, onDone, onCancel }: {
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
      {reason ? <p role="alert" className="font-mono text-xs whitespace-pre-wrap text-rose-400">{reason}</p> : <p>{t("delete.text")}</p>}
    </Modal>
  );
}

// --- agent -------------------------------------------------------------------------------------

interface AgentForm {
  fm: Obj;
  body: string;
}

const Chip = ({ children, onRemove, label }: { children: ReactNode; onRemove?: () => void; label?: string }) => (
  <span className="inline-flex items-center gap-1 rounded-full bg-zinc-900 px-2.5 py-0.5 font-mono text-[13px] text-zinc-200">
    {children}
    {onRemove && <button type="button" onClick={onRemove} aria-label={label} className="text-zinc-400 hover:text-zinc-100">×</button>}
  </span>
);

function AgentEditor({ project, name, onChanged }: { project: Project; name: string; onChanged: () => void }) {
  const path = `agents/${name}.md`;
  const url = `/projects/${enc(project.name)}/agents/${enc(name)}`;
  const [mode, setMode] = useState<"form" | "text">("form");
  const [deleting, setDeleting] = useState(false);
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
  const ui = useConflictUi(active, () => active.doc?.text ?? "");
  useLeaveGuard(form.dirty || text.dirty);
  const summary = project.agents.find((a) => a.name === name);
  const usedBy = project.links.scenario_agent.filter(([, ag]) => ag === name).map(([s]) => s);
  const errors = active.state.kind === "failed" || active.dirty || mode === "text" ? active.errors : summary?.errors ?? [];
  const save = async () => {
    if (await ui.save()) onChanged();
  };
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
    <div className="space-y-5" onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (active.dirty) void save();
      }
    }}>
      <EditorBar title={name} mode={mode} onMode={switchMode} dirty={active.dirty} state={active.state} errors={errors.length}
        modeBlocked={mode === "text" && text.errors.some((e) => e.line) ? t("code.fixYaml", { n: text.errors.find((e) => e.line)!.line! }) : undefined}
        canSave={active.dirty && !active.conflict && !(mode === "text" && (text.validating || text.errors.some((e) => e.line)))}
        onSave={() => void save()} onDelete={() => setDeleting(true)} />
      {ui.bar}
      {active.loadError && <ErrorText error={active.loadError} />}
      {!active.doc && !active.loadError && <Loading rows={5} />}
      {mode === "text" && text.doc && <YamlEditor text={text.text} onChange={text.setText} file={path} errors={text.errors} />}
      {mode === "form" && form.doc && form.value && (
        <AgentFields project={project} name={name} value={form.value} onChange={form.setValue} errors={errors} usedBy={usedBy} />
      )}
      {ui.modal}
      {deleting && form.doc && (
        <DeleteDialog what={t("delete.agent")} name={name} onCancel={() => setDeleting(false)}
          run={() => deleteFile(url, (active.doc ?? form.doc)!.etag)}
          onDone={() => (setDeleting(false), onChanged(), navigate(href(project.name, "agenti")))} />
      )}
    </div>
  );
}

function AgentFields({ project, name, value, onChange, errors, usedBy }: {
  project: Project; name: string; value: AgentForm; onChange: (v: AgentForm) => void; errors: ErrorItem[]; usedBy: string[];
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
    <div className="space-y-5">
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
      <FormField label={t("agent.skills")} errors={fe("skills")}>
        {(a) => (
          <div className="flex flex-wrap items-center gap-1.5">
            {skills.map((s) => <Chip key={s} label={t("agent.removeSkill", { name: s })} onRemove={() => setFm("skills", skills.filter((x) => x !== s))}>{s}</Chip>)}
            <select {...a} aria-label={t("agent.addSkill")} className={`${inputCls} w-auto`} value="" onChange={(e) => e.target.value && setFm("skills", [...skills, e.target.value])}>
              <option value="">+ {t("agent.addSkill")}</option>
              {project.skills.filter((s) => !skills.includes(s.name)).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </select>
          </div>
        )}
      </FormField>
      <FormField label={t("agent.mcp")} help={t("agent.mcpHelp")} errors={[...fe("mcp"), ...fe("tools")]}>
        {() => (
          <ul className="space-y-2">
            {project.mcp_servers.map((s) => {
              const allowed = !!s.agents?.includes(name);
              const on = mcp.includes(s.name);
              return (
                <li key={s.name} className={allowed || on ? "" : "text-zinc-500"}>
                  <label className="flex items-center gap-2 font-mono text-sm">
                    <input type="checkbox" checked={on} disabled={!allowed && !on} onChange={(e) => toggleServer(s.name, e.target.checked, s.tools)} />
                    {s.name}
                    {!allowed && <span className="font-sans text-[13px]">{t("agent.mcpNotAllowed")}</span>}
                  </label>
                  {on && (
                    <div className="mt-1 ml-6 flex flex-wrap gap-3">
                      {(s.tools ?? tools[s.name] ?? []).map((tool) => {
                        const cur = tools[s.name] ?? [];
                        return (
                          <label key={tool} className="flex items-center gap-1.5 font-mono text-[13px]">
                            <input type="checkbox" checked={cur.includes(tool)}
                              onChange={(e) => setFm("tools", { ...tools, [s.name]: e.target.checked ? [...cur, tool] : cur.filter((x) => x !== tool) })} />
                            {tool}
                          </label>
                        );
                      })}
                      {!s.tools && <span className="text-[13px] text-zinc-400">{t("agent.toolsFree")}</span>}
                    </div>
                  )}
                </li>
              );
            })}
            {!project.mcp_servers.length && <li className="text-sm text-zinc-500">–</li>}
          </ul>
        )}
      </FormField>
      <div className="grid grid-cols-3 gap-3">
        <FormField label="max_turns" required={needTurns} errors={fe("limits.max_turns")}
          help={needTurns ? t("agent.turnsRequired") : t("agent.turnsHelp")}>
          {(a) => (
            <input {...a} type="number" min={1} aria-required={needTurns}
              className={`${inputCls} font-mono ${needTurns && limits.max_turns == null ? "ring-2 ring-amber-400" : ""}`}
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
      <FormField label={t("agent.instructions")} errors={fe("body")} required>
        {(a) => <textarea {...a} rows={Math.min(24, Math.max(8, value.body.split("\n").length + 1))} className={`${inputCls} leading-6`}
          value={value.body} onChange={(e) => onChange({ ...value, body: e.target.value })} />}
      </FormField>
      <p className="text-sm text-zinc-400">
        {t("agent.usedBy")}{": "}
        {usedBy.length ? usedBy.map((s, i) => <span key={s}>{i > 0 && ", "}<a className="font-mono underline" href={href(project.name, "scenare", s)}>{s}</a></span>) : "–"}
      </p>
    </div>
  );
}

export function AgentsTab({ project, selected, onChanged }: { project: Project; selected?: string; onChanged: () => void }) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      <MasterDetail project={project} tab="agenti" items={project.agents} selected={selected} onNew={() => setCreating(true)}>
        {(name) => <AgentEditor key={name} project={project} name={name} onChanged={onChanged} />}
      </MasterDetail>
      {creating && (
        <NameDialog title={t("agenti.new")} taken={project.agents.map((a) => a.name)} onCancel={() => setCreating(false)}
          onSubmit={async (name) => {
            await send("POST", `/projects/${enc(project.name)}/agents`, { name });
            setCreating(false);
            onChanged();
            navigate(href(project.name, "agenti", name));
          }} />
      )}
    </>
  );
}

// --- skill -------------------------------------------------------------------------------------

function SkillEditor({ project, name, onChanged }: { project: Project; name: string; onChanged: () => void }) {
  const path = `skills/${name}/SKILL.md`;
  const url = `/projects/${enc(project.name)}/skills/${enc(name)}`;
  const text = useTextFile(project.name, path, url);
  const ui = useConflictUi(text, () => text.doc?.text ?? "");
  const [deleting, setDeleting] = useState(false);
  useLeaveGuard(text.dirty);
  const usedBy = project.links.agent_skill.filter(([, sk]) => sk === name).map(([a]) => a);
  const syntax = text.errors.find((e) => e.line);
  const save = async () => {
    if (await ui.save()) onChanged();
  };
  return (
    <div className="space-y-5" onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (text.dirty) void save();
      }
    }}>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="mr-auto font-mono text-lg font-semibold">{name}</h2>
        <SaveNote dirty={text.dirty} state={text.state} errors={text.errors.length} />
        <button type="button" className={btn.secondary} onClick={() => setDeleting(true)}><Trash2 className="size-4" aria-hidden />{t("common.delete")}</button>
        <button type="button" className={btn.primary} disabled={!text.dirty || !!text.conflict || text.validating || !!syntax} onClick={() => void save()}>
          {t("common.save")}
        </button>
      </div>
      {ui.bar}
      {text.loadError && <ErrorText error={text.loadError} />}
      {text.doc ? <YamlEditor text={text.text} onChange={text.setText} file={path} errors={text.errors} /> : !text.loadError && <Loading rows={5} />}
      <p className="text-sm text-zinc-400">
        {t("skill.usedBy")}{": "}
        {usedBy.length ? usedBy.map((a, i) => <span key={a}>{i > 0 && ", "}<a className="font-mono underline" href={href(project.name, "agenti", a)}>{a}</a></span>) : "–"}
      </p>
      {ui.modal}
      {deleting && text.doc && (
        <DeleteDialog what={t("delete.skill")} name={name} onCancel={() => setDeleting(false)} run={() => deleteFile(url, text.doc!.etag)}
          onDone={() => (setDeleting(false), onChanged(), navigate(href(project.name, "skilly")))} />
      )}
    </div>
  );
}

/** Nový SKILL.md: frontmatter jen se jménem a popisem (popis jako JSON řetězec = platný YAML skalár). */
export const skillTemplate = (name: string, description: string) =>
  `---\nname: ${name}\ndescription: ${JSON.stringify(description || name)}\n---\n${t("skill.templateBody")}\n`;

export function SkillsTab({ project, selected, onChanged }: { project: Project; selected?: string; onChanged: () => void }) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      <MasterDetail project={project} tab="skilly" items={project.skills} selected={selected} onNew={() => setCreating(true)}>
        {(name) => <SkillEditor key={name} project={project} name={name} onChanged={onChanged} />}
      </MasterDetail>
      {creating && (
        <NameDialog title={t("skilly.new")} withDescription taken={project.skills.map((s) => s.name)} onCancel={() => setCreating(false)}
          onSubmit={async (name, description) => {
            await send("PUT", `/projects/${enc(project.name)}/skills/${enc(name)}`, { etag: null, text: skillTemplate(name, description) });
            setCreating(false);
            onChanged();
            navigate(href(project.name, "skilly", name));
          }} />
      )}
    </>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-baseline gap-4 text-sm">
      <div className="text-[13px] font-semibold text-zinc-400">{label}</div>
      <div>{children}</div>
    </div>
  );
}
export { Row };
