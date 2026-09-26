// Spuštění z GUI (§8.5, api.md „Spuštění z GUI“): formulář vstupů podle `inputs` scénáře,
// dry-run nebo ostrý běh bez callbacku; před ostrým během limity z configu a dnešní útrata.
import { useState } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { formatCost, formatMoney } from "../format";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { IoSpec, Project, Spend } from "../types";
import { FormField, ValueInput } from "./form";
import { PanelShell } from "./StepPanel";
import { btn, ErrorText } from "./ui";

/** Hodnoty k odeslání: prázdné vynechá (platí `default`), povinné bez hodnoty = chyba u pole. */
export function runInputs(specs: Record<string, IoSpec>, values: Record<string, unknown>) {
  const inputs: Record<string, unknown> = {};
  const missing: string[] = [];
  for (const [name, spec] of Object.entries(specs)) {
    const v = values[name];
    if (v === undefined || v === "") {
      if (spec.required) missing.push(name);
    } else inputs[name] = v;
  }
  return { inputs, missing };
}

export function RunPanel({ project, scenario, inputs, dirty, onClose }: {
  project: Project; scenario: string; inputs: Record<string, IoSpec> | null; dirty: boolean; onClose: () => void;
}) {
  const specs = inputs ?? {};
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(Object.entries(specs).map(([k, s]) => [k, s.default])));
  const [dry, setDry] = useState(true);
  const [missing, setMissing] = useState<string[]>([]);
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);
  const spend = useApi<Spend>(dry ? null : `/projects/${enc(project.name)}/spend`);
  const hasFile = Object.values(specs).some((s) => s.type === "file");
  const l = project.limits;

  const submit = async () => {
    const r = runInputs(specs, values);
    setMissing(r.missing);
    if (r.missing.length || hasFile) return;
    setBusy(true);
    setError(undefined);
    try {
      const res = await send<{ run_id: string }>("POST", `/projects/${enc(project.name)}/runs`,
        { scenario, inputs: r.inputs, ...(dry ? { dry_run: true } : {}) });
      navigate(href(project.name, "behy", res.run_id));
    } catch (e) {
      setError(e as ApiError);
      setBusy(false);
    }
  };

  return (
    <PanelShell id="run-panel-title" eyebrow={t("runForm.eyebrow")} title={scenario} onClose={onClose}>
      <form className="space-y-5" onSubmit={(e) => (e.preventDefault(), submit())}>
        {dirty && <p className="text-sm text-amber-400">{t("runForm.dirty")}</p>}
        {!Object.keys(specs).length && <p className="text-sm text-zinc-400">{t("runForm.noInputs")}</p>}
        {Object.entries(specs).map(([name, s]) => (
          <FormField key={name} label={name} required={s.required}
            help={[s.type, s.description, s.type === "file" ? t("runForm.fileHelp") : ""].filter(Boolean).join(" · ")}
            errors={missing.includes(name) ? [t("runForm.required")] : []}>
            {(a) => <ValueInput a11y={a} type={s.type} value={values[name]} onChange={(v) => (setValues({ ...values, [name]: v }), setMissing(missing.filter((m) => m !== name)))} />}
          </FormField>
        ))}
        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-zinc-300">{t("runForm.mode")}</legend>
          <label className="flex items-start gap-2 text-sm">
            <input type="radio" name="mode" checked={dry} onChange={() => setDry(true)} className="mt-1" />
            <span>{t("runForm.dry")}<span className="block text-xs text-zinc-400">{t("runForm.dryHelp")}</span></span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="radio" name="mode" checked={!dry} onChange={() => setDry(false)} className="mt-1" />
            <span>{t("runForm.live")}<span className="block text-xs text-zinc-400">{t("runForm.liveHelp")}</span></span>
          </label>
        </fieldset>
        {!dry && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg bg-zinc-900 p-3 text-sm" aria-label={t("runForm.limits")}>
            <dt className="text-zinc-400">{t("runForm.runBudget")}</dt>
            <dd className="font-mono">{typeof l.run_budget_usd === "number" ? `${formatMoney(l.run_budget_usd)} USD` : "–"}</dd>
            {typeof l.run_image_budget_usd === "number" && (
              <><dt className="text-zinc-400">{t("runForm.imageBudget")}</dt><dd className="font-mono">{formatMoney(l.run_image_budget_usd)} USD</dd></>
            )}
            <dt className="text-zinc-400">{t("runForm.timeout")}</dt><dd className="font-mono">{String(l.run_timeout ?? "–")}</dd>
            <dt className="text-zinc-400">{t("runForm.daily")}</dt>
            <dd className="font-mono">
              {spend.data ? `${formatCost(spend.data.total_usd)}` : "…"}
              {typeof l.daily_budget_usd === "number" ? ` / ${formatMoney(l.daily_budget_usd)} USD` : " USD"}
            </dd>
          </dl>
        )}
        {hasFile && <p className="text-sm text-amber-400">{t("runForm.fileBlocked")}</p>}
        {error && (
          <div className="space-y-1">
            <ErrorText error={error} />
            <ul className="list-inside list-disc font-mono text-xs text-rose-400">{error.details.map((d) => <li key={d}>{d}</li>)}</ul>
          </div>
        )}
        <button type="submit" className={`${btn.primary} max-sm:w-full`} disabled={busy || hasFile}>
          {busy ? t("runForm.starting") : dry ? t("runForm.submitDry") : t("runForm.submitLive")}
        </button>
      </form>
    </PanelShell>
  );
}
