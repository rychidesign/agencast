// Sloupec karet kroků (§2.3, §2.4) — stejný pro editor a prohlížeč běhu (§2.5).
// Editor přidává `ctx.edit`: konektory s +, koš a ⋯ vně pilulky, klávesy (§4.1–4.3, §6).
import { AlignJustify, ArrowDown, ChevronDown, ChevronRight, CircleX, Trash2, TriangleAlert } from "lucide-react";
import { useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import type { Anchor, ListRef } from "../edit";
import { formatCost, formatDuration } from "../format";
import { t } from "../i18n";
import { href } from "../router";
import { callChildren, runValue, type RunCtx } from "../run";
import { flatten, stepValue } from "../steps";
import type { ErrorItem, IoSpec, RunStep, Step } from "../types";
import { AddButton, TypePicker, type Pick } from "./TypePicker";
import { TypeIcon } from "./TypeIcon";
import { Menu, StatusIcon, type Status } from "./ui";

/** Editační akce sloupce; kroky nesou `uid` (edit.ts `WStep`). */
export interface EditCtx {
  add: (at: Anchor, pick: Pick) => void;
  remove: (step: Step) => void;
  shift: (step: Step, delta: -1 | 1) => void;
  cut: (step: Step) => void;
  /** Vyjmutý krok čeká na „Vložit sem“. */
  cut_?: Step;
  addBranch: (step: Step) => void;
  /** Hlavička má výstupy a krok `output` chybí → nabídka na konci hlavního seznamu. */
  addOutput?: () => void;
}

export interface ListCtx {
  project: string;
  selected?: string;
  onSelect: (key: string) => void;
  errors: Map<string, ErrorItem[]>;
  run?: RunCtx;
  edit?: EditCtx;
  /** Editor: jméno scénáře a cesta přes call (`?z=`), ze kterých „otevřít“ u `call` skládá drobečky. */
  scenario?: string;
  trail?: string;
}

export const uidOf = (s: Step) => (s as { uid?: string }).uid ?? s.id;

const RUN_ICON: Record<RunStep["status"], Status> = {
  running: "running", succeeded: "succeeded", failed: "failed", cancelled: "cancelled", skipped: "skipped", interrupted: "interrupted",
};

/** Klíč karty: id v editoru, cesta v běhu (`navrh/copy`). */
const keyOf = (step: Step, ctx: ListCtx) => (ctx.run ? ctx.run.prefix + step.id : step.id);

/** Výběr karty z klávesnice (Enter/mezerník, `detail` 0) pošle fokus do otevřeného panelu (§6); Esc ho vrátí. */
const focusPanel = (e: MouseEvent) =>
  e.detail === 0 && requestAnimationFrame(() => document.querySelector<HTMLElement>("aside :is(select, input, textarea, [role=tab])")?.focus());

/** ↑/↓ mezi kartami sloupce (§6); karty jsou tlačítka v pořadí dokumentu. */
export function onColumnKey(e: KeyboardEvent<HTMLElement>) {
  if ((e.key !== "ArrowDown" && e.key !== "ArrowUp") || e.altKey) return;
  if (!(e.target as HTMLElement).matches("[data-step-card]")) return;
  const cards = [...e.currentTarget.querySelectorAll<HTMLElement>("[data-step-card]")];
  const i = cards.indexOf(document.activeElement as HTMLElement);
  if (i < 0) return;
  e.preventDefault();
  cards[Math.max(0, Math.min(cards.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
}

interface CardProps {
  step: Step;
  ctx: ListCtx;
  /** Kontejner (`parallel`, `switch`) má jiný tvar — zaoblený obdélník. */
  shape?: "pill" | "head";
  meta?: string;
  /** Kam vložit krok „nad“ (editor). */
  above?: Anchor;
}

export function StepCard({ step, ctx, shape = "pill", meta, above }: CardProps) {
  const key = keyOf(step, ctx);
  const rs = ctx.run?.steps.get(key);
  const selected = ctx.selected === key;
  const errors = ctx.errors.get(step.id) ?? [];
  const value = (ctx.run && runValue(step.type, rs)) || meta || stepValue(step)
    || (ctx.run ? (rs ? t(`rstatus.${rs.status}`) : t("run.notReached")) : "");
  const warn = !!rs?.continued;
  const status: Status | undefined = ctx.run ? (warn ? "warning" : rs ? RUN_ICON[rs.status] : "none") : undefined;
  // nedošlo i přeskočeno (nevybraný případ, `when`) je ztlumené (§3 CaseSection); důvod nese hodnota karty
  const dim = ctx.run && (!rs || rs.status === "skipped");
  let right: ReactNode = step.when ? <span className="font-mono">{t("step.when", { expr: step.when })}</span> : null;
  if (ctx.run) {
    const secs = rs?.status === "running" && rs.started_at ? (ctx.run.now - Date.parse(rs.started_at)) / 1000 : rs?.duration_s;
    right = rs && rs.status !== "skipped" ? (
      <span className="inline-flex gap-2 font-mono tabular-nums">
        <span data-testid={`step-duration-${key}`}>{formatDuration(secs)}</span>
        {rs.cost_usd != null && <>· <span data-testid={`step-cost-${key}`}>{formatCost(rs.cost_usd)}</span></>}
      </span>
    ) : null;
  }
  const edit = ctx.edit;
  const isCut = !!edit?.cut_ && uidOf(edit.cut_) === uidOf(step);
  const label = `${t("step.number", { n: step.nn })}: ${step.type ?? "?"} ${step.id}${status ? ` — ${rs ? t(`rstatus.${rs.status}`) : t("run.notReached")}` : ""}${isCut ? ` — ${t("edit.cutMark")}` : ""}`;
  const onKey = (e: KeyboardEvent) => {
    if (!edit) return;
    if (e.key === "Delete") edit.remove(step);
    else if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) edit.shift(step, e.key === "ArrowUp" ? -1 : 1);
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "x") edit.cut(step);
    else return;
    e.preventDefault();
    e.stopPropagation();
  };
  return (
    <div className={`${dim ? "opacity-40" : ""} ${edit ? "group relative" : ""}`}>
      <button
        type="button" data-step-card={key} aria-pressed={selected} aria-label={label}
        onClick={(e) => (ctx.onSelect(key), !selected && focusPanel(e))} onKeyDown={onKey}
        className={`flex w-full items-center gap-3 bg-surface px-5 py-3 text-left transition-colors hover:bg-surface-hover ${shape === "pill" ? "rounded-full" : "rounded-card"} ${
          selected ? "ring-2 ring-accent" : ""
        } ${isCut ? "opacity-50" : ""}`}
      >
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-nested font-mono text-sm text-fg-secondary">
          {status ? <StatusIcon status={status} label="" className="size-4" /> : step.nn}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-[11px] tracking-wider text-fg-secondary uppercase">
            <TypeIcon type={step.type} className="size-4 text-type" />
            {step.type ?? "?"} · <span className="font-mono normal-case tracking-normal text-fg-secondary">{step.id}</span>
            {errors.length > 0 && <span className="size-1.5 rounded-full bg-error" aria-hidden />}
          </span>
          <span className={`block truncate text-sm ${value ? "font-semibold text-fg" : "font-normal text-fg-muted"}`}>
            {value || t("step.value.empty")}
          </span>
        </span>
        {right && <span className="max-w-[40%] shrink-0 truncate text-[13px] text-fg-muted">{right}</span>}
      </button>
      {edit && <CardControls step={step} edit={edit} above={above} />}
      {warn && (
        <p className="mt-1 ml-14 flex items-center gap-1.5 text-[13px] text-warning">
          <TriangleAlert className="size-4" aria-hidden />{t("run.warning")}
        </p>
      )}
      {errors.map((e, i) => (
        <p key={i} className="mt-1 ml-14 flex items-start gap-1.5 text-[13px] text-error">
          <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden /><span className="line-clamp-2">{e.message.split("\n")[0]}</span>
        </p>
      ))}
    </div>
  );
}

/** ⋯ a koš vně pilulky (§2.3): při hoveru a `focus-within`, na dotyku trvale ztlumeně. */
function CardControls({ step, edit, above }: { step: Step; edit: EditCtx; above?: Anchor }) {
  const [picker, setPicker] = useState<Anchor | null>(null);
  const uid = uidOf(step);
  const out = step.type === "output";
  const items = [
    ...(out ? [] : [
      { label: t("edit.moveUp"), onSelect: () => edit.shift(step, -1) },
      { label: t("edit.moveDown"), onSelect: () => edit.shift(step, 1) },
      { label: t("edit.cut"), onSelect: () => edit.cut(step) },
    ]),
    ...(above ? [{ label: t("edit.insertAbove"), onSelect: () => setPicker(above) }] : []),
    ...(out ? [] : [{ label: t("edit.insertBelow"), onSelect: () => setPicker({ after: uid }) }]),
    { label: t("edit.delete"), onSelect: () => edit.remove(step) },
  ];
  return (
    <div className="absolute top-1/2 left-full ml-2 flex -translate-y-1/2 items-center gap-1 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 pointer-coarse:opacity-60 pointer-coarse:group-focus-within:opacity-100">
      <Menu items={items} label={t("common.menuFor", { name: step.id })} />
      <button type="button" onClick={() => edit.remove(step)} aria-label={t("edit.deleteStep", { id: step.id })} title={t("edit.delete")}
        className="grid size-7 place-items-center rounded-full bg-error/15 text-error hover:bg-error/25 pointer-coarse:size-11">
        <Trash2 className="size-3.5" aria-hidden />
      </button>
      {picker && (
        <div className="relative">
          <TypePicker paste={edit.cut_?.id} onClose={() => setPicker(null)} onPick={(p) => (setPicker(null), edit.add(picker, p))} />
        </div>
      )}
    </div>
  );
}

/** Šipka mezi kartami; v editoru se při hoveru/fokusu promění v (+) (§2.3 Konektor). `afterId` = krok nad (+). */
export function Connector({ ctx, at, afterId }: { ctx: ListCtx; at: Anchor; afterId?: string }) {
  const edit = ctx.edit;
  if (!edit) return <Arrow />;
  return (
    <div className="group/conn relative flex h-10 items-center justify-center pointer-coarse:h-12">
      <ArrowDown className={`absolute size-4 text-fg-muted group-focus-within/conn:opacity-0 group-hover/conn:opacity-0 pointer-coarse:opacity-0 ${edit.cut_ ? "opacity-0" : ""}`} aria-hidden />
      <AddButton label={afterId ? t("edit.addAfter", { id: afterId }) : t("edit.addStart")} testid={afterId && `add-after-${afterId}`}
        paste={edit.cut_?.id} always={!!edit.cut_} onPick={(p) => edit.add(at, p)} />
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex h-10 items-center justify-center text-fg-muted" aria-hidden>
      <ArrowDown className="size-4" />
    </div>
  );
}

/** Pseudo-krok pro kroky volaného scénáře, které známe jen ze záznamu běhu. */
const fromRun = (rs: RunStep, i: number): Step => ({
  nn: i + 1, address: [], id: rs.step.split("/").pop()!, type: rs.kind, when: null, fields: {}, refs: [],
});

/** Kontejner se dá sbalit šipkou u čísla (§2.4): vnitřek zmizí, zůstane počet kroků. */
function Container({ step, ctx, meta, above, inner, children }: {
  step: Step; ctx: ListCtx; meta: string; above?: Anchor; inner: Step[]; children: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <div className="relative rounded-card bg-surface p-2">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        aria-label={t(open ? "step.collapse" : "step.expand", { id: step.id })}
        className="absolute top-6 left-2 z-10 grid size-6 place-items-center rounded-full text-fg-muted hover:bg-surface-hover hover:text-fg pointer-coarse:size-11">
        <Icon className="size-4" aria-hidden />
      </button>
      <div className="pl-8"><StepCard step={step} ctx={ctx} shape="head" meta={meta} above={above} /></div>
      {open ? <div className="p-2">{children}</div>
        : <p className="px-5 pb-2 text-[13px] text-fg-muted">{t("count.steps", { n: flatten(inner).length })}</p>}
    </div>
  );
}

function Branch({ label, testid, children }: { label: string; testid?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-card bg-nested p-3" aria-label={label} data-testid={testid}>
      <h4 className="mb-2 font-mono text-[13px] text-fg-muted">{label}</h4>
      {children}
    </section>
  );
}

function StepItem({ step, ctx, above }: { step: Step; ctx: ListCtx; above?: Anchor }) {
  const uid = uidOf(step);
  const sub = (key: string[]): ListRef => ({ parent: uid, key });
  const addBranch = ctx.edit && (
    <button type="button" onClick={() => ctx.edit!.addBranch(step)} className="rounded-full bg-nested px-3 py-1.5 text-[13px] text-fg-secondary hover:bg-surface-hover pointer-coarse:min-h-11">
      + {t(step.type === "parallel" ? "edit.addBranch" : "edit.addCase")}
    </button>
  );
  if (step.type === "parallel" && step.branches) {
    const names = Object.keys(step.branches);
    return (
      <Container step={step} ctx={ctx} above={above} inner={Object.values(step.branches).flat()}
        meta={`${names.join(" ∥ ")} · ${t("step.parallel.meta", { n: names.length })}`}>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-3">
          {names.map((b) => <Branch key={b} label={b} testid={`branch-${b}`}><StepList steps={step.branches![b]} ctx={ctx} list={sub(["parallel", b])} /></Branch>)}
        </div>
        {addBranch && <div className="mt-2 text-right">{addBranch}</div>}
      </Container>
    );
  }
  if (step.type === "switch" && step.cases) {
    return (
      <Container step={step} ctx={ctx} above={above} meta={stepValue(step)}
        inner={[...Object.values(step.cases).flat(), ...(step.default ?? [])]}>
        <div className="space-y-3">
          {Object.entries(step.cases).map(([c, steps]) => (
            <Branch key={c} label={`= ${c}`} testid={`case-${c}`}><StepList steps={steps} ctx={ctx} list={sub(["switch", "cases", c])} /></Branch>
          ))}
          {step.default?.length || ctx.edit ? (
            <Branch label={t("step.switch.default")} testid="case-default">
              {!step.default?.length && <p className="font-mono text-[13px] text-fg-muted">{t("step.switch.elseNothing")}</p>}
              <StepList steps={step.default ?? []} ctx={ctx} list={sub(["switch", "default"])} />
            </Branch>
          ) : (
            <p className="px-3 font-mono text-[13px] text-fg-muted">{t("step.switch.elseNothing")}</p>
          )}
          {addBranch && <div className="text-right">{addBranch}</div>}
        </div>
      </Container>
    );
  }
  if (step.type === "call") {
    const target = step.call ?? String((step.fields.call as { scenario?: string } | undefined)?.scenario ?? "");
    const path = ctx.run ? ctx.run.prefix + step.id : "";
    // V běhu: kroky volaného scénáře ze snímku (`callees`), bez něj jen ty ze záznamu.
    const children = !ctx.run?.steps.has(path) ? []
      : ctx.run.callees[target] ?? callChildren(ctx.run, path).map(fromRun);
    // V editoru „otevřít“ nese cestu přes call (`?z=ig-post:navrh`) pro drobečky a návrat na kartu (§4.7).
    const from = ctx.trail !== undefined ? [ctx.trail, `${ctx.scenario}:${step.id}`].filter(Boolean).join(",") : undefined;
    const open = target && (
      <a href={href(ctx.project, "scenare", target, { z: from })} className="text-[13px] text-fg-secondary underline hover:text-fg">
        {target} {t("step.call.open")}
      </a>
    );
    if (children.length && ctx.run) {
      const inner = { ...ctx, run: { ...ctx.run, prefix: `${path}/` } };
      return (
        <Container step={step} ctx={ctx} meta={stepValue(step)} inner={children}>
          <div className="mb-2 px-3">{open}</div>
          <Branch label={target}><StepList steps={children} ctx={inner} /></Branch>
        </Container>
      );
    }
    return (
      <div>
        <div className="rounded-card bg-surface p-2"><StepCard step={step} ctx={ctx} shape="head" above={above} /></div>
        {open && <div className="mt-1 ml-16">{open}</div>}
      </div>
    );
  }
  return <StepCard step={step} ctx={ctx} above={above} />;
}

const MAIN: ListRef = { parent: null, key: [] };

export function StepList({ steps, ctx, list = MAIN }: { steps: Step[]; ctx: ListCtx; list?: ListRef }) {
  const edit = ctx.edit;
  const last = steps[steps.length - 1];
  const end: Anchor = last ? { after: uidOf(last) } : { list };
  const main = list.parent === null;
  return (
    <ol>
      {steps.map((s, i) => {
        const above: Anchor = i ? { after: uidOf(steps[i - 1]) } : { list };
        return (
          <li key={uidOf(s)}>
            {i > 0 && <Connector ctx={ctx} at={above} afterId={steps[i - 1].id} />}
            <StepItem step={s} ctx={ctx} above={edit ? above : undefined} />
          </li>
        );
      })}
      {edit && last?.type !== "output" && (
        <li className="flex h-14 items-center justify-center gap-3">
          <AddButton always label={t("edit.addEnd")} paste={edit.cut_?.id} onPick={(p) => edit.add(end, p)} />
          {main && edit.addOutput && (
            <button type="button" onClick={edit.addOutput} className="rounded-full bg-nested px-2.5 py-1 font-mono text-[13px] text-fg-secondary ring-1 ring-line hover:bg-surface-hover pointer-coarse:min-h-11">
              + output
            </button>
          )}
        </li>
      )}
    </ol>
  );
}

/** Hlavičková karta: vstupy a výstupy scénáře, vždy první, ikona místo čísla. */
export function HeaderCard({ inputs, outputs, selected, onSelect }: {
  inputs: Record<string, IoSpec> | null; outputs: Record<string, IoSpec> | null; selected: boolean; onSelect: () => void;
}) {
  const i = Object.keys(inputs ?? {});
  const o = Object.keys(outputs ?? {});
  const value = t("step.header.value", {
    inputs: i.length ? `${t("count.inputs", { n: i.length })}: ${i.join(", ")}` : t("step.header.noInputs"),
    outputs: o.length ? `${t("count.outputs", { n: o.length })}: ${o.join(", ")}` : t("step.header.noOutputs"),
  });
  return (
    <button type="button" data-step-card="" aria-pressed={selected} onClick={(e) => (onSelect(), !selected && focusPanel(e))}
      className={`flex w-full items-center gap-3 rounded-full bg-surface px-5 py-3 text-left hover:bg-surface-hover ${selected ? "ring-2 ring-accent" : ""}`}>
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-nested text-fg-secondary">
        <AlignJustify className="size-4" strokeWidth={1.5} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] tracking-wider text-fg-secondary uppercase">{t("step.header")}</span>
        <span className="block truncate text-sm font-semibold text-fg">{value}</span>
      </span>
    </button>
  );
}
