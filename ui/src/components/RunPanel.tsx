// Spuštění z GUI (§8.5, api.md „Spuštění z GUI“): formulář vstupů podle `inputs` scénáře,
// dry-run nebo ostrý běh bez callbacku; před ostrým během limity z configu a dnešní útrata.
import { Play, TriangleAlert, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ApiError, enc, send, useApi } from "../api";
import { formatMoney, formatSpend } from "../format";
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
  <p className="flex items-start gap-3 rounded-control bg-warning/10 p-3 text-xs leading-[19px] text-warning"><TriangleAlert className="size-4 shrink-0" aria-hidden />{text}</p>
);

// návrh 10 (změřeno z .pen): eyebrow 11 verzálky, karty režimu `nested` r8 p14, řádky limitů 32 px (12 px), mezery 20
const eyebrow = "text-[11px] leading-[17px] tracking-[0.08em] text-fg-muted uppercase";

/** Řádek limitu: štítek 12 `fg-secondary` vlevo, hodnota mono 12 vpravo, oddělovač pod. */
const Limit = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex min-h-8 items-center justify-between gap-3 border-b border-line py-1.5 text-xs">
    <dt className="text-fg-secondary">{label}</dt>
    <dd className="text-right font-mono text-fg tabular-nums">{children}</dd>
  </div>
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
        <fieldset className="space-y-3">
          <legend className={`mb-3 ${eyebrow}`}>{t("runForm.mode")}</legend>
          {([[true, "runForm.dry", "runForm.dryHelp"], [false, "runForm.live", "runForm.liveHelp"]] as const).map(([value, label, help]) => (
            <label key={label} className={`block cursor-pointer space-y-1 rounded-control bg-nested p-3.5 ${dry === value ? "ring-1 ring-accent" : "hover:bg-surface-hover"}`}>
              <span className="flex min-h-11 items-center gap-2.5 text-[13px] text-fg-secondary">
                <input type="radio" name="mode" checked={dry === value} onChange={() => setDry(value)} />{t(label)}
              </span>
              <span className="block text-xs leading-[18px] text-fg-secondary">{t(help)}</span>
            </label>
          ))}
        </fieldset>
        {!dry && (
          <div>
            <p className={`mb-2 ${eyebrow}`} aria-hidden>{t("runForm.limitsTitle")}</p>
            <dl aria-label={t("runForm.limits")}>
              <Limit label={t("runForm.runBudget")}>{typeof l.run_budget_usd === "number" ? `${formatMoney(l.run_budget_usd)} USD` : "–"}</Limit>
              {typeof l.run_image_budget_usd === "number" && <Limit label={t("runForm.imageBudget")}>{formatMoney(l.run_image_budget_usd)} USD</Limit>}
              <Limit label={t("runForm.timeout")}>{String(l.run_timeout ?? "–")}</Limit>
              <Limit label={t("runForm.daily")}>
                {spend.data ? formatSpend(spend.data.total_usd) : "…"}
                {typeof l.daily_budget_usd === "number" ? ` / ${formatMoney(l.daily_budget_usd)} USD` : " USD"}
              </Limit>
            </dl>
          </div>
        )}
        {dirty && <Warning text={t("runForm.dirty")} />}
        {hasFile && <Warning text={t("runForm.fileBlocked")} />}
        {error && (
          <div className="space-y-1">
            <ErrorText error={error} />
            <ul className="list-inside list-disc font-mono text-xs text-error">{error.details.map((d) => <li key={d}>{d}</li>)}</ul>
          </div>
        )}
        <div className="flex justify-end gap-3 max-sm:flex-col-reverse">
          <button type="button" className={`${btn.secondary} max-sm:w-full`} onClick={onClose}>
            <X className="size-4" aria-hidden />{t("common.cancel")}
          </button>
          <button type="submit" className={`${btn.primary} max-sm:w-full`} disabled={busy || hasFile}>
            <Play className="size-4" aria-hidden />{busy ? t("runForm.starting") : dry ? t("runForm.submitDry") : t("runForm.submitLive")}
          </button>
        </div>
      </form>
    </PanelShell>
  );
}
