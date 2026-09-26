// §2.8 Config jen ke čtení: config.yaml + MCP servery; proměnné prostředí jen ✓/✗, nikdy hodnota.
import { CodeXml } from "lucide-react";
import { useState } from "react";
import { enc, useApi } from "../api";
import { CodeView } from "../components/CodeView";
import { ErrorList, ErrorText, Loading, StatusBadge, Toggle, ValueView } from "../components/ui";
import { t } from "../i18n";
import type { FileDoc, Project } from "../types";
import { Row } from "./Agents";

type Obj = Record<string, unknown>;

function EnvVar({ name, env }: { name: unknown; env?: Record<string, boolean> }) {
  if (typeof name !== "string") return <span className="text-zinc-500">–</span>;
  const set = env?.[name];
  return (
    <span className="inline-flex items-center gap-3">
      <span className="font-mono">{name}</span>
      {set !== undefined && (
        <StatusBadge status={set ? "succeeded" : "failed"}>
          <span className="text-[13px] text-zinc-400">{set ? t("config.envSet") : t("config.envMissing")}</span>
        </StatusBadge>
      )}
    </span>
  );
}

export function ConfigTab({ name, project }: { name: string; project?: Project }) {
  const base = `/projects/${enc(name)}/files`;
  const config = useApi<FileDoc>(`${base}/config.yaml`);
  const mcp = useApi<FileDoc>(`${base}/mcp.yaml`);
  // Bez projektu (config neprošel, 422) rovnou text souboru.
  const [mode, setMode] = useState<"form" | "yaml">(project ? "form" : "yaml");
  if (config.error) return <ErrorText error={config.error} />;
  if (!config.data) return <Loading rows={6} />;
  const data = (config.data.data ?? {}) as Obj;
  const or = (data.openrouter ?? {}) as Obj;
  const models = (data.models ?? {}) as Record<string, Obj>;
  const env = project?.env;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm text-zinc-400"><span className="font-mono">config.yaml · mcp.yaml</span></h2>
        <Toggle label={t("code.mode")} value={mode} onChange={setMode}
          options={[{ key: "form", label: t("code.form") }, { key: "yaml", label: <><CodeXml className="size-3.5" aria-hidden />YAML</> }]} />
      </div>
      {mode === "yaml" ? (
        <div className="space-y-6">
          <CodeView text={config.data.text} file="config.yaml" errors={config.data.errors} />
          {mcp.data && <CodeView text={mcp.data.text} file="mcp.yaml" errors={mcp.data.errors} />}
        </div>
      ) : (
        <div className="space-y-5">
          <ErrorList errors={config.data.errors} />
          <Row label="OpenRouter">
            <div className="space-y-1">
              <div>{t("config.keyFrom")} <EnvVar name={or.api_key_env} env={env} /></div>
              {or.jev_model !== undefined && <div>{t("config.jevModel")} <span className="font-mono">{String(or.jev_model)}</span></div>}
            </div>
          </Row>
          <Row label={t("config.models")}>
            <table className="text-sm">
              <tbody>
                {Object.entries(models).map(([alias, m]) => {
                  const users = project?.agents.filter((a) => a.model === alias).length ?? 0;
                  return (
                    <tr key={alias}>
                      <td className="py-0.5 pr-6 font-mono">{alias}</td>
                      <td className="pr-6 font-mono text-zinc-300">{String(m.id ?? "")}</td>
                      <td className="pr-6 font-mono text-zinc-400">{String(m.structured_output ?? "")}</td>
                      <td className="pr-6 text-zinc-400">{m.max_tokens != null ? `max_tokens ${m.max_tokens}` : ""}</td>
                      <td className="text-zinc-400">{users ? t("config.usedByAgents", { n: users }) : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Row>
          <Row label={t("config.storage")}><ValueView value={data.storage} /></Row>
          <Row label={t("config.limits")}><ValueView value={data.limits} /></Row>
          <Row label="Webhook"><EnvVar name={(data.webhook as Obj | undefined)?.token_env} env={env} /></Row>
          <Row label="Callback"><EnvVar name={(data.callback as Obj | undefined)?.secret_env} env={env} /></Row>
          <Row label={t("config.env")}>
            <ul className="space-y-1">
              {Object.keys(env ?? {}).map((k) => <li key={k}><EnvVar name={k} env={env} /></li>)}
            </ul>
          </Row>
          <Row label={t("config.mcp")}>
            <ul className="space-y-1">
              {project?.mcp_servers.map((s) => (
                <li key={s.name} className="text-sm">
                  <span className="font-mono">{s.name}</span>
                  <span className="text-zinc-400">
                    {" "}{s.type}
                    {s.agents && ` · ${t("config.mcpAgents")}: ${s.agents.join(", ")}`}
                    {s.scenarios && ` · ${t("config.mcpScenarios")}: ${s.scenarios.join(", ")}`}
                    {s.tools && ` · ${t("config.mcpTools")}: ${s.tools.join(", ")}`}
                  </span>
                </li>
              ))}
              {!project?.mcp_servers.length && <li className="text-zinc-500">–</li>}
            </ul>
          </Row>
        </div>
      )}
    </div>
  );
}
