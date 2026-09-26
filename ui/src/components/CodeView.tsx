// `YamlEditor` ke čtení (§3, §4.5): čísla řádků, chybné řádky s rose značkou, dva odstíny.
import { useEffect, useRef } from "react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { ErrorList } from "./ui";

/** Klíč světle, komentář ztlumeně — nic víc (§4.5: žádné barvy). */
export function Line({ text }: { text: string }) {
  if (/^\s*#/.test(text)) return <span className="text-zinc-500">{text}</span>;
  const m = /^(\s*(?:-\s+)?)([\w.-]+:)(.*)$/.exec(text);
  if (!m) return <span className="text-zinc-300">{text}</span>;
  return (
    <>
      <span className="text-zinc-300">{m[1]}</span>
      <span className="text-zinc-100">{m[2]}</span>
      <span className="text-zinc-300">{m[3]}</span>
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
  useEffect(() => {
    if (focus) ref.current?.querySelector(`[data-line="${focus[0]}"]`)?.scrollIntoView({ block: "center" });
  }, [focus]);
  return (
    <div>
      <div ref={ref} className="overflow-auto rounded-xl bg-zinc-800/60 p-4 font-mono text-sm leading-6 ring-1 ring-zinc-700" tabIndex={0}
        role="region" aria-label={file}>
        <table className="border-collapse">
          <tbody>
            {lines.map((l, i) => {
              const n = i + 1;
              const hi = focus && n >= focus[0] && n <= focus[1];
              return (
                <tr key={i} data-line={n} className={bad.has(n) ? "border-l-2 border-rose-400 bg-rose-500/5" : hi ? "bg-zinc-700/50" : ""}>
                  <td className="pr-4 text-right align-top text-zinc-500 select-none">{n}</td>
                  <td className="whitespace-pre"><Line text={l} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-zinc-400">{t("code.hint", { file: `workflows/${file}` })}</p>
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
