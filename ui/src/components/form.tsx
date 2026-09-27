// Editační prvky (§3 inventář): pole se štítkem, výraz/šablona s našeptávačem, JSON, modál rozhodnutí.
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type KeyboardEvent } from "react";
import { Braces } from "lucide-react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { btn } from "./ui";

const selectArrow = "[&:is(select)]:appearance-none [&:is(select)]:bg-[linear-gradient(45deg,transparent_50%,var(--color-fg-muted)_50%),linear-gradient(135deg,var(--color-fg-muted)_50%,transparent_50%)] [&:is(select)]:bg-[size:8px_8px] [&:is(select)]:bg-[position:calc(100%-25px)_55%,calc(100%-17px)_55%] [&:is(select)]:bg-no-repeat [&:is(select)]:pr-10";
export const inputCls =
  `w-full min-h-11 rounded-[var(--radius-control)] bg-nested px-3 py-2 text-sm text-fg placeholder:text-fg-muted ring-1 ring-line focus:outline-none focus:ring-2 focus:ring-accent aria-invalid:ring-error aria-invalid:focus:ring-error disabled:opacity-50 pointer-coarse:text-base [&:is(textarea)]:p-3 ${selectArrow}`;
const mono = "font-mono text-[13px]";

/** Pole se štítkem nad sebou (§6): `aria-describedby` na nápovědu i chybu. */
export function FormField({ label, help, errors = [], required, children, action }: {
  label: string; help?: ReactNode; errors?: (ErrorItem | string)[]; required?: boolean; action?: ReactNode;
  children: (a11y: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const id = useId();
  const described = [help && `${id}-help`, errors.length && `${id}-err`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-fg-secondary">
          {label}{required && <span className="text-fg-muted"> *</span>}
        </label>
        {action}
      </div>
      {children({ id, "aria-describedby": described, "aria-invalid": errors.length > 0 || undefined })}
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

/** Drobná pilulka „+ Přidat …“ vpravo od štítku sekce (§3 Button). */
export const AddPill = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <button type="button" onClick={onClick} className="rounded-full bg-nested px-2.5 py-0.5 text-xs text-fg-secondary hover:bg-surface-hover pointer-coarse:min-h-11">
    + {label}
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
export function CodeInput({ value, onChange, candidates, template = false, multiline = false, a11y, placeholder }: {
  value: string; onChange: (v: string) => void; candidates: string[]; template?: boolean; multiline?: boolean;
  a11y: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }; placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement & HTMLInputElement>(null);
  const caretAt = useRef<number | null>(null);
  const selection = useRef<{ start: number; end: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
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
  return (
    <div ref={root} className="relative">
      {multiline
        ? <textarea {...props} className={`${inputCls} ${mono} [&:is(textarea)]:pr-12`} rows={Math.min(12, Math.max(3, value.split("\n").length))} />
        : <input {...props} className={`${inputCls} ${mono} pr-12`} />}
      <button
        type="button" className={`absolute right-0.5 grid size-10 place-items-center rounded-[var(--radius-control)] bg-control text-variable hover:bg-control-hover pointer-coarse:size-11 ${multiline ? "top-1" : "top-1/2 -translate-y-1/2"} disabled:cursor-not-allowed disabled:opacity-40`}
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
        <Braces className="size-4" aria-hidden />
      </button>
      {open && (
        <ul id={listId} role="listbox" className="absolute left-0 z-30 mt-1 w-full rounded-[var(--radius-card)] bg-surface p-1 ring-1 ring-line">
          {matches.map((c, i) => (
            <li key={c} id={`${listId}-${i}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => (e.preventDefault(), accept(c))}
              className={`flex h-8 cursor-pointer items-center rounded-[var(--radius-control)] px-3 text-variable ${mono} ${i === active ? "bg-surface-hover" : "hover:bg-surface-hover"}`}>
              {c}
            </li>
          ))}
        </ul>
      )}
      {variablesOpen && (
        <div ref={menu} id={menuId} role="menu" onKeyDown={onVariableMenuKey}
          className="absolute right-0 top-full z-40 mt-1 max-h-72 w-64 overflow-y-auto rounded-[var(--radius-card)] bg-surface p-1 ring-1 ring-line">
          {variableGroups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label}>
              <div className="px-3 pt-2 pb-1 text-xs text-fg-muted">{group.label}</div>
              {group.items.map((candidate) => {
                const i = candidates.indexOf(candidate);
                return (
                  <button key={candidate} type="button" role="menuitem" tabIndex={-1}
                    className={`flex min-h-10 w-full items-center rounded-[var(--radius-control)] px-3 text-left text-variable ${mono} ${i === variableActive ? "bg-surface-hover" : "hover:bg-surface-hover"} pointer-coarse:min-h-11`}
                    onFocus={() => setVariableActive(i)} onClick={() => insertVariable(candidate)}>
                    {candidate}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- JSON pro vnořené hodnoty (schema, tools, default, criteria) ----------------------------

/** Mapa nebo seznam jako JSON text; nevalidní JSON se nezapíše a ukáže chybu. Prázdné = pole se smaže. */
export function JsonInput({ value, onChange, a11y, onError }: {
  value: unknown; onChange: (v: unknown) => void; a11y: { id: string; "aria-describedby"?: string };
  onError?: (msg: string | null) => void;
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
    <textarea
      {...a11y} aria-invalid={bad || undefined} spellCheck={false} value={text}
      rows={Math.min(10, Math.max(2, text.split("\n").length))} className={`${inputCls} ${mono}`}
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
export function Modal({ title, children, actions, onCancel, cancelLabel = t("common.cancel") }: {
  title: string; children?: ReactNode; actions: ModalAction[]; onCancel: () => void; cancelLabel?: string;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    (root.current?.querySelector<HTMLElement>("[data-autofocus]") ?? root.current?.querySelector<HTMLElement>("button"))?.focus();
    return () => prev?.focus?.();
  }, []);
  // fokusované tlačítko zmizelo (např. „Smazat“ po odmítnutí z API) → fokus zpět do dialogu, jinak nefunguje Esc ani Tab
  useEffect(() => {
    if (!root.current?.contains(document.activeElement)) root.current?.querySelector<HTMLElement>("button")?.focus();
  });
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    } else if (e.key === "Tab") {
      const all = [...(root.current?.querySelectorAll<HTMLElement>(":is(button, input, textarea, select):not(:disabled), a[href]") ?? [])];
      const i = all.indexOf(document.activeElement as HTMLElement);
      const j = e.shiftKey ? (i <= 0 ? all.length - 1 : i - 1) : (i + 1) % all.length;
      e.preventDefault();
      all[j]?.focus();
    }
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-canvas/70 p-4" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div ref={root} role="dialog" aria-modal="true" aria-labelledby={id} onKeyDown={onKey}
        className="w-full max-w-lg space-y-4 rounded-[var(--radius-panel)] bg-surface p-6">
        <h2 id={id} className="text-lg font-semibold">{title}</h2>
        {children && <div className="space-y-3 text-sm text-fg-secondary">{children}</div>}
        <div className="flex flex-wrap justify-end gap-2">
          {actions.map((a) => (
            <button key={a.label} type="button" onClick={a.onSelect}
              className={a.danger ? btn.danger : a.primary ? btn.primary : btn.secondary}>
              {a.label}
            </button>
          ))}
          <button type="button" className={btn.secondary} onClick={onCancel}>{cancelLabel}</button>
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
