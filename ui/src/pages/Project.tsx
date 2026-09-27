// §2.2 Projekt: hlavička sekce (Scénáře · Agenti · Běhy · Skilly · Config); navigace projektu je v sidebaru (Shell).
import { useState, type ReactNode } from "react";
import { enc, useApi } from "../api";
import { PageHeader } from "../components/PageHeader";
import { ErrorList, ErrorText, Loading, StatusChip, type MenuItem } from "../components/ui";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { ErrorItem, Project } from "../types";
import { AgentsTab, SkillsTab } from "./Agents";
import { ConfigTab } from "./Config";
import { RunsTab } from "./Runs";
import { ScenariosTab } from "./Scenarios";

/** Všechny chyby validace projektu (projekt + soubory). */
export const allErrors = (p: Project): ErrorItem[] => [
  ...p.errors,
  ...[...p.scenarios, ...p.agents, ...p.skills].flatMap((x) => x.errors),
];

/** Odkaz z chyby na soubor a krok (`file` = cesta ve `workflows/`). */
export function errorHref(project: string, e: ErrorItem): string | undefined {
  const m = /^(scenarios|agents|skills)\/([^/]+?)(?:\.yaml|\.md|\/SKILL\.md)$/.exec(e.file ?? "");
  if (m?.[1] === "scenarios") return href(project, "scenare", m[2], { krok: e.step });
  if (m?.[1] === "agents") return href(project, "agenti", m[2]);
  if (m?.[1] === "skills") return href(project, "skilly", m[2]);
  if (e.file === "config.yaml" || e.file === "mcp.yaml") return href(project, "config");
  return undefined;
}

/** Hlavička sekce (G1): záložka do ní doplní akce, ⋯ a druhý řádek; „Načíst znovu“ je v ⋯ vždy první. */
export type SectionHeader = (x?: {
  description?: ReactNode; actions?: ReactNode; menu?: MenuItem[]; menuLabel?: string; children?: ReactNode;
}) => ReactNode;

export function ProjectPage({ project, tab, item }: { project: string; tab: Tab; item?: string }) {
  const [gen, setGen] = useState(0);
  const detail = useApi<Project>(`/projects/${enc(project)}`);
  const reload = () => (detail.reload(), setGen(gen + 1));
  const p = detail.data;
  const errors = p ? allErrors(p) : [];
  const header: SectionHeader = (x = {}) => (
    <>
      <PageHeader title={t(`project.tab.${tab}`)} description={x.description} actions={x.actions} menuLabel={x.menuLabel}
        menu={[{ label: t("common.reload"), onSelect: reload }, ...(x.menu ?? [])]}
        meta={errors.length > 0 && (
          <details className="relative text-sm">
            <summary className="cursor-pointer list-none rounded-full [&::-webkit-details-marker]:hidden">
              <StatusChip status="failed">{t("validation.count", { n: errors.length })}</StatusChip>
            </summary>
            <div className="absolute z-20 mt-2 w-[36rem] max-w-[calc(100vw-2rem)] rounded-card bg-surface p-4 ring-1 ring-line">
              <ErrorList errors={errors} hrefFor={(e) => errorHref(project, e)} />
            </div>
          </details>
        )}>
        {x.children}
      </PageHeader>
      {detail.error?.status === 422 && (
        <div role="alert" className="mb-6 space-y-2 rounded-card bg-surface p-4">
          <p className="text-sm text-error">{t("server.config", { error: detail.error.message })}</p>
          <ul className="list-inside list-disc font-mono text-[13px] text-fg-secondary">
            {detail.error.details.map((d) => <li key={d}>{d}</li>)}
          </ul>
          {tab !== "config" && <a className="text-sm underline" href={href(project, "config")}>{t("server.openConfig")}</a>}
        </div>
      )}
      {detail.error && detail.error.status !== 422 && detail.error.status !== 0 && <ErrorText error={detail.error} />}
    </>
  );
  // Hlavičku kreslí záložka, jakmile má data (kvůli Uložit a přepínači); do té doby ji kreslí stránka.
  const tabOwnsHeader = tab === "config" ? !!(p || detail.error) : tab !== "behy" && !!p;
  return (
    <div key={gen}>
      {!tabOwnsHeader && header()}
      {tab === "config" && (p || detail.error) && <ConfigTab name={project} project={p} header={header} onChanged={detail.reload} />}
      {tab === "behy" && <RunsTab project={project} />}
      {!p ? (
        tab !== "behy" && !detail.error && <Loading rows={4} />
      ) : (
        <>
          {tab === "scenare" && <ScenariosTab project={p} header={header} onChanged={detail.reload} />}
          {tab === "agenti" && <AgentsTab project={p} header={header} selected={item} onChanged={detail.reload} />}
          {tab === "skilly" && <SkillsTab project={p} header={header} selected={item} onChanged={detail.reload} />}
        </>
      )}
    </div>
  );
}
