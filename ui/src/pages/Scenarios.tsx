// §2.2 Záložka Scénáře: mřížka karet scénářů.
import { ArrowUpRight, Plus } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send } from "../api";
import { Modal, NameDialog } from "../components/form";
import { LastRun } from "../components/RunBadge";
import { IconChain } from "../components/TypeIcon";
import { btn, ErrorList, Menu, StatusChip } from "../components/ui";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { ErrorItem, Project, ScenarioSummary } from "../types";
import type { SectionHeader } from "./Project";

/** Příkaz spuštění z CLI; povinné vstupy bez `default` jako `-i jmeno=…`. */
export function runCommand(root: string, s: ScenarioSummary): string {
  const inputs = Object.entries(s.inputs ?? {})
    .filter(([, v]) => v.required && v.default === undefined)
    .map(([k]) => ` -i ${k}=…`)
    .join("");
  return `agencast --project ${root} run ${s.name}${inputs}`;
}

export function ScenariosTab({ project, header, onChanged }: { project: Project; header: SectionHeader; onChanged: () => void }) {
  const [creating, setCreating] = useState(false);
  const [checked, setChecked] = useState<{ name: string; errors: ErrorItem[] | string }>();
  const base = `/projects/${enc(project.name)}`;
  /** Validovat (⋯): `POST …/validate` bez těla = projekt jak je na disku, chyby jen tohoto souboru. */
  const validate = async (name: string) => {
    setChecked({ name, errors: t("common.loading") });
    try {
      const r = await send<{ errors: ErrorItem[] }>("POST", `${base}/validate`, {});
      setChecked({ name, errors: r.errors.filter((e) => e.file === `scenarios/${name}.yaml`) });
    } catch (e) {
      setChecked({ name, errors: (e as ApiError).message });
    }
  };
  return (
    <>
      {header({ actions: (
        <button type="button" onClick={() => setCreating(true)} className={btn.primary}>
          <Plus className="size-4" aria-hidden />{t("scenarios.new")}
        </button>
      ) })}
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-5">
        {!project.scenarios.length && <li>
          <button type="button" onClick={() => setCreating(true)}
            className="flex min-h-[290px] w-full flex-col items-center justify-center gap-3 rounded-panel border border-dashed border-line p-6 text-fg-secondary hover:bg-surface-hover hover:text-fg">
            <Plus className="size-6" aria-hidden />
            <span className="text-sm">{t("scenarios.new")}</span>
          </button>
        </li>}
        {project.scenarios.map((s) => (
          <ScenarioCard key={s.name} project={project} scenario={s} onValidate={() => void validate(s.name)} />
        ))}
      </ul>
      {creating && (
        <NameDialog title={t("scenarios.new")} withDescription taken={project.scenarios.map((s) => s.name)} onCancel={() => setCreating(false)}
          onSubmit={async (name, description) => {
            await send("POST", `${base}/scenarios`, { name, ...(description ? { description } : {}) });
            setCreating(false);
            onChanged();
            navigate(href(project.name, "scenare", name, { krok: "_hlavicka" }));
          }} />
      )}
      {checked && (
        <Modal title={t("scenarios.validated", { name: checked.name })} onCancel={() => setChecked(undefined)} actions={[]} cancelLabel={t("common.close")}>
          <div aria-live="polite">
            {typeof checked.errors === "string" ? <p>{checked.errors}</p>
              : checked.errors.length ? <ErrorList errors={checked.errors} hrefFor={(e) => e.step ? href(project.name, "scenare", checked.name, { krok: e.step }) : undefined} />
              : <StatusChip status="succeeded">{t("scenarios.valid")}</StatusChip>}
          </div>
        </Modal>
      )}
    </>
  );
}

function ScenarioCard({ project, scenario: s, onValidate }: { project: Project; scenario: ScenarioSummary; onValidate: () => void }) {
  const open = href(project.name, "scenare", s.name);
  const agents = project.links.scenario_agent.filter(([sc]) => sc === s.name).map(([, a]) => a);
  const menu = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("scenarios.runsOf"), onSelect: () => navigate(href(project.name, "behy", undefined, { scenar: s.name })) },
    { label: t("scenarios.copyRun"), onSelect: () => navigator.clipboard.writeText(runCommand(project.root, s)) },
    { label: t("scenarios.validate"), onSelect: onValidate },
  ];
  return (
    <li data-testid={`scenario-card-${s.name}`} className="relative flex min-h-[290px] flex-col gap-5 rounded-panel bg-surface p-6 hover:bg-surface-hover">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1 overflow-hidden"><IconChain types={s.types} /></div>
        <div className="relative z-10 -mr-2"><Menu items={menu} label={t("common.menuFor", { name: s.name })} /></div>
      </div>
      <div className="space-y-2">
        <h2 className="text-xl leading-snug font-semibold break-words">
          <a href={open} className="after:absolute after:inset-0 after:rounded-panel">{s.name}</a>
        </h2>
        {s.description && <p className="line-clamp-2 text-sm text-fg-secondary" title={s.description}>{s.description}</p>}
        <p className="flex flex-wrap items-center gap-2 font-mono text-xs text-fg-muted">
          <span>{[t("count.steps", { n: s.steps_count }), agents.length ? t("count.agents", { n: agents.length }) : ""].filter(Boolean).join(" · ")}</span>
          {s.callable && <span className="rounded-full bg-nested px-2 py-0.5 text-type">{t("scenario.callable")}</span>}
        </p>
      </div>
      <div className="mt-auto flex items-center justify-between gap-3">
        <span className="relative z-10 min-w-0">
          {s.errors.length > 0 ? (
            <StatusChip status="failed">{t("validation.count", { n: s.errors.length })}</StatusChip>
          ) : (
            <LastRun run={s.last_run} />
          )}
        </span>
        {/* celá karta je odkaz (titul); „Otevřít ↗“ je jen vizuální výzva, ne druhý odkaz */}
        <span className="inline-flex shrink-0 items-center gap-2 text-sm font-medium text-fg" aria-hidden>
          {t("common.open")}<ArrowUpRight className="size-4 text-fg-secondary" />
        </span>
      </div>
    </li>
  );
}
