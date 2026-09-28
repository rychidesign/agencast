// Soubory běhu (`GET …/runs/<id>/files/<cesta>`): prohlížeč textu/JSON/PNG a strom (§2.5 Soubory).
import { ChevronDown, Eye, File, Folder } from "lucide-react";
import { useEffect, useState } from "react";
import { enc, getBlob, getText, useApi } from "../api";
import { t } from "../i18n";
import { setQuery } from "../router";
import { Markdown } from "./Markdown";
import { CodeBlock, CodeHead, ErrorText, Loading, Toggle } from "./ui";

export const runFilePath = (project: string, runId: string, path: string) =>
  `/projects/${enc(project)}/runs/${enc(runId)}/files/${path.split("/").map(enc).join("/")}`;

const isImage = (p: string) => /\.(png|jpe?g|webp|gif)$/i.test(p);
const isMarkdown = (p: string) => /\.md$/i.test(p);

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

export function FileViewer({ project, runId, path, name = path, preview = false }: {
  project: string; runId: string; path: string; name?: string; /** Markdown vykreslený (návrh 13 „Náhled“). */ preview?: boolean;
}) {
  const url = runFilePath(project, runId, path);
  const text = useApi<string>(isImage(path) ? null : url, undefined, getText);
  if (isImage(path)) return <BlobImage path={url} alt={path} />;
  if (text.error) return <ErrorText error={text.error} />;
  if (text.data === undefined) return <Loading rows={4} />;
  if (preview && isMarkdown(path)) return (
    <section className="overflow-hidden rounded-panel bg-surface ring-1 ring-line">
      <CodeHead icon={Eye} name={name} chip={t("files.preview")} />
      <div className="p-6"><Markdown text={text.data} /></div>
    </section>
  );
  const json = path.endsWith(".json");
  const ext = path.split(".").pop()!.toUpperCase();
  return <CodeBlock title={name} text={json ? prettyJson(text.data) : text.data} foot={`${ext} · ${t("code.readOnly")}`} />;
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
    <ul className="space-y-0.5 [&_ul]:pl-4">
      {Object.entries(tree).map(([name, sub]) => {
        const path = prefix + name;
        return sub ? (
          <li key={name}>
            <details open={!!current?.startsWith(`${path}/`) || prefix === ""}>
              <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-[6px] px-2.5 font-mono text-xs text-fg hover:bg-surface-hover [&::-webkit-details-marker]:hidden">
                <ChevronDown className="size-3.5 shrink-0 text-fg-muted" aria-hidden /><Folder className="size-4 shrink-0 text-fg-muted" aria-hidden />{name}
              </summary>
              <TreeNode tree={sub} prefix={`${path}/`} current={current} />
            </details>
          </li>
        ) : (
          <li key={name}>
            <button type="button" onClick={() => setQuery({ soubor: path })} title={path} aria-current={current === path ? "true" : undefined}
              className={`flex min-h-11 w-full items-center gap-2 rounded-[6px] px-2.5 text-left font-mono text-xs ${current === path ? "bg-surface-active text-fg" : "text-fg hover:bg-surface-hover"}`}>
              <File className="size-4 shrink-0 text-fg-muted" aria-hidden /><span className="truncate">{name}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Záložka Soubory (návrh 13, změřeno z .pen): strom 300 px (`surface` r10 p12, položky mono 12), prohlížeč `surface` r12 p24:
 *  cesta + u Markdownu Náhled | Kód, nápověda mono 11, pod tím blok. */
export function FilesTab({ project, runId, files, current }: { project: string; runId: string; files: string[]; current?: string }) {
  const [mode, setMode] = useState<"preview" | "code">("preview");
  const shown = current && files.includes(current) ? current : undefined;
  return (
    <div className="grid grid-cols-[300px_1fr] items-start gap-6 max-lg:grid-cols-1">
      <nav aria-label={t("run.tab.soubory")} className="max-h-[75vh] overflow-auto rounded-[10px] bg-surface p-3">
        <TreeNode tree={buildTree(files)} prefix="" current={current} />
      </nav>
      <div className="min-w-0 space-y-6 rounded-card bg-surface p-6">
        {shown ? <>
          <div className="flex flex-wrap items-center gap-3">
            <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-fg-secondary" title={shown}>{shown}</span>
            {isMarkdown(shown) && <Toggle label={t("code.mode")} value={mode} onChange={setMode}
              options={[{ key: "preview", label: t("files.preview") }, { key: "code", label: t("files.code") }]} />}
          </div>
          <FileViewer project={project} runId={runId} path={shown} preview={mode === "preview"} />
        </> : <p className="text-sm text-fg-muted">{current ? t("run.noFile") : t("run.pickFile")}</p>}
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
