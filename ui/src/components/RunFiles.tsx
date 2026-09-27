// Soubory běhu (`GET …/runs/<id>/files/<cesta>`): prohlížeč textu/JSON/PNG a strom (§2.5 Soubory).
import { useEffect, useState } from "react";
import { enc, getBlob, getText, useApi } from "../api";
import { t } from "../i18n";
import { setQuery } from "../router";
import { ErrorText, Loading } from "./ui";

export const runFilePath = (project: string, runId: string, path: string) =>
  `/projects/${enc(project)}/runs/${enc(runId)}/files/${path.split("/").map(enc).join("/")}`;

const isImage = (p: string) => /\.(png|jpe?g|webp|gif)$/i.test(p);

function prettyJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

/** Obrázek jde přes fetch s tokenem → blob URL (img src by token neposlal). */
function BlobImage({ path, alt }: { path: string; alt: string }) {
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState<Error>();
  useEffect(() => {
    let u: string | undefined;
    getBlob(path).then((b) => setUrl((u = URL.createObjectURL(b))), setError);
    return () => void (u && URL.revokeObjectURL(u));
  }, [path]);
  if (error) return <ErrorText error={error} />;
  return url ? <img src={url} alt={alt} className="max-h-[60vh] rounded-control" /> : <Loading rows={1} />;
}

export function FileViewer({ project, runId, path }: { project: string; runId: string; path: string }) {
  const url = runFilePath(project, runId, path);
  const text = useApi<string>(isImage(path) ? null : url, undefined, getText);
  if (isImage(path)) return <BlobImage path={url} alt={path} />;
  if (text.error) return <ErrorText error={text.error} />;
  if (text.data === undefined) return <Loading rows={4} />;
  const body = path.endsWith(".json") ? prettyJson(text.data) : text.data;
  return <pre className="overflow-auto rounded-card bg-nested p-4 font-mono text-[13px] leading-5 whitespace-pre-wrap break-words">{body}</pre>;
}

type Tree = { [name: string]: Tree | null };

function buildTree(files: string[]): Tree {
  const root: Tree = {};
  for (const f of files) {
    const parts = f.split("/");
    let node = root;
    parts.forEach((p, i) => {
      if (i === parts.length - 1) node[p] = null;
      else node = (node[p] ??= {}) as Tree;
    });
  }
  return root;
}

function TreeNode({ tree, prefix, current }: { tree: Tree; prefix: string; current?: string }) {
  return (
    <ul className="space-y-0.5 pl-3 first:pl-0">
      {Object.entries(tree).map(([name, sub]) => {
        const path = prefix + name;
        return sub ? (
          <li key={name}>
            <details open={!!current?.startsWith(`${path}/`) || prefix === ""}>
              <summary className="cursor-pointer font-mono text-[13px] text-fg-muted">{name}/</summary>
              <TreeNode tree={sub} prefix={`${path}/`} current={current} />
            </details>
          </li>
        ) : (
          <li key={name}>
            <button type="button" onClick={() => setQuery({ soubor: path })} aria-current={current === path ? "true" : undefined}
              className={`w-full truncate rounded-control px-2 py-0.5 text-left font-mono text-[13px] ${current === path ? "bg-surface text-fg" : "text-fg-secondary hover:bg-surface-hover"}`}>
              {name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function FilesTab({ project, runId, files, current }: { project: string; runId: string; files: string[]; current?: string }) {
  return (
    <div className="grid grid-cols-[18rem_1fr] gap-6">
      <nav aria-label={t("run.tab.soubory")} className="max-h-[75vh] overflow-auto">
        <TreeNode tree={buildTree(files)} prefix="" current={current} />
      </nav>
      <div className="min-w-0">
        {current && files.includes(current) ? <FileViewer project={project} runId={runId} path={current} />
          : <p className="text-sm text-fg-muted">{current ? t("run.noFile") : t("run.pickFile")}</p>}
      </div>
    </div>
  );
}

/** report.html v sandboxovaném iframe bez skriptů (soubor je samostatný, CSS uvnitř). */
export function ReportTab({ project, runId }: { project: string; runId: string }) {
  const html = useApi<string>(runFilePath(project, runId, "report.html"), undefined, getText);
  if (html.error) return <ErrorText error={html.error} />;
  if (html.data === undefined) return <Loading rows={6} />;
  return <iframe title={t("run.reportTitle")} sandbox="" srcDoc={html.data} className="h-[80vh] w-full rounded-card bg-white" />;
}
