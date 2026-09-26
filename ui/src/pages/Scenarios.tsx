// §2.2 Záložka Scénáře: mřížka karet scénářů.
import { Plus } from "lucide-react";
import { useState } from "react";
import { ApiError, enc, send, useApi, type Saved } from "../api";
import { Modal, NameDialog } from "../components/form";
import { LastRun } from "../components/RunBadge";
import { IconChain } from "../components/TypeIcon";
import { EmptyState, ErrorList, Menu, Skeleton, StatusChip } from "../components/ui";
import { formatWhen, runScenario, runStartedAt, utcTitle } from "../format";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { ErrorItem, Project, RunListItem, Scenario, ScenarioSummary } from "../types";

/** Příkaz spuštění z CLI; povinné vstupy bez `default` jako `-i jmeno=…`. */
export function runCommand(root: string, s: ScenarioSummary): string {
  const inputs = Object.entries(s.inputs ?? {})
    .filter(([, v]) => v.required && v.default === undefined)
    .map(([k]) => ` -i ${k}=…`)
    .join("");
  return `agencast --project ${root} run ${s.name}${inputs}`;
}

export function ScenariosTab({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const runs = useApi<{ runs: RunListItem[] }>(`/projects/${enc(project.name)}/runs`);
  const [creating, setCreating] = useState(false);
  const [checked, setChecked] = useState<{ name: string; errors: ErrorItem[] | string }>();
  const lastRun = (name: string) => runs.data?.runs.find((r) => r.status !== "queued" && runScenario(r) === name);
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
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
        <li>
          <button type="button" onClick={() => setCreating(true)}
            className="flex min-h-52 w-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-600 p-5 text-zinc-300 hover:bg-zinc-800/40 hover:text-zinc-100">
            <Plus className="size-6" aria-hidden />
            <span className="text-sm">{t("scenarios.new")}</span>
          </button>
        </li>
        {project.scenarios.map((s) => (
          <ScenarioCard key={s.name} project={project} scenario={s} lastRun={runs.data ? lastRun(s.name) ?? null : undefined} onValidate={() => void validate(s.name)} />
        ))}
        {!project.scenarios.length && <li><EmptyState text={t("scenarios.empty")} /></li>}
      </ul>
      {creating && (
        <NameDialog title={t("scenarios.new")} withDescription taken={project.scenarios.map((s) => s.name)} onCancel={() => setCreating(false)}
          onSubmit={async (name, description) => {
            const r = await send<{ etag: string }>("POST", `${base}/scenarios`, { name });
            // popis do hlavičky hned (šablona má zástupný); když neprojde, scénář už existuje a popis jde změnit v editoru
            if (description) await send<Saved>("PUT", `${base}/scenarios/${enc(name)}`, { etag: r.etag, fields: { description } }).catch(() => undefined);
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

function ScenarioCard({ project, scenario: s, lastRun, onValidate }: {
  project: Project; scenario: ScenarioSummary; lastRun: RunListItem | null | undefined; onValidate: () => void;
}) {
  // ponytail: jeden GET na scénář kvůli řetězci ikon; až API dá typy kroků v přehledu, odpadne (nalezy-api.md).
  const detail = useApi<Scenario>(`/projects/${enc(project.name)}/scenarios/${enc(s.name)}`);
  const open = href(project.name, "scenare", s.name);
  const agents = project.links.scenario_agent.filter(([sc]) => sc === s.name).map(([, a]) => a);
  const nIn = Object.keys(s.inputs ?? {}).length;
  const nOut = Object.keys(s.outputs ?? {}).length;
  const meta = [
    t("count.steps", { n: s.steps_count }),
    agents.join(", "),
    nIn ? t("count.inputs", { n: nIn }) : "",
    nOut ? t("count.outputs", { n: nOut }) : "",
    s.callable ? t("scenario.callable") : "",
  ].filter(Boolean);
  const menu = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("scenarios.runsOf"), onSelect: () => navigate(href(project.name, "behy", undefined, { scenar: s.name })) },
    { label: t("scenarios.copyRun"), onSelect: () => navigator.clipboard.writeText(runCommand(project.root, s)) },
    { label: t("scenarios.validate"), onSelect: onValidate },
  ];
  const when = lastRun ? lastRun.finished_at ?? runStartedAt(lastRun) : null;
  return (
    <li className="relative flex min-h-52 flex-col rounded-xl bg-zinc-800/60 p-5 hover:bg-zinc-800">
      <div className="flex flex-wrap items-center gap-3">
        {detail.data ? <IconChain types={detail.data.steps.map((st) => st.type)} /> : <Skeleton className="h-8 w-40" />}
        <div className="relative z-10 ml-auto flex items-center gap-1 whitespace-nowrap">
          {s.errors.length > 0 ? (
            <StatusChip status="failed">{t("validation.count", { n: s.errors.length })}</StatusChip>
          ) : (
            lastRun !== undefined && <LastRun run={lastRun ?? undefined} />
          )}
          <Menu items={menu} label={t("common.menuFor", { name: s.name })} />
        </div>
      </div>
      <h2 className="mt-4 text-lg leading-snug font-semibold">
        <a href={open} className="after:absolute after:inset-0 after:rounded-xl">{s.description || s.name}</a>
      </h2>
      <p className="mt-1 text-[13px] text-zinc-400">{meta.join(" · ")}</p>
      <div className="mt-auto flex items-center justify-between pt-4 text-[13px] text-zinc-400">
        <span className="font-mono">{s.name}.yaml</span>
        <span title={utcTitle(when)}>{lastRun === undefined ? "" : when ? formatWhen(when) : t("runs.none")}</span>
      </div>
    </li>
  );
}
