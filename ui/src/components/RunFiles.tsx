// Soubory běhu (`GET …/runs/<id>/files/<cesta>`): prohlížeč textu/JSON/PNG a strom (§2.5 Soubory).
import { Braces, Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { enc, getBlob, getText, useApi } from "../api";
import { t } from "../i18n";
import { setQuery } from "../router";
import { btn, ErrorText, Loading } from "./ui";

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

/** Blok kódu (fidelity §2 „CodeViewer“): hlavička 40 px s názvem a čipem, tělo `nested` s čísly řádků, patička s Kopírovat.
 *  ponytail: lokální náhrada za `CodeBlock` z vlny E2 — po sloučení nahradit jejím. */
export function CodeBlock({ name, text, badge, foot }: { name: string; text: string; badge: string; foot?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <figure className="overflow-hidden rounded-card ring-1 ring-line">
      <figcaption className="flex h-10 items-center gap-2 px-4">
        <Braces className="size-4 shrink-0 text-fg-secondary" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-[13px]" title={name}>{name}</span>
        <span className="shrink-0 rounded-md px-2 py-0.5 font-mono text-[11px] text-fg-secondary ring-1 ring-line">{badge}</span>
      </figcaption>
      <pre className="max-h-[60vh] overflow-auto bg-nested py-3 font-mono text-[13px] leading-6"><code className="table w-full">
        {text.split("\n").map((l, i) => (
          <span key={i} className="table-row">
            <span className="table-cell w-10 pr-4 text-right text-xs text-fg-muted select-none" aria-hidden>{i + 1}</span>
            <span className="table-cell pr-4 whitespace-pre-wrap break-words">{l}</span>
          </span>
        ))}
      </code></pre>
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <span className="truncate font-mono text-xs text-fg-muted">{foot ?? t("code.readOnly")}</span>
        <button type="button" className={btn.secondary} onClick={copy}>
          {done ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{done ? t("common.copied") : t("common.copy")}
        </button>
      </div>
    </figure>
  );
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

export function FileViewer({ project, runId, path, name = path }: { project: string; runId: string; path: string; name?: string }) {
  const url = runFilePath(project, runId, path);
  const text = useApi<string>(isImage(path) ? null : url, undefined, getText);
  if (isImage(path)) return <BlobImage path={url} alt={path} />;
  if (text.error) return <ErrorText error={text.error} />;
  if (text.data === undefined) return <Loading rows={4} />;
  const json = path.endsWith(".json");
  const ext = path.split(".").pop()!.toUpperCase();
  return <CodeBlock name={name} text={json ? prettyJson(text.data) : text.data} badge={t("code.readOnlyBadge")} foot={`${ext} · ${t("code.readOnly")}`} />;
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
              <summary className="flex h-9 cursor-pointer items-center px-2 font-mono text-[13px] text-fg-muted">{name}/</summary>
              <TreeNode tree={sub} prefix={`${path}/`} current={current} />
            </details>
          </li>
        ) : (
          <li key={name}>
            <button type="button" onClick={() => setQuery({ soubor: path })} title={path} aria-current={current === path ? "true" : undefined}
              className={`flex h-9 w-full items-center truncate rounded-control px-3 text-left font-mono text-[13px] ${current === path ? "bg-surface-active text-fg" : "text-fg-secondary hover:bg-surface-hover"}`}>
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
    <div className="grid grid-cols-[18rem_1fr] items-start gap-6">
      <nav aria-label={t("run.tab.soubory")} className="max-h-[75vh] overflow-auto rounded-panel bg-surface p-3">
        <TreeNode tree={buildTree(files)} prefix="" current={current} />
      </nav>
      <div className="min-w-0 rounded-panel bg-surface p-6">
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
