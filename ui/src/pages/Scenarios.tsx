// §2.2 Záložka Scénáře: mřížka karet scénářů.
import { Plus } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send } from "../api";
import { Modal, NameDialog } from "../components/form";
import { LastRun } from "../components/RunBadge";
import { IconChain } from "../components/TypeIcon";
import { btn, ErrorList, Menu, StatusChip } from "../components/ui";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { ErrorItem, Project, ScenarioSummary } from "../types";

/** Příkaz spuštění z CLI; povinné vstupy bez `default` jako `-i jmeno=…`. */
export function runCommand(root: string, s: ScenarioSummary): string {
  const inputs = Object.entries(s.inputs ?? {})
    .filter(([, v]) => v.required && v.default === undefined)
    .map(([k]) => ` -i ${k}=…`)
    .join("");
  return `agencast --project ${root} run ${s.name}${inputs}`;
}

export function ScenariosTab({ project, onChanged }: { project: Project; onChanged: () => void }) {
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
      <div className="mb-4 flex justify-end">
        <button type="button" onClick={() => setCreating(true)} className={btn.primary}>
          <Plus className="size-4" aria-hidden />{t("scenarios.new")}
        </button>
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-4">
        {!project.scenarios.length && <li>
          <button type="button" onClick={() => setCreating(true)}
            className="flex min-h-52 w-full flex-col items-center justify-center gap-3 rounded-card border border-dashed border-line p-5 text-fg-secondary hover:bg-surface-hover hover:text-fg">
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
    <li data-testid={`scenario-card-${s.name}`} className="relative flex min-h-52 flex-col rounded-card bg-surface p-5 hover:bg-surface-hover">
      <div className="flex flex-wrap items-center gap-3">
        <IconChain types={s.types} />
        <div className="relative z-10 ml-auto flex items-center gap-1 whitespace-nowrap">
          {s.errors.length > 0 ? (
            <StatusChip status="failed">{t("validation.count", { n: s.errors.length })}</StatusChip>
          ) : (
            <LastRun run={s.last_run} />
          )}
          <Menu items={menu} label={t("common.menuFor", { name: s.name })} />
        </div>
      </div>
      <h2 className="mt-4 text-lg leading-snug font-semibold">
        <a href={open} className="after:absolute after:inset-0 after:rounded-card">{s.name}</a>
      </h2>
      {s.description && <p className="mt-1 text-sm text-fg-secondary">{s.description}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-4 text-[13px] text-fg-muted">
        <span>{[t("count.steps", { n: s.steps_count }), agents.join(", ")].filter(Boolean).join(" · ")}</span>
        {s.callable && <span className="rounded-full bg-nested px-2 py-0.5">{t("scenario.callable")}</span>}
      </div>
    </li>
  );
}
