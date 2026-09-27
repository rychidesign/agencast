// §2.8 Config: formulář pro models, limits, storage, webhook, callback a openrouter.api_key_env
// (`PUT …/config`, merge patch); YAML režim = config.yaml a mcp.yaml jako text (`files/`).
// Proměnné prostředí jen ✓/✗, nikdy hodnota.
import { CodeXml, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { enc } from "../api";
import { AddPill, FormField, inputCls, Modal } from "../components/form";
import { YamlEditor } from "../components/YamlEditor";
import { btn, ErrorList, ErrorText, Loading, StatusBadge, Toggle } from "../components/ui";
import { KeyInput } from "../components/StepPanel";
import { isObj, mergePatch } from "../edit";
import { t } from "../i18n";
import { useFileDraft, useLeaveGuard, useTextFile } from "../textfile";
import type { FileDoc, Project } from "../types";
import { SaveNote, useConflictUi } from "./Agents";

type Obj = Record<string, unknown>;

/** Část config.yaml, kterou `PUT …/config` smí měnit (api.md „Operace“). */
export function configFields(data: unknown): Obj {
  const d: Obj = isObj(data) ? data : {};
  const out: Obj = {};
  for (const k of ["models", "limits", "storage", "webhook", "callback"]) if (d[k] !== undefined) out[k] = d[k];
  const or = isObj(d.openrouter) ? d.openrouter : {};
  if (or.api_key_env !== undefined) out.openrouter = { api_key_env: or.api_key_env };
  return out;
}

function EnvVar({ name, env }: { name: unknown; env?: Record<string, boolean> }) {
  if (typeof name !== "string" || !name) return <span className="text-fg-muted">–</span>;
  const set = env?.[name];
  if (set === undefined) return <span className="text-[13px] text-fg-muted">{t("config.envUnknown")}</span>;
  return (
    <StatusBadge status={set ? "succeeded" : "failed"}>
      <span className="text-[13px] text-fg-muted">{set ? t("config.envSet") : t("config.envMissing")}</span>
    </StatusBadge>
  );
}

const Section = ({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) => (
  <section className="space-y-3 border-t border-line pt-5">
    <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{title}</h3>{action}</div>
    {children}
  </section>
);

export function ConfigTab({ name, project, onChanged }: { name: string; project?: Project; onChanged?: () => void }) {
  // Bez projektu (config neprošel, 422) rovnou text souboru.
  const [mode, setMode] = useState<"form" | "yaml">(project ? "form" : "yaml");
  const url = `/projects/${enc(name)}/config`;
  const form = useFileDraft<Obj>(name, mode === "form" ? "config.yaml" : null, {
    fromDoc: (d: FileDoc) => configFields(d.data),
    request: (d, v) => {
      const fields = mergePatch(configFields(d.data), v);
      return fields ? { method: "PUT", url, body: { fields } } : null;
    },
  }, "config");
  const config = useTextFile(name, mode === "yaml" ? "config.yaml" : null);
  const mcp = useTextFile(name, mode === "yaml" ? "mcp.yaml" : null);
  const formUi = useConflictUi(form, () => form.doc?.text ?? "");
  const configUi = useConflictUi(config, () => config.doc?.text ?? "");
  const mcpUi = useConflictUi(mcp, () => mcp.doc?.text ?? "");
  useLeaveGuard(form.dirty || config.dirty || mcp.dirty);
  const texts = [config, mcp].filter((f) => f.dirty);
  const dirty = mode === "form" ? form.dirty : texts.length > 0;
  const syntax = [...config.errors, ...mcp.errors].find((e) => e.line);
  const canSave = mode === "form" ? form.dirty && !form.conflict
    : texts.length > 0 && !syntax && texts.every((f) => !f.validating && !f.conflict);

  const save = async () => {
    const ok = mode === "form" ? await formUi.save()
      : (await Promise.all([config.dirty ? configUi.save() : true, mcp.dirty ? mcpUi.save() : true])).every(Boolean);
    if (ok) onChanged?.();
    return ok;
  };
  const switchMode = (m: "form" | "yaml") => {
    if (m === mode || (m === "form" && syntax)) return;
    if (!dirty) return setMode(m);
    formUi.setModal(
      <Modal title={t("mode.title")} onCancel={formUi.close} actions={[
        { label: t("mode.save"), primary: true, onSelect: async () => (formUi.close(), (await save()) && setMode(m)) },
        { label: t("mode.discard"), danger: true, onSelect: () => (formUi.close(), form.discard(), config.discard(), mcp.discard(), setMode(m)) },
      ]}><p>{t("mode.fileDirty")}</p></Modal>,
    );
  };
  const state = mode === "form" ? form.state : (config.state.kind !== "idle" ? config.state : mcp.state);
  const errors = mode === "form" ? form.errors : [...config.errors, ...mcp.errors];

  return (
    <div className="space-y-5" onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (canSave) void save();
      }
    }}>
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <p className="mr-auto truncate font-mono text-[13px] text-fg-muted">{project?.root}</p>
          <button type="button" className={btn.primary} disabled={!canSave} onClick={() => void save()} title="Ctrl+S">{t("common.save")}</button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Toggle label={t("code.mode")} value={mode} onChange={switchMode}
            options={[{ key: "form", label: t("code.form"), disabled: syntax ? t("code.fixYaml", { n: syntax.line! }) : !project ? t("config.formNeedsValid") : undefined },
              { key: "yaml", label: <><CodeXml className="size-3.5" aria-hidden />YAML</> }]} />
          <SaveNote dirty={dirty} state={state} errors={errors.length} />
        </div>
      </div>
      {mode === "form" ? (
        <>
          {formUi.bar}
          {form.loadError && <ErrorText error={form.loadError} />}
          {!form.doc && !form.loadError && <Loading rows={6} />}
          {form.doc && form.value && <ConfigFields project={project} value={form.value} onChange={form.setValue}
            errors={form.errors} jev={isObj(form.doc.data) && isObj(form.doc.data.openrouter) ? form.doc.data.openrouter.jev_model : undefined} />}
          {formUi.modal}
        </>
      ) : (
        <div className="space-y-8">
          {configUi.bar}
          {config.doc ? <YamlEditor text={config.text} onChange={config.setText} file="config.yaml" errors={config.errors} />
            : config.loadError ? <ErrorText error={config.loadError} /> : <Loading rows={8} />}
          {mcpUi.bar}
          {mcp.doc ? <YamlEditor text={mcp.text} onChange={mcp.setText} file="mcp.yaml" errors={mcp.errors} />
            : mcp.loadError?.status === 404 ? <p className="text-sm text-fg-muted">{t("config.noMcp")}</p>
            : mcp.loadError ? <ErrorText error={mcp.loadError} /> : <Loading rows={4} />}
          {formUi.modal}{configUi.modal}{mcpUi.modal}
        </div>
      )}
    </div>
  );
}

/** Alias modelu podle config.schema.json (`kebab`): jako jméno agenta a scénáře, s pomlčkou. */
const KEBAB = /^[a-z][a-z0-9-]*$/;

const LIMITS: [string, "usd" | "time" | "int"][] = [
  ["run_budget_usd", "usd"], ["run_image_budget_usd", "usd"], ["run_timeout", "time"],
  ["max_call_depth", "int"], ["max_parallel_runs", "int"], ["daily_budget_usd", "usd"],
];
const STORAGE: Record<string, string[]> = {
  local: ["path", "public_base_url"],
  r2: ["bucket", "account_id_env", "access_key_id_env", "secret_access_key_env", "public_base_url"],
};

function ConfigFields({ project, value, onChange, errors, jev }: {
  project?: Project; value: Obj; onChange: (v: Obj) => void; errors: { message: string; field?: string }[]; jev: unknown;
}) {
  const env = project?.env;
  const fe = (p: string) => errors.filter((e) => e.field === p || e.field?.startsWith(`${p}.`));
  const sub = (k: string): Obj => (isObj(value[k]) ? (value[k] as Obj) : {});
  const put = (k: string, v: Obj) => onChange({ ...value, [k]: v });
  const clean = (o: Obj, k: string, v: unknown): Obj => {
    const c = { ...o };
    if (v === undefined || v === "") delete c[k];
    else c[k] = v;
    return c;
  };
  const models = sub("models") as Record<string, Obj>;
  const limits = sub("limits");
  const storage = sub("storage");
  const stype = String(storage.type ?? "local");
  const sconf = isObj(storage[stype]) ? (storage[stype] as Obj) : {};
  const usage = (alias: string) => project?.agents.filter((a) => a.model === alias).map((a) => a.name) ?? [];
  const envField = (label: string, section: string, k: string) => {
    const v = String(sub(section)[k] ?? "");
    return (
      <FormField label={label} errors={fe(`${section}.${k}`)} help={<EnvVar name={v} env={env} />}>
        {(a) => <input {...a} className={`${inputCls} font-mono`} value={v} placeholder="JMENO_PROMENNE"
          onChange={(e) => put(section, clean(sub(section), k, e.target.value))} />}
      </FormField>
    );
  };
  const known = ["models", "limits", "storage", "webhook", "callback", "openrouter"];
  return (
    <div className="space-y-5">
      <ErrorList errors={errors.filter((e) => !e.field || !known.some((k) => e.field!.startsWith(k)))} />
      <Section title={t("config.connection")}>
        <p className="text-xs text-fg-muted">{t("config.secretsHelp")}</p>
        {envField(t("config.keyFrom"), "openrouter", "api_key_env")}
        <p className="text-sm text-fg-muted">{t("config.jevModel")} <span className="font-mono">{String(jev ?? "jev-1.13")}</span> · {t("config.yamlOnly")}</p>
      </Section>
      <Section title={t("config.models")} action={<AddPill label={t("config.addAlias")} onClick={() => {
        let n = 1;
        while (`model-${n}` in models) n++;
        put("models", { ...models, [`model-${n}`]: { id: "" } });
      }} />}>
        <ul className="space-y-2">
          {Object.entries(models).map(([alias, m]) => {
            const users = usage(alias);
            const setM = (k: string, v: unknown) => put("models", { ...models, [alias]: clean(m, k, v) });
            return (
              <li key={alias} className="space-y-1">
                <div className="grid grid-cols-[10rem_1fr_7rem_7rem_9rem_7rem_auto] items-center gap-2">
                  {users.length ? <span className="px-3 font-mono text-sm">{alias}</span>
                    : <KeyInput name={alias} taken={Object.keys(models)} label={t("config.alias")} pattern={KEBAB} hint={t("config.aliasRule")}
                      onRename={(to) => put("models", Object.fromEntries(Object.entries(models).map(([k, v]) => [k === alias ? to : k, v])))} />}
                  <input aria-label={t("config.modelId", { alias })} className={`${inputCls} font-mono`} placeholder="anthropic/claude-haiku-4.5"
                    value={String(m.id ?? "")} onChange={(e) => setM("id", e.target.value)} />
                  <select aria-label={t("config.api", { alias })} className={inputCls} value={String(m.api ?? "chat")}
                    onChange={(e) => {
                      const next = clean(m, "api", e.target.value);
                      put("models", { ...models, [alias]: e.target.value === "images" ? next : clean(next, "quality", undefined) });
                    }}>
                    <option value="chat">chat</option>
                    <option value="images">images</option>
                  </select>
                  {m.api === "images" ? <select aria-label={t("config.quality", { alias })} className={inputCls} value={String(m.quality ?? "")}
                    onChange={(e) => setM("quality", e.target.value || undefined)}>
                    <option value="">{t("panel.default")}</option>
                    <option value="auto">auto</option>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select> : <span />}
                  <select aria-label={t("config.structured", { alias })} className={inputCls} value={String(m.structured_output ?? "")}
                    onChange={(e) => setM("structured_output", e.target.value)}>
                    <option value="">native_schema ({t("panel.default")})</option>
                    <option value="native_schema">native_schema</option>
                    <option value="tool_wrapper">tool_wrapper</option>
                    <option value="prompt">prompt</option>
                  </select>
                  <input aria-label={t("config.maxTokens", { alias })} type="number" min={1} className={`${inputCls} font-mono`} placeholder="max_tokens"
                    value={typeof m.max_tokens === "number" ? m.max_tokens : ""} onChange={(e) => setM("max_tokens", e.target.value === "" ? undefined : Number(e.target.value))} />
                  <button type="button" className={btn.icon} disabled={users.length > 0}
                    aria-label={t("config.removeAlias", { alias })}
                    title={users.length ? t("config.aliasUsed", { agents: users.join(", ") }) : t("config.removeAlias", { alias })}
                    onClick={() => put("models", Object.fromEntries(Object.entries(models).filter(([k]) => k !== alias)))}>
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </div>
                <p className="px-3 text-xs text-fg-muted">{users.length ? t("config.usedByAgents", { agents: users.join(", ") }) : t("config.unused")}</p>
                {fe(`models.${alias}`).map((e, i) => <p key={i} className="font-mono text-xs text-error">{e.message}</p>)}
              </li>
            );
          })}
        </ul>
        <p className="text-xs text-fg-muted">{t("config.aliasRule")}</p>
      </Section>
      <Section title={t("config.storage")}>
        <FormField label="type" errors={fe("storage.type")}>
          {(a) => (
            <select {...a} className={inputCls} value={stype} onChange={(e) => put("storage", { type: e.target.value, [e.target.value]: isObj(storage[e.target.value]) ? storage[e.target.value] : {} })}>
              <option value="local">local</option>
              <option value="r2">r2</option>
            </select>
          )}
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          {(STORAGE[stype] ?? []).map((k) => (
            <FormField key={k} label={k} errors={fe(`storage.${stype}.${k}`)} help={k.endsWith("_env") ? <EnvVar name={sconf[k]} env={env} /> : undefined}>
              {(a) => <input {...a} className={`${inputCls} font-mono`} value={String(sconf[k] ?? "")}
                onChange={(e) => put("storage", { ...storage, [stype]: clean(sconf, k, e.target.value) })} />}
            </FormField>
          ))}
        </div>
      </Section>
      <Section title={t("config.limits")}>
        <div className="grid grid-cols-3 gap-3">
          {LIMITS.map(([k, kind]) => (
            <FormField key={k} label={k} errors={fe(`limits.${k}`)} required={k === "run_budget_usd" || k === "run_timeout"}>
              {(a) => kind === "time" ? (
                <input {...a} className={`${inputCls} font-mono`} placeholder="1h" value={String(limits[k] ?? "")} onChange={(e) => put("limits", clean(limits, k, e.target.value))} />
              ) : (
                <input {...a} type="number" min={kind === "int" ? 1 : 0} step={kind === "int" ? 1 : 0.01} className={`${inputCls} font-mono`}
                  value={typeof limits[k] === "number" ? (limits[k] as number) : ""}
                  onChange={(e) => put("limits", clean(limits, k, e.target.value === "" ? undefined : Number(e.target.value)))} />
              )}
            </FormField>
          ))}
        </div>
      </Section>
      <Section title={t("config.webhook")}>
        <div className="grid grid-cols-2 gap-3">
          {envField("webhook.token_env", "webhook", "token_env")}
          {envField("callback.secret_env", "callback", "secret_env")}
        </div>
      </Section>
      <Section title={t("config.env")}>
        <ul className="space-y-1 text-sm">
          {Object.keys(env ?? {}).map((k) => <li key={k} className="flex gap-3"><span className="font-mono">{k}</span><EnvVar name={k} env={env} /></li>)}
        </ul>
      </Section>
      <Section title={t("config.mcp")}>
        <ul className="space-y-1">
          {project?.mcp_servers.map((s) => (
            <li key={s.name} className="text-sm">
              <span className="font-mono">{s.name}</span>
              <span className="text-fg-muted">
                {" "}{s.type}
                {s.agents && ` · ${t("config.mcpAgents")}: ${s.agents.join(", ")}`}
                {s.scenarios && ` · ${t("config.mcpScenarios")}: ${s.scenarios.join(", ")}`}
                {s.tools && ` · ${t("config.mcpTools")}: ${s.tools.join(", ")}`}
              </span>
            </li>
          ))}
          {!project?.mcp_servers.length && <li className="text-sm text-fg-muted">{t("config.noMcp")}</li>}
        </ul>
        {!!project?.mcp_servers.length && <p className="text-xs text-fg-muted">{t("config.mcpYaml")}</p>}
      </Section>
    </div>
  );
}
