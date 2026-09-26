// §2.3–2.4 Editor scénáře v čtecí verzi: sloupec karet + panel, nebo YAML režim přes celou šířku.
import { ArrowLeft, CodeXml } from "lucide-react";
import { useEffect, useMemo, type KeyboardEvent, type ReactNode } from "react";
import { enc, useApi } from "../api";
import { CodeView, stepLines } from "../components/CodeView";
import { HeaderCard, onColumnKey, StepList, Arrow, type ListCtx } from "../components/StepCards";
import { HeaderPanel, StepPanel } from "../components/StepPanel";
import { ErrorText, Loading, StatusChip, Toggle } from "../components/ui";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import { flatten } from "../steps";
import type { ErrorItem, FileDoc, Scenario } from "../types";

/** Výběr hlavičkové karty v `?krok=` (id kroku nesmí začínat `_`, nekoliduje). */
export const HEADER_KEY = "_hlavicka";

export function errorsByStep(errors: ErrorItem[]): Map<string, ErrorItem[]> {
  const m = new Map<string, ErrorItem[]>();
  for (const e of errors) if (e.step) m.set(e.step, [...(m.get(e.step) ?? []), e]);
  return m;
}

/** Posune vybranou kartu do pohledu (klik na čip „čte z“ skočí na kartu). */
export function useScrollToCard(key: string | undefined) {
  useEffect(() => {
    if (key) document.querySelector(`[data-step-card="${CSS.escape(key)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [key]);
}

/** Esc zavře panel a vrátí fokus na kartu (§6). */
export function closeOnEsc(selected: string | undefined) {
  return (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !selected) return;
    setQuery({ krok: undefined });
    document.querySelector<HTMLElement>(`[data-step-card="${CSS.escape(selected === HEADER_KEY ? "" : selected)}"]`)?.focus();
  };
}

export function PanelSlot({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-4 bottom-4 z-20 max-h-[70vh] overflow-auto rounded-2xl shadow-2xl min-[1100px]:sticky min-[1100px]:top-4 min-[1100px]:max-h-[calc(100vh-2rem)] min-[1100px]:w-[400px] min-[1100px]:shrink-0 min-[1100px]:self-start min-[1100px]:shadow-none">
      {children}
    </div>
  );
}

export function ScenarioPage({ project, scenario }: { project: string; scenario: string }) {
  const { query } = useLocation();
  const selected = query.get("krok") ?? undefined;
  const yaml = query.get("rezim") === "yaml";
  const base = `/projects/${enc(project)}`;
  const sc = useApi<Scenario>(`${base}/scenarios/${enc(scenario)}`);
  const file = `scenarios/${scenario}.yaml`;
  const doc = useApi<FileDoc>(yaml ? `${base}/files/${file}` : null);
  const s = sc.data;
  const all = useMemo(() => (s ? flatten(s.steps) : []), [s]);
  const errors = useMemo(() => errorsByStep(s?.errors ?? []), [s]);
  useScrollToCard(yaml ? undefined : selected);

  const select = (key: string) => setQuery({ krok: key === selected ? undefined : key });
  const ctx: ListCtx = { project, selected, onSelect: select, errors };
  const step = all.find((x) => x.id === selected);

  return (
    <main className="min-h-screen" onKeyDown={closeOnEsc(selected)}>
      <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-5 gap-y-2 bg-zinc-900/95 px-8 py-4">
        <a href={href(project, "scenare")} className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100">
          <ArrowLeft className="size-4" aria-hidden /> {t("editor.back", { project })}
        </a>
        <h1 className="font-mono text-lg font-semibold">{scenario}</h1>
        {s && <span className="min-w-0 truncate text-sm text-zinc-300">{s.description}</span>}
        <div className="ml-auto flex items-center gap-4">
          {s && s.errors.length > 0 && <StatusChip status="failed">{t("validation.count", { n: s.errors.length })}</StatusChip>}
          <span className="text-xs text-zinc-500">{t("editor.readonly")}</span>
          <Toggle label={t("code.mode")} value={yaml ? "yaml" : "form"}
            onChange={(m) => setQuery({ rezim: m === "yaml" ? "yaml" : undefined })}
            options={[{ key: "form", label: t("code.form") }, { key: "yaml", label: <><CodeXml className="size-3.5" aria-hidden />YAML</> }]} />
        </div>
      </header>
      <div className="px-8 pb-16">
        {sc.error && sc.error.status !== 0 && <ErrorText error={sc.error} />}
        {!s && !sc.error && <div className="mx-auto max-w-[640px] pt-6"><Loading rows={4} pill /></div>}
        {s && yaml && (
          doc.data ? (
            <div className="pt-4">
              <CodeView text={doc.data.text} file={file} errors={doc.data.errors}
                focus={selected && selected !== HEADER_KEY ? stepLines(doc.data.text, selected) : undefined} />
            </div>
          ) : doc.error ? <ErrorText error={doc.error} /> : <Loading rows={8} />
        )}
        {s && !yaml && (
          <div className="flex justify-center gap-6 pt-6">
            <section className="w-full max-w-[640px]" aria-label={t("step.list")} onKeyDown={onColumnKey}>
              <HeaderCard inputs={s.inputs} outputs={s.outputs} selected={selected === HEADER_KEY} onSelect={() => select(HEADER_KEY)} />
              <Arrow />
              <StepList steps={s.steps} ctx={ctx} />
            </section>
            {selected === HEADER_KEY && (
              <PanelSlot><HeaderPanel scenario={s} errors={s.errors.filter((e) => !e.step)} onClose={() => setQuery({ krok: undefined })} /></PanelSlot>
            )}
            {step && (
              <PanelSlot>
                <StepPanel step={step} scenario={s} all={all} project={project} errors={errors.get(step.id) ?? []}
                  onClose={() => setQuery({ krok: undefined })} onSelect={(id) => setQuery({ krok: id })} />
              </PanelSlot>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
