// Editační prvky (§3 inventář): pole se štítkem, výraz/šablona s našeptávačem, JSON, modál rozhodnutí.
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type KeyboardEvent } from "react";
import { Braces, Check, CircleX, Plus, X } from "lucide-react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { btn, trapTab, usePopoverPosition } from "./ui";

const selectArrow = "[&:is(select)]:appearance-none [&:is(select)]:bg-[linear-gradient(45deg,transparent_50%,var(--color-fg-muted)_50%),linear-gradient(135deg,var(--color-fg-muted)_50%,transparent_50%)] [&:is(select)]:bg-[size:8px_8px] [&:is(select)]:bg-[position:calc(100%-25px)_55%,calc(100%-17px)_55%] [&:is(select)]:bg-no-repeat [&:is(select)]:pr-10";
/** Pole (návrh `V3 / TextInput`, změřeno z .pen): 44 px, `nested`, r6, v klidu bez rámečku; fokus ring 2 `accent`
 *  bez odsazení, neplatné ring 2 `error`. */
export const inputCls =
  `w-full min-h-11 rounded-[6px] bg-nested px-3 py-2 text-sm text-fg placeholder:text-fg-muted focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-0 aria-invalid:ring-2 aria-invalid:ring-error aria-invalid:focus:ring-error disabled:opacity-50 pointer-coarse:text-base [&:is(textarea)]:p-3 ${selectArrow}`;
const mono = "font-mono text-[13px]";

/** Vlastnosti pole od `FormField`; `label` jen u `boxed` (štítek v toolbaru `CodeBox`). */
export type A11y = { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean; label?: ReactNode };

/** Pole se štítkem nad sebou (§6): `aria-describedby` na nápovědu i chybu. `boxed` = štítek kreslí pole samo
 *  (víceřádkový `CodeInput`, `JsonInput`). */
export function FormField({ label, help, errors = [], required, children, action, boxed = false }: {
  label: string; help?: ReactNode; errors?: (ErrorItem | string)[]; required?: boolean; action?: ReactNode; boxed?: boolean;
  children: (a11y: A11y) => ReactNode;
}) {
  const id = useId();
  const described = [help && `${id}-help`, errors.length && `${id}-err`].filter(Boolean).join(" ") || undefined;
  const labelEl = (
    <label htmlFor={id} className="text-[13px] font-medium text-fg-secondary">
      {label}{required && <span className="text-fg-muted"> *</span>}
    </label>
  );
  return (
    <div className="space-y-2">
      {!boxed && (
        <div className="flex items-center justify-between gap-2">
          {labelEl}
          {action}
        </div>
      )}
      {children({ id, "aria-describedby": described, "aria-invalid": errors.length > 0 || undefined, ...(boxed && { label: labelEl }) })}
      {help && <p id={`${id}-help`} className="text-xs text-fg-muted">{help}</p>}
      {errors.length > 0 && (
        <div id={`${id}-err`} className="space-y-1">
          {errors.map((e, i) => (
            <p key={i} className="font-mono text-xs whitespace-pre-wrap text-error">{typeof e === "string" ? e : e.message}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/** „+ Přidat …“ vpravo od štítku sekce: sekundární tlačítko (návrh 09, změřeno z .pen). */
export const AddPill = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <button type="button" onClick={onClick} className={btn.secondary}>
    <Plus className="size-4" aria-hidden />{label}
  </button>
);

// --- výraz a šablona s našeptávačem -------------------------------------------------------

/** Slovo před kurzorem, které se doplňuje (`steps.co`), nebo null (v šabloně jen uvnitř `{{ }}`). */
export function tokenAt(text: string, caret: number, template: boolean): string | null {
  const before = text.slice(0, caret);
  if (template && before.lastIndexOf("{{") <= before.lastIndexOf("}}")) return null;
  const m = /[A-Za-z_][\w.]*$/.exec(before);
  return m && /^(i|s)/.test(m[0]) ? m[0] : null;
}

/** `ExprInput` / `TemplateInput` (§3): mono pole; `candidates` = `inputs.x`, `steps.<id>.<pole>` z kroků nad. */
export function CodeInput({ value, onChange, candidates, template = false, multiline = false, a11y: { label, ...a11y }, placeholder }: {
  value: string; onChange: (v: string) => void; candidates: string[]; template?: boolean; multiline?: boolean;
  a11y: A11y; placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement & HTMLInputElement>(null);
  const caretAt = useRef<number | null>(null);
  const selection = useRef<{ start: number; end: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const suggestionsRef = useRef<HTMLUListElement>(null);
  const variableRef = useRef<HTMLButtonElement>(null);
  const [token, setToken] = useState<string | null>(null);
  // kurzor za doplněnou hodnotu hned po jejím vykreslení (rAF by předběhlo další úhoz)
  useLayoutEffect(() => {
    if (caretAt.current == null) return;
    ref.current?.setSelectionRange(caretAt.current, caretAt.current);
    caretAt.current = null;
  }, [value]);
  const [active, setActive] = useState(0);
  const [variablesOpen, setVariablesOpen] = useState(false);
  const [variableActive, setVariableActive] = useState(0);
  const listId = `${a11y.id}-list`;
  const menuId = `${a11y.id}-variables`;
  const matches = token ? candidates.filter((c) => c.startsWith(token) && c !== token).slice(0, 8) : [];
  const open = matches.length > 0;
  usePopoverPosition(open, suggestionsRef, ref, "left", true, matches.length);
  usePopoverPosition(variablesOpen, menu, variableRef);
  const variableGroups = [...new Set(candidates.map((c) => c.startsWith("inputs.") ? "inputs" : `steps.${c.split(".")[1]}`))]
    .map((key) => ({
      label: key === "inputs" ? t("form.variables.inputs") : t("form.variables.step", { id: key.slice("steps.".length) }),
      items: candidates.filter((c) => key === "inputs" ? c.startsWith("inputs.") : c === key || c.startsWith(`${key}.`)),
    }));

  useEffect(() => {
    if (variablesOpen) menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]")[variableActive]?.focus();
  }, [variablesOpen, variableActive]);
  useEffect(() => {
    if (!variablesOpen) return;
    const close = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setVariablesOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [variablesOpen]);

  const refresh = (text: string, caret: number | null) => {
    setToken(caret == null ? null : tokenAt(text, caret, template));
    setActive(0);
  };
  const accept = (c: string) => {
    const el = ref.current!;
    const caret = el.selectionStart ?? value.length;
    const start = caret - (token?.length ?? 0);
    const next = value.slice(0, start) + c + value.slice(caret);
    caretAt.current = start + c.length;
    onChange(next);
    setToken(null);
  };
  const rememberSelection = (el: HTMLInputElement | HTMLTextAreaElement) => {
    if (el.selectionStart != null && el.selectionEnd != null) selection.current = { start: el.selectionStart, end: el.selectionEnd };
  };
  const insertVariable = (candidate: string) => {
    const start = Math.min(selection.current?.start ?? value.length, value.length);
    const end = Math.min(selection.current?.end ?? start, value.length);
    const before = value.slice(0, start);
    const insideTemplate = template && before.lastIndexOf("{{") > before.lastIndexOf("}}");
    const inserted = template && !insideTemplate ? `{{ ${candidate} }}` : candidate;
    const next = before + inserted + value.slice(end);
    caretAt.current = start + inserted.length;
    selection.current = { start: caretAt.current, end: caretAt.current };
    onChange(next);
    setToken(null);
    setVariablesOpen(false);
    ref.current?.focus();
  };
  const onVariableMenuKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setVariableActive((i) => (i + (e.key === "ArrowDown" ? 1 : candidates.length - 1)) % candidates.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = candidates[variableActive];
      if (item) insertVariable(item);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setVariablesOpen(false);
      ref.current?.focus();
    }
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.ctrlKey && e.key === " " && candidates.length) {
      e.preventDefault();
      setVariableActive(0);
      setVariablesOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a + (e.key === "ArrowDown" ? 1 : matches.length - 1)) % matches.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      accept(matches[active]);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      setToken(null);
    }
  };
  const props = {
    ref, value, placeholder, ...a11y,
    role: "combobox", "aria-expanded": open, "aria-controls": listId, "aria-autocomplete": "list" as const,
    "aria-activedescendant": open ? `${listId}-${active}` : undefined,
    className: `${inputCls} ${mono}`, spellCheck: false,
    onKeyDown: onKey,
    onSelect: (e: React.SyntheticEvent<HTMLInputElement & HTMLTextAreaElement>) => rememberSelection(e.currentTarget),
    onKeyUp: (e: React.KeyboardEvent<HTMLInputElement & HTMLTextAreaElement>) => rememberSelection(e.currentTarget),
    onClick: (e: React.MouseEvent<HTMLInputElement & HTMLTextAreaElement>) => rememberSelection(e.currentTarget),
    onBlur: (e: React.FocusEvent<HTMLInputElement & HTMLTextAreaElement>) => {
      rememberSelection(e.currentTarget);
      setTimeout(() => setToken(null), 150);
    },
    onChange: (e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => {
      onChange(e.target.value);
      rememberSelection(e.target);
      refresh(e.target.value, e.target.selectionStart);
    },
  };
  const variableButton = (
    <button
      ref={variableRef} type="button" className="grid size-11 shrink-0 place-items-center text-variable hover:brightness-125 disabled:cursor-not-allowed disabled:opacity-40 [&>svg]:size-[18px]"
      aria-label={t("form.variables.insert")} title={candidates.length ? t("form.variables.insert") : t("form.variables.none")}
      aria-haspopup="menu" aria-expanded={variablesOpen} aria-controls={menuId} disabled={!candidates.length}
      onClick={() => (setVariableActive(0), setVariablesOpen((isOpen) => !isOpen))}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setVariableActive(0);
          setVariablesOpen((isOpen) => !isOpen);
        } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !variablesOpen) {
          e.preventDefault();
          setVariableActive(0);
          setVariablesOpen(true);
        }
      }}
    >
      <Braces aria-hidden />
    </button>
  );
  const suggestions = open && (
    <ul ref={suggestionsRef} id={listId} role="listbox" className="popover fixed z-[60] overflow-y-auto p-2">
      {matches.map((c, i) => (
        <li key={c} id={`${listId}-${i}`} role="option" aria-selected={i === active}
          onMouseDown={(e) => (e.preventDefault(), accept(c))}
          className={`flex h-10 cursor-pointer items-center rounded-[7px] px-3 text-variable ${mono} ${i === active ? "bg-surface-active" : "hover:bg-surface-active"}`}>
          {c}
        </li>
      ))}
    </ul>
  );
  const variableMenu = variablesOpen && (
    <div ref={menu} id={menuId} role="menu" onKeyDown={onVariableMenuKey}
      className="popover fixed z-[60] max-h-72 w-64 overflow-y-auto p-2">
      {variableGroups.map((group) => (
        <div key={group.label} role="group" aria-label={group.label}>
          <div className="px-3 pt-2 pb-1 text-xs text-fg-muted">{group.label}</div>
          {group.items.map((candidate) => {
            const i = candidates.indexOf(candidate);
            return (
              <button key={candidate} type="button" role="menuitem" tabIndex={-1}
                className={`flex min-h-10 w-full items-center rounded-[7px] px-3 text-left text-variable ${mono} ${i === variableActive ? "bg-surface-active" : "hover:bg-surface-active"} pointer-coarse:min-h-11`}
                onFocus={() => setVariableActive(i)} onClick={() => insertVariable(candidate)}>
                {candidate}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
  if (!multiline) return (
    // `V3 / VariableInput`: jeden box 44 px, `{}` uvnitř vpravo bez výplně a bez rámečku
    <div ref={root} className="relative">
      <input {...props} className={`${inputCls} ${mono} pr-12`} />
      <div className="absolute top-0 right-0">{variableButton}{variableMenu}</div>
      {suggestions}
    </div>
  );
  const opened = (value.match(/\{\{/g) ?? []).length, closed = (value.match(/\}\}/g) ?? []).length;
  return (
    <div ref={root}>
      <CodeBox label={label} kind={t(template ? "form.kind.template" : "form.kind.expr")} invalid={!!a11y["aria-invalid"]}
        tools={<div className="relative -my-3 -mr-3">{variableButton}{variableMenu}</div>}
        status={template && value.includes("{{") ? (opened === closed ? ["ok", t("form.template.ok")] : ["bad", t("form.template.bad")]) : undefined}
        shortcut={candidates.length ? t("form.variables.shortcut") : undefined}>
        <div className="relative">
          <textarea {...props} className={codeArea} rows={Math.min(12, Math.max(3, value.split("\n").length))} />
          {suggestions}
        </div>
      </CodeBox>
    </div>
  );
}

/** Editor uvnitř `CodeBox`: bez vlastní výplně a prstence (fokus nese box). */
const codeArea = `block w-full resize-y bg-transparent p-4 ${mono} leading-5 text-fg placeholder:text-fg-muted focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 pointer-coarse:text-base`;

/** Víceřádkové pole (návrh `V3 / CodeInput`, změřeno z .pen): box `nested` r8 bez rámečku; toolbar p 12 16 s linkou
 *  (štítek 13 `fg-secondary`, vpravo jazyk mono 11 `text-type` + nástroje), editor p 16, patička p 10 16 s linkou
 *  (stav 12 s ikonou 14, vpravo zkratka mono 11 `fg-muted`). Fokus ring 2 `accent` na celém boxu. */
function CodeBox({ label, kind, tools, status, shortcut, invalid, children }: {
  label?: ReactNode; kind: string; tools?: ReactNode; status?: ["ok" | "bad", string]; shortcut?: string; invalid?: boolean; children: ReactNode;
}) {
  return (
    // DOM: editor, pak toolbar (Tab z pole jde na `{}` jako u jednořádkového); vizuálně toolbar nahoře (`order-first`)
    <div className={`relative flex flex-col rounded-control bg-nested ${invalid ? "ring-2 ring-error" : "has-[textarea:focus]:ring-2 has-[textarea:focus]:ring-accent"}`}>
      {children}
      <div className="order-first flex min-h-11 items-center justify-between gap-4 border-b border-line px-4 py-3">
        <div className="min-w-0">{label}</div>
        <div className="flex items-center gap-3.5">
          <span className="font-mono text-[11px] font-medium text-type">{kind}</span>
          {tools}
        </div>
      </div>
      {(status || shortcut) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2.5">
          {status && (
            <span className={`inline-flex items-center gap-2 font-mono text-xs whitespace-nowrap ${status[0] === "ok" ? "text-success" : "text-error"}`}>
              {status[0] === "ok" ? <Check className="size-3.5" aria-hidden /> : <CircleX className="size-3.5" aria-hidden />}{status[1]}
            </span>
          )}
          {shortcut && <span className="ml-auto font-mono text-[11px] whitespace-nowrap text-fg-muted">{shortcut}</span>}
        </div>
      )}
    </div>
  );
}

// --- JSON pro vnořené hodnoty (schema, tools, default, criteria) ----------------------------

/** Mapa nebo seznam jako JSON text; nevalidní JSON se nezapíše a ukáže chybu. Prázdné = pole se smaže. */
export function JsonInput({ value, onChange, a11y: { label, ...a11y }, onError }: {
  value: unknown; onChange: (v: unknown) => void; a11y: A11y; onError?: (msg: string | null) => void;
}) {
  const show = (v: unknown) => (v === undefined ? "" : JSON.stringify(v, null, 2));
  const [text, setText] = useState(show(value));
  const [bad, setBad] = useState(false);
  const last = useRef(value);
  useEffect(() => {
    if (JSON.stringify(value) !== JSON.stringify(last.current)) setText(show(value));
    last.current = value;
  }, [value]);
  return (
    <CodeBox label={label} kind="JSON" invalid={bad || !!a11y["aria-invalid"]}
      status={text.trim() ? (bad ? ["bad", t("form.json.bad")] : ["ok", t("form.json.ok")]) : undefined}>
      <textarea
        {...a11y} aria-invalid={bad || a11y["aria-invalid"] || undefined} spellCheck={false} value={text}
        rows={Math.min(10, Math.max(2, text.split("\n").length))} className={codeArea}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const v = e.target.value.trim() ? JSON.parse(e.target.value) : undefined;
            setBad(false);
            onError?.(null);
            last.current = v;
            onChange(v);
          } catch {
            setBad(true);
            onError?.(t("form.badJson"));
          }
        }}
      />
    </CodeBox>
  );
}

// --- modál jen pro rozhodnutí (§1) ------------------------------------------------------------

export interface ModalAction {
  label: string;
  onSelect: () => void;
  primary?: boolean;
  danger?: boolean;
}

/** Modál rozhodnutí: fokus na první akci, Esc = zrušit, Tab zůstává uvnitř. */
/** Fokus dostane první akce dialogu (ne Zrušit ani křížek) — jako před přeskupením patičky. */
const firstAction = (root: HTMLElement | null) =>
  root?.querySelector<HTMLElement>("[data-action]") ?? root?.querySelector<HTMLElement>("button:not([data-close])");

export function Modal({ title, children, actions, onCancel, cancelLabel = t("common.cancel") }: {
  title: string; children?: ReactNode; actions: ModalAction[]; onCancel: () => void; cancelLabel?: string;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    (root.current?.querySelector<HTMLElement>("[data-autofocus]") ?? firstAction(root.current))?.focus();
    return () => { document.documentElement.style.overflow = overflow; prev?.focus?.(); };
  }, []);
  // fokusované tlačítko zmizelo (např. „Smazat“ po odmítnutí z API) → fokus zpět do dialogu, jinak nefunguje Esc ani Tab
  useEffect(() => {
    if (!root.current?.contains(document.activeElement)) firstAction(root.current)?.focus();
  });
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    } else if (e.key === "Tab") trapTab(root.current, e);
  };
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-canvas/70 md:items-center md:p-4" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      {/* návrh „ModalShell“ (změřeno z .pen): r14, hlavička p24 s linkou (titul 22 + zavřít 44), obsah p24 gap 18,
          patička p 18 24 s linkou: Zrušit, pak akce */}
      <div ref={root} role="dialog" aria-modal="true" aria-labelledby={id} onKeyDown={onKey}
        className="sheet-enter sheet-shadow flex max-h-[calc(100dvh-48px)] w-full max-w-lg flex-col rounded-t-tile bg-surface md:rounded-tile md:shadow-[var(--shadow-pop)]">
        <div className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-fg-muted/40 md:hidden" aria-hidden />
        <div className="flex items-center gap-4 border-b border-line py-4 pr-4 pl-6">
          <h2 id={id} className="min-w-0 flex-1 text-[22px] leading-8 font-semibold">{title}</h2>
          {/* informační dialog (bez akcí) má jediné „Zavřít“ dole */}
          {actions.length > 0 && (
            <button type="button" data-close className={btn.icon} onClick={onCancel} aria-label={t("common.close")} title={t("common.close")}>
              <X className="size-4" aria-hidden />
            </button>
          )}
        </div>
        {children && <div className="min-h-0 space-y-[18px] overflow-y-auto p-6 text-sm text-fg-secondary">{children}</div>}
        <div className={`flex shrink-0 flex-wrap justify-end gap-2.5 px-6 pt-[18px] pb-[calc(18px+env(safe-area-inset-bottom))] ${children ? "border-t border-line" : ""}`}>
          <button type="button" className={btn.secondary} onClick={onCancel}>{cancelLabel}</button>
          {actions.map((a) => (
            <button key={a.label} type="button" data-action onClick={a.onSelect}
              className={a.danger ? btn.danger : a.primary ? btn.primary : btn.secondary}>
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Enter v textovém poli dialogu = hlavní akce (formulář s víc poli bez submit tlačítka se sám neodešle). */
export const submitOnEnter = (submit: () => unknown) => (e: KeyboardEvent) => {
  if (e.key === "Enter" && (e.target as HTMLElement).matches("input:not([type=checkbox]):not([type=radio])")) {
    e.preventDefault();
    void submit();
  }
};

/** Dialog se jménem (nový scénář / agent / skill): slug s kontrolou na místě; `models` = výběr aliasu (agent). */
export function NameDialog({ title, taken, onSubmit, onCancel, withDescription = false, models, pattern = /^[a-z][a-z0-9-]*$/,
  initialName = "", submitLabel = t("common.create") }: {
  title: string; taken: string[]; onSubmit: (name: string, description: string, model: string) => Promise<void> | void;
  onCancel: () => void; withDescription?: boolean; models?: string[]; pattern?: RegExp; initialName?: string; submitLabel?: string;
}) {
  const [name, setName] = useState(initialName);
  const [desc, setDesc] = useState("");
  const [model, setModel] = useState(models?.[0] ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const problem = !name ? null : !pattern.test(name) ? t("form.slug") : taken.includes(name) ? t("form.taken", { name }) : null;
  const submit = async () => {
    if (!name || problem || busy) return;
    if (initialName && name === initialName) return onCancel(); // přejmenování na totéž jméno nic nedělá
    setBusy(true);
    try {
      await onSubmit(name, desc, model);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onCancel={onCancel}
      actions={[{ label: busy ? t("common.saving") : submitLabel, primary: true, onSelect: submit }]}>
      <form onSubmit={(e) => (e.preventDefault(), submit())} onKeyDown={submitOnEnter(submit)} className="space-y-3">
        <FormField label={t("form.name")} help={t("form.slugHelp")} errors={problem ? [problem] : []} required>
          {(a) => <input {...a} data-autofocus value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} ${mono}`} autoComplete="off" />}
        </FormField>
        {withDescription && (
          <FormField label={t("agent.description")}>
            {(a) => <input {...a} value={desc} onChange={(e) => setDesc(e.target.value)} className={inputCls} />}
          </FormField>
        )}
        {models && (
          <FormField label={t("agent.model")} help={t("agent.modelHelp")}>
            {(a) => (
              <select {...a} value={model} onChange={(e) => setModel(e.target.value)} className={inputCls}>
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </FormField>
        )}
        {error && <p role="alert" className="font-mono text-xs whitespace-pre-wrap text-error">{error}</p>}
      </form>
    </Modal>
  );
}

/** Hodnota vstupu podle `type` scénáře (formulář spuštění, výchozí hodnota vstupu). */
export function ValueInput({ type, value, onChange, a11y }: {
  type?: string; value: unknown; onChange: (v: unknown) => void;
  a11y: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean };
}) {
  switch (type) {
    case "boolean":
      return <label htmlFor={a11y.id} className="inline-flex size-9 items-center justify-center pointer-coarse:size-11"><input {...a11y} type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-accent" /></label>;
    case "number":
    case "integer":
      return (
        <input {...a11y} type="number" step={type === "integer" ? 1 : "any"} className={`${inputCls} font-mono`}
          value={typeof value === "number" ? value : ""} onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />
      );
    case "list":
    case "object":
      return <JsonInput a11y={a11y} value={value} onChange={onChange} />;
    case "file":
      return <input {...a11y} disabled className={inputCls} value="" placeholder={t("run.fileInput")} />;
    default:
      return <textarea {...a11y} rows={2} className={inputCls} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />;
  }
}
