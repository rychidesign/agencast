// §2.7 Agenti a §2.9 Skilly — seznam vlevo, obsah vpravo, jen ke čtení.
import { CodeXml } from "lucide-react";
import { useState, type ReactNode } from "react";
import { enc, useApi } from "../api";
import { CodeView } from "../components/CodeView";
import { EmptyState, ErrorList, ErrorText, Loading, Toggle, ValueView } from "../components/ui";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { ErrorItem, FileDoc, Project } from "../types";

export function MasterDetail({ project, tab, items, selected, children }: {
  project: Project; tab: Tab; items: { name: string; errors: ErrorItem[] }[]; selected?: string;
  children: (name: string) => ReactNode;
}) {
  const current = selected ?? items[0]?.name;
  if (!items.length) return <EmptyState text={t(`${tab}.empty`)} />;
  return (
    <div className="grid grid-cols-[14rem_1fr] gap-8">
      <nav aria-label={t(`project.tab.${tab}`)}>
        <ul className="space-y-0.5">
          {items.map((it) => (
            <li key={it.name}>
              <a href={href(project.name, tab, it.name)} aria-current={it.name === current ? "page" : undefined}
                className={`flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm ${it.name === current ? "bg-zinc-800 text-zinc-100" : "text-zinc-300 hover:bg-zinc-800/60"}`}>
                <span className="truncate font-mono">{it.name}</span>
                {it.errors.length > 0 && <span className="shrink-0 text-xs text-rose-400">✗ {t("validation.count", { n: it.errors.length })}</span>}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <section aria-live="polite">{current && children(current)}</section>
    </div>
  );
}

/** Soubor z `files/` s přepínačem Form | `<>` Markdown (u agentů a skillů). */
function FileView({ project, path, title, form }: {
  project: string; path: string; title: string; form: (doc: FileDoc) => ReactNode;
}) {
  const doc = useApi<FileDoc>(`/projects/${enc(project)}/files/${path}`);
  const [mode, setMode] = useState<"form" | "text">("form");
  if (doc.error) return <ErrorText error={doc.error} />;
  if (!doc.data) return <Loading rows={5} />;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-mono text-lg font-semibold">{title}</h2>
        <Toggle label={t("code.mode")} value={mode} onChange={setMode}
          options={[{ key: "form", label: t("code.form") }, { key: "text", label: <><CodeXml className="size-3.5" aria-hidden />{t("code.markdown")}</> }]} />
      </div>
      {mode === "text" ? (
        <CodeView text={doc.data.text} file={path} errors={doc.data.errors} />
      ) : (
        <>
          <ErrorList errors={doc.data.errors} />
          {form(doc.data)}
        </>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-baseline gap-4 text-sm">
      <div className="text-[13px] font-semibold text-zinc-400">{label}</div>
      <div>{children}</div>
    </div>
  );
}

const Chip = ({ children, muted }: { children: ReactNode; muted?: boolean }) => (
  <span className={`inline-flex items-center rounded-full bg-zinc-800 px-2.5 py-0.5 font-mono text-[13px] ${muted ? "text-zinc-500" : "text-zinc-200"}`}>{children}</span>
);

/** Instrukce / text skillu jako čitelný text (Markdown se nevykresluje, jen zachová řádky). */
const Body = ({ title, text }: { title: string; text: string }) => (
  <div className="space-y-2">
    <h3 className="text-[13px] font-semibold text-zinc-400">{title}</h3>
    <div className="rounded-xl bg-zinc-800/60 p-4 text-sm leading-6 whitespace-pre-wrap">{text.trim()}</div>
  </div>
);

export function AgentsTab({ project, selected }: { project: Project; selected?: string }) {
  return (
    <MasterDetail project={project} tab="agenti" items={project.agents} selected={selected}>
      {(name) => {
        const a = project.agents.find((x) => x.name === name);
        const usedBy = project.links.scenario_agent.filter(([, ag]) => ag === name).map(([s]) => s);
        const servers = project.mcp_servers;
        return (
          <FileView key={name} project={project.name} path={`agents/${name}.md`} title={name} form={(doc) => {
            const fm = doc.frontmatter ?? {};
            const mcp = Array.isArray(fm.mcp) ? (fm.mcp as string[]) : [];
            const tools = (fm.tools ?? {}) as Record<string, string[]>;
            return (
              <div className="space-y-4">
                <Row label={t("agent.description")}>{a?.description ?? String(fm.description ?? "")}</Row>
                <Row label={t("agent.model")}>
                  <span className="font-mono">{a?.model ?? String(fm.model ?? "")}</span>
                  {a?.model_id && <span className="ml-3 font-mono text-zinc-400">{a.model_id}</span>}
                </Row>
                <Row label={t("agent.skills")}>
                  <span className="flex flex-wrap gap-1.5">
                    {(a?.skills ?? []).map((s) => <a key={s} href={href(project.name, "skilly", s)}><Chip>{s}</Chip></a>)}
                    {!a?.skills.length && <span className="text-zinc-500">–</span>}
                  </span>
                </Row>
                <Row label={t("agent.mcp")}>
                  <ul className="space-y-1">
                    {servers.map((s) => {
                      const allowed = s.agents?.includes(name);
                      const on = mcp.includes(s.name);
                      return (
                        <li key={s.name} className={allowed ? "" : "text-zinc-500"}>
                          <span className="font-mono">{on ? "☑" : "☐"} {s.name}</span>
                          {on && tools[s.name] && <span className="ml-2 font-mono text-[13px] text-zinc-400">{tools[s.name].join(", ")}</span>}
                          {!allowed && <span className="ml-2 text-[13px]">{t("agent.mcpNotAllowed")}</span>}
                        </li>
                      );
                    })}
                    {!servers.length && <li className="text-zinc-500">–</li>}
                  </ul>
                </Row>
                <Row label={t("agent.limits")}><ValueView value={fm.limits} /></Row>
                <Body title={t("agent.instructions")} text={doc.body ?? ""} />
                <Row label={t("agent.usedBy")}>
                  <span className="flex flex-wrap gap-2">
                    {usedBy.map((s) => <a key={s} className="font-mono underline" href={href(project.name, "scenare", s)}>{s}</a>)}
                    {!usedBy.length && <span className="text-zinc-500">–</span>}
                  </span>
                </Row>
              </div>
            );
          }} />
        );
      }}
    </MasterDetail>
  );
}

export function SkillsTab({ project, selected }: { project: Project; selected?: string }) {
  return (
    <MasterDetail project={project} tab="skilly" items={project.skills} selected={selected}>
      {(name) => {
        const s = project.skills.find((x) => x.name === name);
        const usedBy = project.links.agent_skill.filter(([, sk]) => sk === name).map(([a]) => a);
        return (
          <FileView key={name} project={project.name} path={`skills/${name}/SKILL.md`} title={name} form={(doc) => (
            <div className="space-y-4">
              <Row label={t("agent.description")}>{s?.description}</Row>
              <Body title={t("skill.text")} text={doc.body ?? ""} />
              <Row label={t("skill.usedBy")}>
                <span className="flex flex-wrap gap-2">
                  {usedBy.map((a) => <a key={a} className="font-mono underline" href={href(project.name, "agenti", a)}>{a}</a>)}
                  {!usedBy.length && <span className="text-zinc-500">–</span>}
                </span>
              </Row>
            </div>
          )} />
        );
      }}
    </MasterDetail>
  );
}

export { Row, Chip };
