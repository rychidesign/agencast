// Panel kroku ke čtení (§2.3): pole typu nahoře, dole sbalené Podmínka / Spolehlivost / Podrobnosti.
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { t, tOr } from "../i18n";
import { href } from "../router";
import { readBy, readsFrom, RELIABILITY } from "../steps";
import type { ErrorItem, Scenario, Step } from "../types";
import { btn, Collapsible, ErrorList, Field, ValueView } from "./ui";

export function PanelShell({ id, eyebrow, title, onClose, children }: {
  id: string; eyebrow: string; title: ReactNode; onClose: () => void; children: ReactNode;
}) {
  return (
    <aside aria-labelledby={id} className="rounded-2xl bg-zinc-800 p-5">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold tracking-wider text-zinc-400 uppercase">{eyebrow}</div>
          <h2 id={id} className="truncate text-lg font-semibold">{title}</h2>
        </div>
        <button type="button" className={btn.icon} onClick={onClose} aria-label={t("common.close")} title={t("common.close")}>
          <X className="size-4" aria-hidden />
        </button>
      </div>
      {children}
    </aside>
  );
}

const Chips = ({ ids, onSelect }: { ids: string[]; onSelect: (id: string) => void }) =>
  ids.length ? (
    <span className="flex flex-wrap gap-1.5">
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => onSelect(id)}
          className="rounded-full bg-zinc-900 px-2.5 py-0.5 font-mono text-[13px] hover:bg-zinc-700">{id}</button>
      ))}
    </span>
  ) : <span className="text-zinc-500">{t("panel.nothing")}</span>;

/** Pole typu kroku: tělo `fields[type]` a ostatní pole mimo společná (spolehlivost). */
export function TypeFields({ step }: { step: Step }) {
  const body = step.type ? step.fields[step.type] : undefined;
  const extra = Object.entries(step.fields).filter(([k]) => k !== step.type && !(RELIABILITY as readonly string[]).includes(k));
  const entries: [string, unknown][] =
    body && typeof body === "object" && !Array.isArray(body) ? Object.entries(body) : body !== undefined ? [[step.type!, body]] : [];
  if (step.type === "parallel") entries.unshift(["branches", Object.keys(step.branches ?? {})]);
  return (
    <div className="space-y-4">
      {[...entries, ...extra].map(([k, v]) => (
        <Field key={k} label={tOr(`field.${k}`, k)}><ValueView value={v} /></Field>
      ))}
    </div>
  );
}

export function StepPanel({ step, scenario, all, project, errors, onClose, onSelect, children }: {
  step: Step; scenario: Scenario; all: Step[]; project: string; errors: ErrorItem[];
  onClose: () => void; onSelect: (id: string) => void; children?: ReactNode;
}) {
  const reliability = RELIABILITY.filter((k) => step.fields[k] !== undefined);
  return (
    <PanelShell id="step-panel-title" eyebrow={t("panel.step", { n: step.nn })}
      title={<span className="font-mono">{step.type ?? "?"} · {step.id}</span>} onClose={onClose}>
      <div className="space-y-5">
        <ErrorList errors={errors} />
        {children ?? <TypeFields step={step} />}
        <div className="divide-y divide-zinc-700 border-t border-zinc-700">
          {step.type !== "output" && (
            <Collapsible title={t("panel.condition")} value={<span className="font-mono">{step.when ?? t("panel.always")}</span>}>
              <p className="font-mono text-[13px] whitespace-pre-wrap">{step.when ?? t("panel.always")}</p>
              <p className="mt-2 text-xs text-zinc-400">{t("panel.conditionHelp")}</p>
            </Collapsible>
          )}
          <Collapsible title={t("panel.reliability")}
            value={reliability.length ? reliability.join(", ") : t("panel.default")}>
            {reliability.length ? (
              <div className="space-y-3">
                {reliability.map((k) => <Field key={k} label={tOr(`field.${k}`, k)}><ValueView value={step.fields[k]} /></Field>)}
              </div>
            ) : <p className="text-sm text-zinc-400">{t("panel.default")}</p>}
          </Collapsible>
          <Collapsible title={t("panel.details")} value={<span className="font-mono">{step.id}</span>}>
            <dl className="space-y-3 text-sm">
              <div><dt className="text-[13px] font-semibold text-zinc-300">{t("panel.readsFrom")}</dt>
                <dd className="mt-1"><Chips ids={readsFrom(step)} onSelect={onSelect} /></dd></div>
              <div><dt className="text-[13px] font-semibold text-zinc-300">{t("panel.readBy")}</dt>
                <dd className="mt-1"><Chips ids={readBy(all, step.id)} onSelect={onSelect} /></dd></div>
            </dl>
            <a className="mt-3 inline-block text-sm underline"
              href={href(project, "scenare", scenario.name, { krok: step.id, rezim: "yaml" })}>{t("panel.openYaml")}</a>
          </Collapsible>
        </div>
      </div>
    </PanelShell>
  );
}

export function HeaderPanel({ scenario, errors, onClose }: { scenario: Scenario; errors: ErrorItem[]; onClose: () => void }) {
  return (
    <PanelShell id="step-panel-title" eyebrow={t("panel.header")} title={scenario.description} onClose={onClose}>
      <div className="space-y-4">
        <ErrorList errors={errors} />
        <Field label={t("panel.inputs")}><ValueView value={scenario.inputs ?? {}} /></Field>
        <Field label={t("panel.outputs")}><ValueView value={scenario.outputs ?? {}} /></Field>
        <Field label="callable"><ValueView value={scenario.callable} /></Field>
      </div>
    </PanelShell>
  );
}
