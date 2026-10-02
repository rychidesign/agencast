// §2.3–2.4 Scenario editor: column of cards + panel (Form), or YAML across the full width (§4.5).
// Form keeps the in-progress tree (scenarioDraft.ts), YAML the in-progress text (textfile.ts); both go to disk
// only via the Save button / Ctrl+S. Form → YAML converts the in-progress tree to text via `render`;
// YAML → Form converts the unsaved text via `render` without writing (api-findings.md item 26).
import { CodeXml, Play, Save } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { stepLines } from "../components/yaml";
import { Modal, NameDialog, slugify, type ModalAction } from "../components/form";
import { RunPanel } from "../components/RunPanel";
import { Connector, HeaderCard, onColumnKey, StepList, uidOf, type EditCtx, type ListCtx } from "../components/StepCards";
import { HeaderPanel, StepPanel } from "../components/StepPanel";
import { ConflictBar, DiffModal, YamlEditor } from "../components/YamlEditor";
import { PageHeader } from "../components/PageHeader";
import { ErrorText, Loading, SheetContext, Toggle, btn, useMedia, type MenuItem } from "../components/ui";
import {
  adopt, blankStep, findStep, flat, insert, move, numbered, remove, renameStep, shift, update, type Draft, type WStep,
} from "../edit";
import { t } from "../i18n";
import { href, navigate, setQuery, useLocation } from "../router";
import { useScenarioDraft } from "../scenarioDraft";
import { readBy } from "../steps";
import { draftKey, syntaxError, useLeaveGuard, useTextFile, writeDraft } from "../textfile";
import type { ErrorItem, Project, Step, StepType } from "../types";
import { DeleteDialog, deleteFile, SaveNote } from "./Agents";
import { runCommand } from "./Scenarios";

/** Selection of the header card in `?step=` (a step id may not start with `_`, so there is no collision). */
export const HEADER_KEY = "_header";

export function errorsByStep(errors: ErrorItem[]): Map<string, ErrorItem[]> {
  const m = new Map<string, ErrorItem[]>();
  for (const e of errors) if (e.step) m.set(e.step, [...(m.get(e.step) ?? []), e]);
  return m;
}

/** Scrolls the selected card into view (clicking a "reads from" chip jumps to the card). */
export function useScrollToCard(key: string | undefined) {
  useEffect(() => {
    if (!key) return;
    const card = document.querySelector(`[data-step-card="${CSS.escape(key)}"]`);
    const rect = card?.getBoundingClientRect();
    if (rect && (rect.top < 0 || rect.bottom > window.innerHeight)) card?.scrollIntoView?.({
      block: "nearest", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "auto" : "smooth",
    });
  }, [key]);
}

const focusCard = (id: string) =>
  requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-step-card="${CSS.escape(id)}"]`)?.focus());

/** Esc closes the panel and returns focus to the card (§6). */
export function closeOnEsc(selected: string | undefined) {
  return (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !selected || e.defaultPrevented) return;
    setQuery({ step: undefined });
    focusCard(selected === HEADER_KEY ? "" : selected);
  };
}

export function PanelSlot({ children, wide = false }: { children: ReactNode; /** Step panel in a run (design 12: 520 px). */ wide?: boolean }) {
  // From 1280 px a drawer over the full height of the window on the right edge (over the header strip too), with a large blurred
  // shadow; it reports its width in `--drawer-w`, by which the Shell narrows the page, so the column and the header actions stay
  // beside it. Not modal: the cards stay clickable. Narrower = full-screen sheet (PanelShell).
  const sheet = useMedia("(max-width: 1279px)");
  const width = wide ? 520 : 440;
  useLayoutEffect(() => {
    if (sheet) return;
    const root = document.documentElement.style;
    root.setProperty("--drawer-w", `${width}px`);
    return () => void root.removeProperty("--drawer-w");
  }, [sheet, width]);
  if (sheet) return <SheetContext.Provider value>{children}</SheetContext.Provider>;
  return (
    <div style={{ width }} className="drawer-enter drawer-shadow fixed inset-y-0 right-0 z-40 flex flex-col">
      {children}
    </div>
  );
}

type Pending =
  | { kind: "delete"; step: WStep; readers: string[]; nested: number }
  | { kind: "rename"; step: WStep; to: string; readers: string[] }
  | { kind: "retype"; step: WStep; type: StepType }
  | { kind: "mode"; to: "form" | "yaml" }
  | { kind: "overwrite" }
  | { kind: "branch"; step: WStep }
  | { kind: "diff"; before: string; after: string };

export function ScenarioPage({ project, scenario }: { project: string; scenario: string }) {
  const { query } = useLocation();
  const selected = query.get("step") ?? undefined;
  const yaml = query.get("mode") === "yaml";
  const trail = query.get("from") ?? "";
  const [running, setRunning] = useState(false);
  const [cut, setCut] = useState<string>();
  const [pending, setPending] = useState<Pending>();
  const [renaming, setRenaming] = useState(false);
  const [renameGuard, setRenameGuard] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [caretLine, setCaretLine] = useState(1);
  const proj = useApi<Project>(`/projects/${enc(project)}`);
  const form = useScenarioDraft(project, scenario, !yaml);
  const file = `scenarios/${scenario}.yaml`;
  const noticeKey = `agencast.rename.${project}/${scenario}`;
  const [renamedFiles] = useState(() => {
    const files = sessionStorage.getItem(noticeKey);
    if (!files) return [];
    sessionStorage.removeItem(noticeKey);
    return files.split("\n");
  });
  const text = useTextFile(project, yaml ? file : null);
  useLeaveGuard(form.dirty || text.dirty);
  const work = form.work;
  const steps = useMemo(() => (work ? numbered(work.steps) : []), [work]);
  const all = useMemo(() => flat(steps), [steps]);
  const fileErrors = form.errors.filter((e) => !e.file || e.file === file);
  const byStep = useMemo(() => errorsByStep(fileErrors), [fileErrors]);
  useScrollToCard(yaml ? undefined : selected);

  const select = (key: string) => setQuery({ step: key === selected ? undefined : key });
  const step = all.find((x) => x.id === selected);
  const setSteps = (fn: (s: WStep[]) => WStep[], coalesce?: string) => form.change((d) => ({ ...d, steps: fn(d.steps) }), coalesce);

  // --- column actions -------------------------------------------------------------------------
  const doRemove = (s: WStep) => {
    setSteps((l) => remove(l, s.uid));
    if (selected === s.id) setQuery({ step: undefined });
    setAnnounce(t("edit.removed", { id: s.id }));
  };
  const edit: EditCtx = {
    add: (at, pick) => {
      if (!work) return;
      if (pick === "paste") {
        if (!cut) return;
        setSteps((l) => move(l, cut, at));
        const id = findStep(work.steps, cut)?.id;
        setCut(undefined);
        if (id) setAnnounce(t("edit.pasted", { id }));
        return;
      }
      const s = blankStep(work.steps, pick);
      setSteps((l) => insert(l, at, s));
      setQuery({ step: s.id });
      setAnnounce(t("edit.added", { id: s.id }));
    },
    remove: (s) => {
      const w = s as WStep;
      const readers = readBy(all, w.id).filter((id) => id !== w.id);
      const nested = flat([w]).length - 1;
      if (readers.length || nested) setPending({ kind: "delete", step: w, readers, nested });
      else doRemove(w);
    },
    shift: (s, d) => {
      setSteps((l) => shift(l, uidOf(s), d));
      focusCard(s.id);
    },
    cut: (s) => {
      setCut(uidOf(s));
      setAnnounce(t("edit.cutDone", { id: s.id }));
    },
    cut_: cut ? all.find((s) => s.uid === cut) : undefined,
    addBranch: (s) => setPending({ kind: "branch", step: s as WStep }),
    addOutput:
      work && Object.keys(work.header.outputs ?? {}).length && !work.steps.some((s) => s.type === "output")
        ? () => {
          const s = blankStep(work.steps, "output");
          const last = work.steps[work.steps.length - 1];
          setSteps((l) => insert(l, last ? { after: last.uid } : { list: { parent: null, key: [] } }, s));
          setQuery({ step: s.id });
        }
        : undefined,
  };
  const ctx: ListCtx = { project, selected, onSelect: select, errors: byStep, edit, scenario, trail };

  const doRename = (s: WStep, to: string) => {
    setSteps((l) => renameStep(l, s.uid, to));
    if (selected === s.id) setQuery({ step: to });
    setAnnounce(t("edit.renamed", { id: s.id, to }));
  };
  /** Rename: a read step asks once and rewrites the readers' references (batch `rename_step`, `rename_refs`). */
  const rename = (s: WStep, to: string) => {
    const readers = readBy(all, s.id).filter((id) => id !== s.id);
    if (readers.length) setPending({ kind: "rename", step: s, to, readers });
    else doRename(s, to);
  };
  const retype = (s: WStep, type: StepType) => {
    setSteps((l) => update(l, s.uid, (x) => blankStep(l, type, { id: x.id, when: x.when, uid: x.uid })));
    setAnnounce(t("edit.retyped", { id: s.id, type }));
  };
  /** Filled-in fields that a type change would discard. */
  const filled = (s: WStep) => {
    const body = s.type ? s.fields[s.type] : undefined;
    const rest = Object.keys(s.fields).filter((k) => k !== s.type);
    const hasBody = body !== undefined && body !== "" && JSON.stringify(body) !== "{}" && !(s.type === "switch" && !(body as { value?: string }).value);
    return hasBody || rest.length > 0 || flat([s]).length > 1;
  };

  // --- saving and modes -------------------------------------------------------------------------
  const syntax = syntaxError(text.errors);
  const saveForm = async () => {
    if (form.overwrite) return setPending({ kind: "overwrite" });
    await form.save();
  };
  const saveYaml = async () => {
    if (text.overwrite) return setPending({ kind: "overwrite" });
    if (await text.save()) void form.reload();
  };
  const save = () => (yaml ? saveYaml() : saveForm());
  const requestRename = () => (yaml ? text.dirty : form.dirty) ? setRenameGuard(true) : setRenaming(true);
  const discardForRename = () => {
    if (yaml) text.discard();
    else void form.reloadFromDisk();
    setRenameGuard(false);
    setRenaming(true);
  };
  const saveForRename = async () => {
    const ok = yaml ? await text.save() : await form.save();
    if (!ok) return;
    if (yaml) void form.reload();
    setRenameGuard(false);
    setRenaming(true);
  };
  const fileEtag = yaml ? text.doc?.etag : form.server?.sc.etag;
  const renameScenario = async (newName: string) => {
    let result: { changed: string[] };
    try {
      result = await send("POST", `/projects/${enc(project)}/scenarios/${enc(scenario)}/rename`, { etag: fileEtag, name: newName });
    } catch (e) {
      const err = e as ApiError;
      throw new Error(err.errors.map((x) => x.message).join("\n") || err.message);
    }
    localStorage.removeItem(draftKey(project, file, "form"));
    localStorage.removeItem(draftKey(project, file));
    if (result.changed.length > 1) sessionStorage.setItem(`agencast.rename.${project}/${newName}`, result.changed.join("\n"));
    proj.reload();
    navigate(href(project, "scenarios", newName, { step: selected, from: trail || undefined }));
  };
  const canSave = yaml ? text.dirty && !syntax && !text.validating && !text.errors.length && !text.conflict : form.dirty && !form.conflict;

  const switchMode = async (to: "form" | "yaml") => {
    if ((to === "yaml") === yaml) return;
    if (to === "form" && syntax) return text.dirty && setPending({ kind: "mode", to });
    if (to === "yaml" && form.dirty) {
      // in-progress tree → text via `render`; the text is then held by YAML mode as unsaved (including the version etag)
      const r = await form.renderText().catch(() => undefined);
      if (!r) return setPending({ kind: "mode", to });
      writeDraft(draftKey(project, file), { etag: r.etag, value: r.text });
      await form.reloadFromDisk();
      return goMode(to);
    }
    if (to === "form" && text.dirty) {
      const r = await send<{ tree: Step[]; errors: ErrorItem[] }>(
        "POST", `/projects/${enc(project)}/scenarios/${enc(scenario)}/render`, { text: text.text },
      ).catch(() => undefined);
      if (!r) return;
      try { await form.setRendered(adopt(r.tree), r.errors); } catch { return; }
      text.discard();
      return goMode(to, false);
    }
    goMode(to);
  };
  const goMode = (to: "form" | "yaml", reload = true) => {
    if (to === "form") {
      const id = stepAtLine(text.text, caretLine);
      if (reload) void form.reload();
      setQuery({ mode: undefined, step: id ?? selected });
    } else setQuery({ mode: "yaml" });
  };

  const onKey = (e: KeyboardEvent) => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (canSave) void save();
    } else if (mod && e.key.toLowerCase() === "z" && !yaml && !(e.target as HTMLElement).matches("input, textarea")) {
      e.preventDefault();
      form.undo();
    } else closeOnEsc(selected)(e);
  };

  const errCount = yaml ? text.errors.length : fileErrors.length;
  const jump = () => {
    const first = fileErrors.find((e) => e.step);
    if (!yaml) setQuery({ step: first?.step ?? HEADER_KEY });
  };
  const conflict = yaml ? text.conflict : form.conflict;
  const showDiff = async () => {
    const disk = await (yaml ? text.diskText() : form.diskText());
    setPending({ kind: "diff", before: yaml ? text.text : form.base?.text ?? "", after: disk });
  };

  const p = proj.data;
  const summary = p?.scenarios.find((s) => s.name === scenario);
  const menu: MenuItem[] = [
    ...(!yaml ? [{ label: t("edit.undo"), shortcut: "Ctrl+Z", onSelect: form.undo, disabled: form.canUndo ? undefined : t("edit.nothingToUndo") }] : []),
    ...(p && summary ? [{ label: t("scenarios.copyRun"), onSelect: () => void navigator.clipboard.writeText(runCommand(p.root, summary)) }] : []),
    { label: t("editor.runs"), onSelect: () => navigate(href(project, "runs", undefined, { scenario })) },
    // without the file etag (still loading) rename and delete are not possible
    ...(fileEtag ? [
      { label: t("rename.button"), onSelect: requestRename },
      { label: t("common.delete"), onSelect: () => setDeleting(true), danger: true },
    ] : []),
  ];
  // nonexistent scenario: only a title and an error, no Save, toggle or "Saved ✓"
  const missing = form.loadError?.status === 404;
  const back = { href: href(project, "scenarios"), label: t("project.tab.scenarios") };
  return (
    <div onKeyDown={onKey}>
      {missing ? <PageHeader back={back} title={<span className="font-mono">{scenario}</span>} /> : <PageHeader sticky
        back={back} trail={trail && <Trail project={project} trail={trail} />}
        title={<span className="font-mono md:text-[27px] md:leading-[41px]">{scenario}</span>}
        description={work?.header.description && <span className="text-[13px] leading-5">{work.header.description}</span>}
        actions={<>
          <button type="button" className={btn.primary} onClick={() => (setRunning(true), setQuery({ step: undefined }))} disabled={!p || !work}>
            <Play className="size-4" aria-hidden />{t("runForm.open")}
          </button>
          <button type="button" className={`${btn.secondary} max-md:hidden`} onClick={() => void save()} disabled={!canSave} title="Ctrl+S">
            <Save className="size-4" aria-hidden />{t("common.save")}
          </button>
        </>}
        compact={[{ label: t("common.save"), onSelect: () => void save(), disabled: canSave ? undefined : t("edit.nothingToSave") }]}
        menu={menu}>
        <Toggle label={t("code.mode")} value={yaml ? "yaml" : "form"} onChange={(m) => void switchMode(m)}
          options={[
            { key: "form", label: t("code.form"), disabled: syntax && !text.dirty ? t("code.fixYaml", { n: syntax.line ?? 0 }) : undefined },
            { key: "yaml", label: <><CodeXml className="size-3.5" aria-hidden />YAML</> },
          ]} />
        <SaveNote dirty={yaml ? text.dirty : form.dirty} errors={errCount} state={yaml ? text.state : form.state} onJump={jump} />
        {conflict && (
          <ConflictBar inHeader conflict={conflict} onDiff={() => void showDiff()}
            onReload={yaml ? text.reloadFromDisk : form.reloadFromDisk}
            onKeep={() => void (yaml ? text.keepMine() : form.keepMine())} />
        )}
      </PageHeader>}
      <p className="sr-only" aria-live="polite" data-testid="announce">{announce}</p>
      {renamedFiles.length > 1 && <p role="status" className="pb-2 text-sm text-fg-muted">
        {t("rename.changed", { files: renamedFiles.join(", ") })}
      </p>}
      <div>
        {form.loadError && form.loadError.status !== 0 && <ErrorText error={form.loadError} />}
        {!work && !form.loadError && <div className="mx-auto max-w-[676px]"><Loading rows={4} pill /></div>}
        {yaml && (
          text.doc ? (
            <div>
              <YamlEditor text={text.text} onChange={text.setText} file={file} errors={text.errors} onCaretLine={setCaretLine}
                focus={selected && selected !== HEADER_KEY ? stepLines(text.text, selected) : undefined} />
            </div>
          ) : text.loadError ? <ErrorText error={text.loadError} /> : <Loading rows={8} />
        )}
        {work && !yaml && (
          <div className="flex justify-center gap-7">
            <section className="w-full max-w-[676px] min-w-0 md:pointer-coarse:pr-12" aria-label={t("step.list")} onKeyDown={onColumnKey}>
              <HeaderCard inputs={work.header.inputs} outputs={work.header.outputs} selected={selected === HEADER_KEY} onSelect={() => select(HEADER_KEY)} />
              <Connector ctx={ctx} at={{ list: { parent: null, key: [] } }} />
              <StepList steps={steps} ctx={ctx} />
            </section>
            {running && p && (
              <PanelSlot>
                <RunPanel project={p} scenario={scenario} inputs={form.server?.draft.header.inputs ?? null} errors={fileErrors} dirty={form.dirty} onClose={() => setRunning(false)} />
              </PanelSlot>
            )}
            {!running && selected === HEADER_KEY && (
              <PanelSlot>
                <HeaderPanel name={scenario} header={work.header} errors={fileErrors.filter((e) => !e.step)} onClose={() => setQuery({ step: undefined })}
                  change={(fn, key) => form.change((d: Draft) => ({ ...d, header: fn(d.header) }), key && `h:${key}`)} />
              </PanelSlot>
            )}
            {!running && step && p && (
              <PanelSlot>
                <StepPanel key={step.uid} step={step} steps={steps} header={work.header} project={p} scenario={scenario}
                  errors={byStep.get(step.id) ?? []} onClose={() => setQuery({ step: undefined })} onSelect={(id) => setQuery({ step: id })}
                  edit={{
                    change: (fn, key) => setSteps((l) => update(l, step.uid, fn), key && `${step.uid}:${key}`),
                    retype: (type) => (filled(step) ? setPending({ kind: "retype", step, type }) : retype(step, type)),
                    remove: () => edit.remove(step),
                    rename: (to) => rename(step, to),
                  }} />
              </PanelSlot>
            )}
          </div>
        )}
      </div>
      {pending && <PendingModal pending={pending} close={() => setPending(undefined)} actions={{
        remove: doRemove, retype, rename: doRename,
        mode: async (to, saveFirst) => {
          if (saveFirst && !(await (yaml ? text.save() : form.save()))) return;
          if (!saveFirst) {
            if (yaml) text.discard();
            else await form.reloadFromDisk();
          }
          goMode(to);
        },
        overwrite: async () => {
          if (yaml) {
            if (await text.save()) void form.reload();
          } else await form.save();
        },
        branch: (s, name) => setSteps((l) => update(l, s.uid, (x) =>
          x.type === "parallel" ? { ...x, branches: { ...x.branches, [name]: [] } } : { ...x, cases: { ...x.cases, [name]: [] } })),
      }} />}
      {renameGuard && <Modal title={t("mode.title")} onCancel={() => setRenameGuard(false)} actions={[
        { label: t("mode.save"), primary: true, onSelect: () => void saveForRename() },
        { label: t("mode.discard"), danger: true, onSelect: discardForRename },
      ]}><p>{t(yaml ? "mode.yamlDirty" : "mode.formDirty")}</p></Modal>}
      {renaming && fileEtag && <NameDialog title={t("rename.title", { what: t("delete.scenario"), name: scenario })} initialName={scenario}
        submitLabel={t("rename.confirm")} pattern={/^[a-z][a-z0-9-]*$/}
        taken={(proj.data?.scenarios ?? []).map((s) => s.name).filter((n) => n !== scenario)}
        onCancel={() => setRenaming(false)} onSubmit={(newName) => renameScenario(newName)} />}
      {deleting && fileEtag && <DeleteDialog what={t("delete.scenario")} name={scenario} onCancel={() => setDeleting(false)}
        run={() => deleteFile(`/projects/${enc(project)}/scenarios/${enc(scenario)}`, fileEtag)}
        onDone={() => {
          localStorage.removeItem(draftKey(project, file, "form"));
          localStorage.removeItem(draftKey(project, file));
          proj.reload();
          navigate(href(project, "scenarios"));
        }} />}
    </div>
  );
}

/** Breadcrumbs `ig-post › draft › ig-text` after "open" on a `call` (§4.7); `?from=ig-post:draft,ig-text:x`.
  *  The scenario name leads back to its `call` card. */
export function Trail({ project, trail }: { project: string; trail: string }) {
  const crumbs = trail ? trail.split(",").map((c) => c.split(":") as [string, string]) : [];
  if (!crumbs.length) return null;
  return (
    <nav aria-label={t("editor.trail")} className="font-mono text-sm text-fg-muted">
      {crumbs.map(([sc, step], i) => (
        <span key={i}>
          <a className="hover:text-fg hover:underline" href={href(project, "scenarios", sc, { step, from: trail.split(",").slice(0, i).join(",") })}>{sc}</a>
          {" › "}{step}{" › "}
        </span>
      ))}
    </nav>
  );
}

/** YAML → Form: the step the cursor was in (the nearest `- id:` above the line). */
export function stepAtLine(text: string, line: number): string | undefined {
  const lines = text.split("\n").slice(0, line).reverse();
  for (const l of lines) {
    const m = /^\s*-\s+id:\s*["']?([a-z][a-z0-9_]*)/.exec(l);
    if (m) return m[1];
  }
  return undefined;
}

function PendingModal({ pending, close, actions }: {
  pending: Pending; close: () => void;
  actions: {
    remove: (s: WStep) => void; retype: (s: WStep, type: StepType) => void; rename: (s: WStep, to: string) => void;
    mode: (to: "form" | "yaml", saveFirst: boolean) => Promise<void>; overwrite: () => Promise<void>;
    branch: (s: WStep, name: string) => void;
  };
}) {
  const run = (fn: () => unknown): ModalAction["onSelect"] => () => {
    close();
    void fn();
  };
  switch (pending.kind) {
    case "delete": {
      const s = pending.step;
      return (
        <Modal title={t("edit.deleteTitle", { id: s.id })} onCancel={close}
          actions={[{ label: t("edit.deleteAnyway"), danger: true, onSelect: run(() => actions.remove(s)) }]}>
          {pending.readers.length > 0 && <p>{t("edit.deleteReaders", { id: s.id, readers: pending.readers.join(", ") })}</p>}
          {pending.nested > 0 && <p>{t("edit.deleteNested", { n: pending.nested })}</p>}
        </Modal>
      );
    }
    case "rename":
      return (
        <Modal title={t("edit.renameTitle", { n: pending.readers.length })} onCancel={close}
          actions={[{ label: t("edit.renameRefs"), primary: true, onSelect: run(() => actions.rename(pending.step, pending.to)) }]}>
          <p>{t("edit.renameText", { id: pending.step.id, to: pending.to })}</p>
          <ul className="list-inside list-disc font-mono">{pending.readers.map((r) => <li key={r}>{r}</li>)}</ul>
        </Modal>
      );
    case "retype":
      return (
        <Modal title={t("edit.retypeTitle", { id: pending.step.id, type: pending.type })} onCancel={close}
          actions={[{ label: t("edit.retype"), danger: true, onSelect: run(() => actions.retype(pending.step, pending.type)) }]}>
          <p>{t("edit.retypeText")}</p>
        </Modal>
      );
    case "mode":
      return (
        <Modal title={t("mode.title")} onCancel={close} actions={[
          { label: t("mode.save"), primary: true, onSelect: run(() => actions.mode(pending.to, true)) },
          { label: t("mode.discard"), danger: true, onSelect: run(() => actions.mode(pending.to, false)) },
        ]}>
          <p>{t(pending.to === "yaml" ? "mode.formDirty" : "mode.yamlDirty")}</p>
        </Modal>
      );
    case "overwrite":
      return (
        <Modal title={t("conflict.overwriteTitle")} onCancel={close}
          actions={[{ label: t("conflict.overwrite"), danger: true, onSelect: run(actions.overwrite) }]}>
          <p>{t("conflict.overwriteText")}</p>
        </Modal>
      );
    case "branch": {
      const s = pending.step;
      const taken = Object.keys((s.type === "parallel" ? s.branches : s.cases) ?? {});
      return (
        <NameDialog title={t(s.type === "parallel" ? "edit.addBranch" : "edit.addCase")} taken={taken} onCancel={close}
          pattern={s.type === "parallel" ? /^[a-z0-9_]+$/ : /^[^\s/][^/]*$/}
          normalize={s.type === "parallel" ? (x) => slugify(x, "_", false) : null /* case = the value to match, leave as is */}
          onSubmit={(name) => (close(), actions.branch(s, name))} />
      );
    }
    case "diff":
      return <DiffModal title={t("conflict.diffTitle")} before={pending.before} after={pending.after} onClose={close} note={t("conflict.diffNote")} />;
  }
}
