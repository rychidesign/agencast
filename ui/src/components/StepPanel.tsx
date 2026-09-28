// Panel kroku (§2.3): typ nahoře jako select, pole typu, dole sbalené Podmínka / Spolehlivost /
// Podrobnosti kroku. Změny jdou do rozpracovaného stromu (edit.ts), na disk až tlačítkem Uložit.
import { PanelRight, Trash2, X } from "lucide-react";
import { useContext, useEffect, useState, type ReactNode } from "react";
import { flat, isObj, outputFields, visibleBefore, type Header, type WStep } from "../edit";
import { t, tOr } from "../i18n";
import { href } from "../router";
import { readBy, readsFrom } from "../steps";
import type { ErrorItem, IoSpec, Project, StepType } from "../types";
import { AddPill, CodeInput, FormField, inputCls, JsonInput } from "./form";
import { PICKER_GROUPS } from "./TypePicker";
import { btn, Collapsible, ErrorList, SheetContext, useDialog } from "./ui";

type Obj = Record<string, unknown>;

/** Ikonové tlačítko hlavičky panelu: 32 px ghost (fidelity §7), na dotyku 44 px. */
export const panelIcon = "grid size-11 shrink-0 place-items-center rounded-[var(--radius-button)] text-fg-secondary hover:bg-surface-hover hover:text-fg disabled:opacity-50";

/** PanelShell (návrh 05, změřeno z .pen): `surface` r16; hlavička p 20 s linkou (ikona 16, eyebrow mono 10 verzálky,
 *  titul 18 semibold, zavřít 44 ghost), tělo p 20, mezera polí 18. Do 1279 px (`SheetContext`) plnoobrazovkový sheet:
 *  `role="dialog"`, fokus past, Esc zavře, tělo scrolluje, hlavička stojí. */
export function PanelShell({ id, eyebrow, title, onClose, actions, children }: {
  id: string; eyebrow: string; title: ReactNode; onClose: () => void; actions?: ReactNode; children: ReactNode;
}) {
  const sheet = useContext(SheetContext);
  const dialog = useDialog<HTMLElement>(onClose, sheet);
  return (
    <aside aria-labelledby={id} ref={dialog.ref} onKeyDown={dialog.onKeyDown}
      {...(sheet && { role: "dialog", "aria-modal": true, tabIndex: -1 })}
      className={sheet ? "fixed inset-0 z-50 flex flex-col bg-surface focus:outline-none" : "rounded-panel bg-surface"}>
      <div className="flex shrink-0 items-center gap-3 border-b border-line py-4 pr-3 pl-5">
        <PanelRight className="size-4 shrink-0 text-fg-secondary" aria-hidden />
        <div className="min-w-0 flex-1 space-y-[3px]">
          <div id={id} className="font-mono text-[10px] leading-[15px] tracking-[0.08em] text-fg-muted uppercase">{eyebrow}</div>
          <div className={`text-lg leading-[26px] font-semibold ${sheet ? "[overflow-wrap:anywhere]" : "truncate"}`}>{title}</div>
        </div>
        {actions}
        <button type="button" className={panelIcon} onClick={onClose} aria-label={t("common.close")} title={t("common.close")}>
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <div className={sheet ? "min-h-0 flex-1 overflow-y-auto overscroll-contain p-5 pb-10" : "p-5"}>{children}</div>
    </aside>
  );
}

/** Kde která společná vlastnost dává smysl (scenario.md §3). */
const RELIABILITY: Record<StepType, string[]> = {
  ask: ["timeout", "budget_usd", "retry", "on_error", "default"],
  task: ["timeout", "budget_usd", "retry", "on_error", "default", "dedupe_key"],
  jev: ["timeout", "budget_usd", "retry", "on_error", "default"],
  image: ["timeout", "budget_usd", "retry", "on_error", "default"],
  call: ["timeout", "budget_usd", "on_error", "default"],
  parallel: ["timeout", "budget_usd"],
  set: ["default"],
  switch: [], fail: [], output: [],
};

const TYPES: StepType[] = [...PICKER_GROUPS.flat(), "output"];
const ID_RE = /^[a-z][a-z0-9_]*$/;

/** Odebere prázdné volitelné hodnoty (pole se pak ze souboru smaže). */
const set = (o: Obj, k: string, v: unknown): Obj => {
  const c = { ...o };
  if (v === undefined || v === "") delete c[k];
  else c[k] = v;
  return c;
};

/** Přejmenuje klíč mapy se zachováním pořadí. */
const renameKey = (o: Obj, from: string, to: string): Obj =>
  Object.fromEntries(Object.entries(o).map(([k, v]) => [k === from ? to : k, v]));

export interface PanelEdit {
  /** Změna kroku; stejné `key` po sobě = jeden krok zpět (psaní do pole). */
  change: (fn: (s: WStep) => WStep, key?: string) => void;
  retype: (type: StepType) => void;
  remove: () => void;
  /** Nové id; čtený krok se před přejmenováním ptá na přepis odkazů. */
  rename: (id: string) => void;
}

export function StepPanel({ step, steps, header, project, scenario, errors, onClose, onSelect, edit }: {
  step: WStep; steps: WStep[]; header: Header; project: Project; scenario: string; errors: ErrorItem[];
  onClose: () => void; onSelect: (id: string) => void; edit: PanelEdit;
}) {
  const type = step.type;
  const visible = visibleBefore(steps, step.uid);
  const candidates = [
    ...Object.keys(header.inputs ?? {}).map((k) => `inputs.${k}`),
    ...visible.flatMap((s) => {
      const target = s.type === "call" ? project.scenarios.find((x) => x.name === s.call)?.outputs : undefined;
      const f = outputFields(s, target);
      return f.length ? f.map((x) => `steps.${s.id}.${x}`) : [`steps.${s.id}`];
    }),
  ];
  const fieldErrors = (path: string) => errors.filter((e) => e.field === path || e.field?.startsWith(`${path}.`));
  const known = ["id", "when", ...(type ? [type, ...RELIABILITY[type]] : [])];
  const loose = errors.filter((e) => !e.field || !known.some((k) => e.field === k || e.field!.startsWith(`${k}.`)));
  const setField = (k: string, v: unknown) => edit.change((s) => ({ ...s, fields: set(s.fields, k, v) }), `f:${k}`);
  const reliability = type ? RELIABILITY[type] : [];
  const filled = reliability.filter((k) => step.fields[k] !== undefined);
  const ctx: FormCtx = { step, candidates, project, header, errors: fieldErrors, change: edit.change };

  return (
    <PanelShell id="step-panel-title" eyebrow={`${t("panel.step", { n: step.nn })} · ${type ?? "?"}`}
      title={<span className="font-mono" title={step.id}>{step.id}</span>} onClose={onClose}
      actions={
        <button type="button" onClick={edit.remove} aria-label={t("edit.deleteStep", { id: step.id })} title={t("edit.delete")}
          className={`${panelIcon} text-error hover:bg-error/10 hover:text-error`}>
          <Trash2 className="size-4" aria-hidden />
        </button>
      }>
      <div className="space-y-[18px]">
        <ErrorList errors={loose} />
        <FormField label={t("panel.type")}>
          {(a) => (
            <select {...a} value={type ?? ""} onChange={(e) => edit.retype(e.target.value as StepType)} disabled={type === "output"}
              className={`${inputCls} font-mono`}>
              {!type && <option value="">?</option>}
              {TYPES.filter((k) => k !== "output" || type === "output").map((k) => <option key={k} value={k}>{k} · {t(`picker.${k}`)}</option>)}
            </select>
          )}
        </FormField>
        <TypeForm ctx={ctx} />
        <div className="divide-y divide-line border-t border-line">
          {type !== "output" && (
            <Collapsible title={t("panel.condition")} value={<span className="font-mono">{step.when || t("panel.always")}</span>}>
              <FormField label={t("panel.when")} help={t("panel.conditionHelp")} errors={fieldErrors("when")}>
                {(a) => <CodeInput a11y={a} value={step.when ?? ""} candidates={candidates} placeholder="steps.kontrola.on_brand < 0.7"
                  onChange={(v) => edit.change((s) => ({ ...s, when: v || null }), "when")} />}
              </FormField>
            </Collapsible>
          )}
          {reliability.length > 0 && (
            <Collapsible title={t("panel.reliability")} value={filled.length ? filled.join(", ") : t("panel.default")}>
              <div className="space-y-3">
                {reliability.map((k) => (
                  <FormField key={k} label={tOr(`field.${k}`, k)} help={tOr(`help.${k}`, "")} errors={fieldErrors(k)} boxed={k === "default"}>
                    {(a) =>
                      k === "on_error" ? (
                        <select {...a} className={inputCls} value={String(step.fields.on_error ?? "")} onChange={(e) => setField(k, e.target.value)}>
                          <option value="">{t("panel.default")} (fail)</option>
                          <option value="fail">fail</option>
                          <option value="continue">continue</option>
                        </select>
                      ) : k === "default" ? (
                        <JsonInput a11y={a} value={step.fields.default} onChange={(v) => setField(k, v)} />
                      ) : k === "budget_usd" || k === "retry" ? (
                        <NumberInput a11y={a} value={step.fields[k]} step={k === "retry" ? 1 : 0.01} onChange={(v) => setField(k, v)} />
                      ) : k === "dedupe_key" ? (
                        <CodeInput a11y={a} template value={String(step.fields[k] ?? "")} candidates={candidates} onChange={(v) => setField(k, v)} />
                      ) : (
                        <input {...a} className={`${inputCls} font-mono`} placeholder="90s, 3m" value={String(step.fields[k] ?? "")} onChange={(e) => setField(k, e.target.value)} />
                      )
                    }
                  </FormField>
                ))}
              </div>
            </Collapsible>
          )}
          <Collapsible title={t("panel.details")} value={<span className="font-mono">{step.id}</span>}>
            <div className="space-y-4">
              <IdField step={step} steps={steps} errors={fieldErrors("id")} onRename={edit.rename} />
              <dl className="space-y-3 text-sm">
                <div><dt className="text-[13px] font-semibold text-fg-secondary">{t("panel.readsFrom")}</dt>
                  <dd className="mt-1"><Chips ids={readsFrom(step)} onSelect={onSelect} /></dd></div>
                <div><dt className="text-[13px] font-semibold text-fg-secondary">{t("panel.readBy")}</dt>
                  <dd className="mt-1"><Chips ids={readBy(flat(steps), step.id)} onSelect={onSelect} /></dd></div>
              </dl>
              <a className="inline-block text-sm text-fg-secondary underline hover:text-fg" href={href(project.name, "scenare", scenario, { krok: step.id, rezim: "yaml" })}>
                {t("panel.openYaml")}
              </a>
            </div>
          </Collapsible>
        </div>
      </div>
    </PanelShell>
  );
}

const Chips = ({ ids, onSelect }: { ids: string[]; onSelect: (id: string) => void }) =>
  ids.length ? (
    <span className="flex flex-wrap gap-1.5">
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => onSelect(id)}
          className="rounded-full bg-nested px-2.5 py-0.5 font-mono text-[13px] hover:bg-surface-hover">{id}</button>
      ))}
    </span>
  ) : <span className="text-fg-muted">{t("panel.nothing")}</span>;

/** Přejmenování id: formát a jedinečnost; odkazy čtenářů přepíše dávka (`rename_step`, `rename_refs`). */
function IdField({ step, steps, errors, onRename }: {
  step: WStep; steps: WStep[]; errors: ErrorItem[]; onRename: (id: string) => void;
}) {
  const [value, setValue] = useState(step.id);
  useEffect(() => setValue(step.id), [step.id]);
  const problem = value === step.id ? null
    : !ID_RE.test(value) ? t("panel.idFormat")
    : flat(steps).some((s) => s.id === value) ? t("form.taken", { name: value })
    : null;
  const commit = () => {
    if (value === step.id || problem) return;
    onRename(value);
    setValue(step.id); // po potvrzení přijde nové id, po zrušení zůstane staré
  };
  return (
    <FormField label="id" errors={[...(problem ? [problem] : []), ...errors]}>
      {(a) => (
        <input {...a} className={`${inputCls} font-mono`} value={value} onChange={(e) => setValue(e.target.value)}
          onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), commit())} />
      )}
    </FormField>
  );
}

function NumberInput({ value, onChange, a11y, step = 1, min }: {
  value: unknown; onChange: (v: number | undefined) => void; a11y: object; step?: number; min?: number;
}) {
  return (
    <input {...a11y} type="number" step={step} min={min} className={`${inputCls} font-mono`}
      value={typeof value === "number" ? value : ""} onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />
  );
}

// --- pole podle typu ----------------------------------------------------------------------

interface FormCtx {
  step: WStep;
  candidates: string[];
  project: Project;
  header: Header;
  errors: (path: string) => ErrorItem[];
  change: PanelEdit["change"];
}

function TypeForm({ ctx }: { ctx: FormCtx }) {
  const { step, candidates, project, errors } = ctx;
  const type = step.type;
  if (!type) return null;
  const body: Obj = isObj(step.fields[type]) ? (step.fields[type] as Obj) : {};
  const setBody = (k: string, v: unknown) =>
    ctx.change((s) => ({ ...s, fields: { ...s.fields, [type]: set(isObj(s.fields[type]) ? (s.fields[type] as Obj) : {}, k, v) } }), `b:${k}`);
  const str = (k: string) => (typeof body[k] === "string" ? (body[k] as string) : "");
  const tpl = (k: string, label: string, multiline = true, placeholder?: string) => (
    <FormField label={label} errors={errors(`${type}.${k}`)} required boxed={multiline}>
      {(a) => <CodeInput a11y={a} template multiline={multiline} value={str(k)} candidates={candidates} placeholder={placeholder} onChange={(v) => setBody(k, v)} />}
    </FormField>
  );
  const agentSelect = (
    <FormField label={t("field.agent")} errors={errors(`${type}.agent`)} required>
      {(a) => (
        <select {...a} className={inputCls} value={str("agent")} onChange={(e) => setBody("agent", e.target.value)}>
          <option value="">—</option>
          {!project.agents.some((x) => x.name === body.agent) && body.agent ? <option value={str("agent")}>{str("agent")}</option> : null}
          {project.agents.map((x) => <option key={x.name} value={x.name}>{x.name} — {x.description}</option>)}
        </select>
      )}
    </FormField>
  );
  const json = (k: string, label: string, help?: string) => (
    <FormField label={label} help={help} errors={errors(`${type}.${k}`)} boxed>
      {(a) => <JsonInput a11y={a} value={body[k]} onChange={(v) => setBody(k, v)} />}
    </FormField>
  );

  switch (type) {
    case "ask":
    case "task": {
      const agent = project.agents.find((x) => x.name === body.agent);
      const servers = Array.isArray(agent?.mcp) ? (agent!.mcp as string[]) : [];
      return (
        <div className="space-y-4">
          {agentSelect}
          {tpl("prompt", t("field.prompt"))}
          {type === "task" && (
            <>
              <FormField label={t("field.max_turns")} help={t("help.max_turns")} errors={errors("task.max_turns")}>
                {(a) => <NumberInput a11y={a} min={1} value={body.max_turns} onChange={(v) => setBody("max_turns", v)} />}
              </FormField>
              {servers.length > 0 && (
                <FormField label={t("field.mcp")} help={t("help.mcpStep")} errors={errors("task.mcp")}>
                  {() => (
                    <div className="space-y-1">
                      {servers.map((srv) => {
                        const on = Array.isArray(body.mcp) && (body.mcp as string[]).includes(srv);
                        return (
                          <label key={srv} className="flex items-center gap-2 font-mono text-sm">
                            <input type="checkbox" checked={on} onChange={() => {
                              const cur = Array.isArray(body.mcp) ? (body.mcp as string[]) : [];
                              const next = on ? cur.filter((x) => x !== srv) : [...cur, srv];
                              setBody("mcp", next.length ? next : undefined);
                            }} />
                            {srv}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </FormField>
              )}
              {json("tools", t("field.tools"), t("help.tools", { ex: '{"instagram": ["publish_media"]}' }))}
            </>
          )}
          {json("schema", t("field.schema"), t("help.schema", { ex: '{"caption": "string", "hashtags": ["string"]}' }))}
        </div>
      );
    }
    case "jev":
      return (
        <div className="space-y-4">
          {tpl("state", t("field.state"), false, "{{ steps.copy.caption }}")}
          <MapRows ctx={ctx} k="questions" label={t("field.questions")} addLabel={t("panel.addQuestion")} prefix="q"
            blank={{ type: "noul", instructions: "" }}
            row={(name, q, setQ) => (
              <div className="space-y-2">
                <select aria-label={t("field.qtype", { name })} className={inputCls} value={String(q.type ?? "noul")}
                  onChange={(e) => setQ(set(q, "type", e.target.value))}>
                  {["noul", "choice", "score"].map((x) => <option key={x}>{x}</option>)}
                </select>
                <FormField label={t("field.instructions")} errors={errors(`jev.questions.${name}.instructions`)}>
                  {(a) => <CodeInput a11y={a} template value={String(q.instructions ?? "")} candidates={candidates} onChange={(v) => setQ(set(q, "instructions", v))} />}
                </FormField>
                {q.type !== "noul" && q.type !== undefined && (
                  <FormField label={t("field.criteria")} help={q.type === "choice" ? t("help.criteriaChoice", { ex: '{"moznost": "popis"}' }) : t("help.criteriaScore", { ex: '["stupeň 0", "stupeň 1"]' })}
                    errors={errors(`jev.questions.${name}.criteria`)} boxed>
                    {(a) => <JsonInput a11y={a} value={q.criteria} onChange={(v) => setQ(set(q, "criteria", v))} />}
                  </FormField>
                )}
              </div>
            )} />
        </div>
      );
    case "image":
      return (
        <div className="space-y-4">
          <FormField label={t("field.model")} errors={errors("image.model")} required>
            {(a) => (
              <select {...a} className={inputCls} value={str("model")} onChange={(e) => setBody("model", e.target.value)}>
                <option value="">—</option>
                {Object.entries(project.models).map(([alias, id]) => <option key={alias} value={alias}>{alias} — {id}</option>)}
              </select>
            )}
          </FormField>
          {tpl("prompt", t("field.prompt"))}
          {([['aspect_ratio', '4:5', 'pomer'], ['quality', 'medium', 'kvalita'], ['resolution', '1K', 'rozliseni']] as const).map(([field, placeholder, input]) => (
            <FormField key={field} label={t(`field.${field}`)} errors={errors(`image.${field}`)}
              help={t("help.imageParameter", { example: `{{ inputs.${input} }}` })}>
              {(a) => <CodeInput a11y={a} template placeholder={placeholder} value={str(field)} candidates={candidates}
                onChange={(v) => setBody(field, v)} />}
            </FormField>
          ))}
        </div>
      );
    case "call": {
      const target = project.scenarios.find((x) => x.name === body.scenario);
      const inputs: Obj = isObj(body.inputs) ? (body.inputs as Obj) : {};
      const names = [...new Set([...Object.keys(target?.inputs ?? {}), ...Object.keys(inputs)])];
      return (
        <div className="space-y-4">
          <FormField label={t("field.scenario")} help={target && !target.callable ? t("help.notCallable") : undefined} errors={errors("call.scenario")} required>
            {(a) => (
              <select {...a} className={inputCls} value={str("scenario")} onChange={(e) => setBody("scenario", e.target.value)}>
                <option value="">—</option>
                {project.scenarios.map((x) => (
                  <option key={x.name} value={x.name}>{x.name}{x.callable ? "" : ` (${t("panel.notCallable")})`}</option>
                ))}
              </select>
            )}
          </FormField>
          {names.map((n) => {
            const spec = target?.inputs?.[n];
            return (
              <FormField key={n} label={`inputs.${n}`} required={spec?.required} errors={errors(`call.inputs.${n}`)}
                help={spec ? [spec.type, spec.description].filter(Boolean).join(" · ") : undefined}>
                {(a) => <CodeInput a11y={a} template value={String(inputs[n] ?? "")} candidates={candidates}
                  onChange={(v) => setBody("inputs", Object.keys(set(inputs, n, v)).length ? set(inputs, n, v) : undefined)} />}
              </FormField>
            );
          })}
        </div>
      );
    }
    case "set":
      return (
        <MapRows ctx={ctx} k="" label={t("field.values")} addLabel={t("panel.addValue")} prefix="hodnota" blank=""
          row={(name, v, setV) => (
            <CodeInput a11y={{ id: `set-${name}` }} value={typeof v === "string" ? v : JSON.stringify(v)} candidates={candidates}
              onChange={(x) => setV(x)} />
          )} />
      );
    case "fail":
      return (
        <FormField label={t("field.message")} errors={errors("fail")} required boxed>
          {(a) => <CodeInput a11y={a} template multiline value={typeof step.fields.fail === "string" ? step.fields.fail : ""} candidates={candidates}
            onChange={(v) => ctx.change((s) => ({ ...s, fields: { ...s.fields, fail: v } }), "b:fail")} />}
        </FormField>
      );
    case "output": {
      const names = [...new Set([...Object.keys(ctx.header.outputs ?? {}), ...Object.keys(body)])];
      return (
        <div className="space-y-4">
          <p className="text-xs text-fg-muted">{t("help.output")}</p>
          {names.map((n) => (
            <FormField key={n} label={n} errors={errors(`output.${n}`)} help={ctx.header.outputs?.[n]?.type}>
              {(a) => <CodeInput a11y={a} template value={String(body[n] ?? "")} candidates={candidates} onChange={(v) => setBody(n, v)} />}
            </FormField>
          ))}
        </div>
      );
    }
    case "switch":
      return (
        <div className="space-y-4">
          <FormField label={t("field.value")} help={t("help.switch")} errors={errors("switch.value")} required>
            {(a) => <CodeInput a11y={a} value={str("value")} candidates={candidates} placeholder="steps.kontrola.druh" onChange={(v) => setBody("value", v)} />}
          </FormField>
          <p className="text-sm text-fg-muted">{t("panel.cases", { names: Object.keys(step.cases ?? {}).join(", ") || "–" })}</p>
        </div>
      );
    case "parallel":
      return <p className="text-sm text-fg-muted">{t("panel.branches", { names: Object.keys(step.branches ?? {}).join(", ") })}</p>;
  }
}

/** Mapa jméno → hodnota (otázky Jev, hodnoty `set`); `k` = klíč v těle typu, "" = celé tělo. */
function MapRows<V>({ ctx, k, label, addLabel, prefix, blank, row }: {
  ctx: FormCtx; k: string; label: string; addLabel: string; prefix: string; blank: V;
  row: (name: string, value: V & Obj, setValue: (v: unknown) => void) => ReactNode;
}) {
  const type = ctx.step.type!;
  const body: Obj = isObj(ctx.step.fields[type]) ? (ctx.step.fields[type] as Obj) : {};
  const map: Obj = k ? (isObj(body[k]) ? (body[k] as Obj) : {}) : body;
  const write = (next: Obj, key: string) =>
    ctx.change((s) => {
      const b: Obj = isObj(s.fields[type]) ? (s.fields[type] as Obj) : {};
      return { ...s, fields: { ...s.fields, [type]: k ? { ...b, [k]: next } : next } };
    }, key);
  const add = () => {
    let n = 1;
    while (`${prefix}_${n}` in map) n++;
    write({ ...map, [`${prefix}_${n}`]: blank }, "add");
  };
  return (
    <FormField label={label} action={<AddPill label={addLabel} onClick={add} />} errors={ctx.errors(k ? `${type}.${k}` : type).filter((e) => e.field === (k ? `${type}.${k}` : type))}>
      {() => (
        <ul className="divide-y divide-line">
          {Object.entries(map).map(([name, v]) => (
            <li key={name} className="space-y-2 py-3 first:pt-0">
              <div className="flex items-center gap-2">
                <KeyInput name={name} taken={Object.keys(map)} onRename={(to) => write(renameKey(map, name, to), "rename")} />
                <button type="button" className={btn.icon} aria-label={t("panel.removeRow", { name })}
                  onClick={() => write(Object.fromEntries(Object.entries(map).filter(([x]) => x !== name)), "remove")}>
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </div>
              {row(name, v as V & Obj, (x) => write({ ...map, [name]: x }, `v:${name}`))}
            </li>
          ))}
        </ul>
      )}
    </FormField>
  );
}

/** Identifikátor ve výrazech (`inputs.tema`, `steps.x.pole`): jako Python jméno bez pomlčky. */
export const IDENT = /^[a-z][a-z0-9_]*$/;

/** Jméno klíče (otázka, hodnota, vstup; alias modelu s `pattern` kebab): zapíše se při opuštění pole,
 *  když je platné a volné; neplatné se vrátí na původní a pravidlo je v `title` (`hint`). */
export function KeyInput({ name, taken, onRename, label, pattern = IDENT, hint }: {
  name: string; taken: string[]; onRename: (to: string) => void; label?: string; pattern?: RegExp; hint?: string;
}) {
  const [value, setValue] = useState(name);
  const bad = value !== name && (!pattern.test(value) || taken.includes(value));
  const commit = () => (bad || value === name ? setValue(name) : onRename(value));
  return (
    <input aria-label={label ?? t("panel.keyName")} aria-invalid={bad || undefined} value={value} onChange={(e) => setValue(e.target.value)}
      onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), commit())}
      title={bad ? (taken.includes(value) ? t("form.taken", { name: value }) : hint ?? t("panel.keyRule")) : undefined}
      className={`${inputCls.replace("w-full", "min-w-0 flex-1")} font-mono`} />
  );
}

// --- hlavička scénáře ---------------------------------------------------------------------

const IO_TYPES = ["string", "number", "integer", "boolean", "list", "object", "file"];

export function HeaderPanel({ name, header, errors, onClose, change }: {
  /** Jméno scénáře jako titul (jako panel Spustit), eyebrow „HLAVIČKA“ se neopakuje. */
  name: string; header: Header; errors: ErrorItem[]; onClose: () => void; change: (fn: (h: Header) => Header, key?: string) => void;
}) {
  const fe = (p: string) => errors.filter((e) => e.field === p || e.field?.startsWith(`${p}.`));
  const io = (which: "inputs" | "outputs") => {
    const map = header[which] ?? {};
    const write = (next: Record<string, IoSpec>, key: string) => change((h) => ({ ...h, [which]: next }), key);
    const add = () => {
      let n = 1;
      while (`${which === "inputs" ? "vstup" : "vystup"}_${n}` in map) n++;
      const name = `${which === "inputs" ? "vstup" : "vystup"}_${n}`;
      write({ ...map, [name]: which === "inputs" ? { type: "string", required: true } : { type: "string" } }, "add");
    };
    return (
      <FormField label={t(`panel.${which}`)} errors={fe(which).filter((e) => e.field === which)}
        action={<AddPill label={t(which === "inputs" ? "panel.addInput" : "panel.addOutput")} onClick={add} />}>
        {() => (
          // každý vstup / výstup jako vnořená karta (návrh 09: `nested` r8 p14)
          <ul className="space-y-3">
            {Object.entries(map).map(([name, spec]) => {
              const put = (s: IoSpec, key: string) => write({ ...map, [name]: s }, `${which}:${name}:${key}`);
              return (
                <li key={name} className="space-y-2 rounded-control bg-nested p-3.5">
                  <div className="flex items-center gap-2">
                    <KeyInput name={name} taken={Object.keys(map)} label={t("panel.keyName")}
                      onRename={(to) => write(renameKey(map, name, to) as Record<string, IoSpec>, "rename")} />
                    <select aria-label={t("panel.ioType", { name })} className={`${inputCls.replace("w-full", "w-28 shrink-0")}`} value={spec.type ?? "string"}
                      onChange={(e) => put({ ...spec, type: e.target.value }, "type")}>
                      {IO_TYPES.map((x) => <option key={x}>{x}</option>)}
                    </select>
                    <button type="button" className={btn.icon} aria-label={t("panel.removeRow", { name })}
                      onClick={() => write(Object.fromEntries(Object.entries(map).filter(([x]) => x !== name)), "remove")}>
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </div>
                  {which === "inputs" && (
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={!!spec.required} onChange={(e) => {
                          const { default: _d, required: _r, ...rest } = spec;
                          put(e.target.checked ? { ...rest, required: true } : { ...rest, default: "" }, "req");
                        }} />
                        {t("run.required")}
                      </label>
                      {!spec.required && (
                        <input aria-label={t("panel.defaultOf", { name })} className={`${inputCls} flex-1 font-mono`} placeholder={t("panel.defaultPh")}
                          value={typeof spec.default === "string" ? spec.default : JSON.stringify(spec.default ?? "")}
                          onChange={(e) => {
                            let v: unknown = e.target.value;
                            if (spec.type !== "string") try { v = JSON.parse(e.target.value); } catch { /* text, server ohlásí typ */ }
                            put({ ...spec, default: v }, "default");
                          }} />
                      )}
                    </div>
                  )}
                  <input aria-label={t("panel.ioDescription", { name })} className={inputCls} placeholder={t("agent.description")}
                    value={spec.description ?? ""} onChange={(e) => {
                      const { description: _x, ...rest } = spec;
                      put(e.target.value ? { ...rest, description: e.target.value } : rest, "desc");
                    }} />
                  {fe(`${which}.${name}`).map((e, i) => <p key={i} className="font-mono text-xs text-error">{e.message}</p>)}
                </li>
              );
            })}
          </ul>
        )}
      </FormField>
    );
  };
  return (
    <PanelShell id="step-panel-title" eyebrow={t("panel.header")} title={<span className="font-mono">{name}</span>} onClose={onClose}>
      <div className="space-y-[18px]">
        <ErrorList errors={errors.filter((e) => !e.field || !/^(description|inputs|outputs|callable)/.test(e.field))} />
        <FormField label={t("agent.description")} help={t("help.description")} errors={fe("description")} required>
          {(a) => <input {...a} className={inputCls} value={header.description} onChange={(e) => change((h) => ({ ...h, description: e.target.value }), "desc")} />}
        </FormField>
        {io("inputs")}
        {io("outputs")}
        <FormField label={t("panel.callableLabel")} help={t("help.callable")} errors={fe("callable")}>
          {(a) => (
            <label className="flex items-center gap-2 text-sm">
              <input {...a} type="checkbox" checked={header.callable} onChange={(e) => change((h) => ({ ...h, callable: e.target.checked }))} />
              {t("panel.callable")}
            </label>
          )}
        </FormField>
      </div>
    </PanelShell>
  );
}
