// `YamlEditor` ke čtení (§3, §4.5): čísla řádků, chybné řádky, dva odstíny.
import { useEffect, useRef, useState } from "react";
import { Check, Copy, FileCode2 } from "lucide-react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { CodeHead, copyBtn, ErrorList } from "./ui";

/** Klíč světle, komentář ztlumeně — nic víc (§4.5: žádné barvy). */
export function Line({ text }: { text: string }) {
  if (/^\s*#/.test(text)) return <span className="text-fg-muted">{text}</span>;
  const m = /^(\s*(?:-\s+)?)([\w.-]+:)(.*)$/.exec(text);
  if (!m) return <span className="text-fg-secondary">{text}</span>;
  return (
    <>
      <span className="text-fg-secondary">{m[1]}</span>
      <span className="text-fg">{m[2]}</span>
      <span className="text-fg-secondary">{m[3]}</span>
    </>
  );
}

export function CodeView({ text, file, errors = [], focus }: {
  text: string;
  /** Soubor ve `workflows/` (nápověda pod blokem). */
  file: string;
  errors?: ErrorItem[];
  /** Řádky (od 1) k podbarvení a posunutí do pohledu. */
  focus?: [number, number];
}) {
  const lines = text.replace(/\n$/, "").split("\n");
  const bad = new Set(errors.map((e) => e.line).filter(Boolean));
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (focus) ref.current?.querySelector(`[data-line="${focus[0]}"]`)?.scrollIntoView({ block: "center" });
  }, [focus]);
  return (
    <div>
      <div className="overflow-hidden rounded-[var(--radius-panel)] bg-surface">
        <CodeHead icon={FileCode2} name={file} chip={t("code.readOnly")} />
        <div ref={ref} className="overflow-auto bg-nested py-4 font-mono text-[13px] leading-[27px] focus-visible:ring-2 focus-visible:ring-accent" tabIndex={0} role="region" aria-label={file}>
          <table className="border-collapse">
            <tbody>
              {lines.map((l, i) => {
                const n = i + 1;
                const hi = focus && n >= focus[0] && n <= focus[1];
                return (
                  <tr key={i} data-line={n} className={bad.has(n) ? "border-l-2 border-error bg-error/10" : hi ? "border-l-2 border-accent bg-surface-active" : ""}>
                    <td className={`w-[58px] pr-3.5 pl-4 text-right align-top font-mono text-xs select-none ${hi ? "text-fg-secondary" : "text-fg-muted"}`}>{n}</td>
                    <td className="pr-4 whitespace-pre"><Line text={l} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 p-3.5">
          <p className="font-mono text-[11px] text-fg-muted">{t("code.hint", { file: `workflows/${file}` })}</p>
          <button type="button" className={copyBtn} onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}>{copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copied ? t("common.copied") : t("common.copy")}</button>
        </div>
      </div>
      {errors.length > 0 && <div className="mt-3"><ErrorList errors={errors} /></div>}
    </div>
  );
}

/** Řádky kroku `id` v textu scénáře: od `- id: <id>` po další položku se stejným nebo menším odsazením. */
export function stepLines(text: string, id: string): [number, number] | undefined {
  const lines = text.split("\n");
  const start = lines.findIndex((l) => new RegExp(`^\\s*-\\s+id:\\s*["']?${id}["']?\\s*(#.*)?$`).test(l));
  if (start < 0) return undefined;
  const indent = lines[start].search(/-/);
  let end = start + 1;
  while (end < lines.length && (lines[end].trim() === "" || lines[end].search(/\S/) > indent)) end++;
  return [start + 1, end];
}
