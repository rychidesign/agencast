// Spuštění z GUI (§8.5, api.md „Spuštění z GUI“): formulář vstupů podle `inputs` scénáře,
// dry-run nebo ostrý běh bez callbacku; před ostrým během limity z configu a dnešní útrata.
import { TriangleAlert } from "lucide-react";
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

const Warning = ({ text }: { text: string }) => (
  <p className="flex items-start gap-2 text-sm text-warning"><TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{text}</p>
);

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
    <PanelShell id="run-panel-title" eyebrow={t("runForm.eyebrow")} title={<span className="font-mono">{scenario}</span>} onClose={onClose}>
      <form className="space-y-5" onSubmit={(e) => (e.preventDefault(), submit())}>
        {!Object.keys(specs).length && <p className="text-sm text-fg-muted">{t("runForm.noInputs")}</p>}
        {Object.entries(specs).map(([name, s]) => (
          <FormField key={name} label={name} required={s.required}
            help={[s.type, s.description, s.type === "file" ? t("runForm.fileHelp") : ""].filter(Boolean).join(" · ")}
            errors={missing.includes(name) ? [t("runForm.required")] : []}>
            {(a) => <ValueInput a11y={a} type={s.type} value={values[name]} onChange={(v) => (setValues({ ...values, [name]: v }), setMissing(missing.filter((m) => m !== name)))} />}
          </FormField>
        ))}
        <fieldset className="space-y-2">
          <legend className="mb-2 text-[11px] font-semibold tracking-wider text-fg-muted uppercase">{t("runForm.mode")}</legend>
          {([[true, "runForm.dry", "runForm.dryHelp"], [false, "runForm.live", "runForm.liveHelp"]] as const).map(([value, label, help]) => (
            <label key={label} className={`flex cursor-pointer items-start gap-3 rounded-card bg-nested p-4 text-sm ${dry === value ? "ring-2 ring-accent" : "ring-1 ring-line hover:bg-surface-hover"}`}>
              <input type="radio" name="mode" checked={dry === value} onChange={() => setDry(value)} className="mt-0.5 accent-accent" />
              <span>{t(label)}<span className="mt-1 block text-xs text-fg-muted">{t(help)}</span></span>
            </label>
          ))}
        </fieldset>
        {!dry && (
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-sm" aria-label={t("runForm.limits")}>
            <dt className="text-fg-muted">{t("runForm.runBudget")}</dt>
            <dd className="text-right font-mono">{typeof l.run_budget_usd === "number" ? `${formatMoney(l.run_budget_usd)} USD` : "–"}</dd>
            {typeof l.run_image_budget_usd === "number" && (
              <><dt className="text-fg-muted">{t("runForm.imageBudget")}</dt><dd className="text-right font-mono">{formatMoney(l.run_image_budget_usd)} USD</dd></>
            )}
            <dt className="text-fg-muted">{t("runForm.timeout")}</dt><dd className="text-right font-mono">{String(l.run_timeout ?? "–")}</dd>
            <dt className="text-fg-muted">{t("runForm.daily")}</dt>
            <dd className="text-right font-mono">
              {spend.data ? `${formatCost(spend.data.total_usd)}` : "…"}
              {typeof l.daily_budget_usd === "number" ? ` / ${formatMoney(l.daily_budget_usd)} USD` : " USD"}
            </dd>
          </dl>
        )}
        {dirty && <Warning text={t("runForm.dirty")} />}
        {hasFile && <Warning text={t("runForm.fileBlocked")} />}
        {error && (
          <div className="space-y-1">
            <ErrorText error={error} />
            <ul className="list-inside list-disc font-mono text-xs text-error">{error.details.map((d) => <li key={d}>{d}</li>)}</ul>
          </div>
        )}
        <div className="flex justify-end">
          <button type="submit" className={`${btn.primary} max-sm:w-full`} disabled={busy || hasFile}>
            {busy ? t("runForm.starting") : dry ? t("runForm.submitDry") : t("runForm.submitLive")}
          </button>
        </div>
      </form>
    </PanelShell>
  );
}
