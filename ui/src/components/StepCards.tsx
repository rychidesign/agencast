// Column of step cards (§2.3, §2.4) — the same for the editor and the run viewer (§2.5).
// The editor adds `ctx.edit`: connectors with +, the ⋯ menu and keys (§4.1–4.3, §6).
import { AlignJustify, ArrowDown, ChevronDown, ChevronRight, CircleX, Plus, TriangleAlert, Variable } from "lucide-react";
import { useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import type { Anchor, ListRef } from "../edit";
import { formatCost, formatDuration } from "../format";
import { t } from "../i18n";
import { href } from "../router";
import { callChildren, runValue, type RunCtx } from "../run";
import { flatten, stepLines } from "../steps";
import type { ErrorItem, IoSpec, RunStep, Step } from "../types";
import { AddButton, TypePicker, type Pick } from "./TypePicker";
import { TypeIcon } from "./TypeIcon";
import { btn, Menu, StatusIcon, type Status } from "./ui";

/** Editing actions of the column; steps carry a `uid` (edit.ts `WStep`). */
export interface EditCtx {
  add: (at: Anchor, pick: Pick) => void;
  remove: (step: Step) => void;
  shift: (step: Step, delta: -1 | 1) => void;
  cut: (step: Step) => void;
  /** A cut step waits for "Paste here". */
  cut_?: Step;
  addBranch: (step: Step) => void;
  /** The header has outputs and the `output` step is missing → menu at the end of the main list. */
  addOutput?: () => void;
}

export interface ListCtx {
  project: string;
  selected?: string;
  onSelect: (key: string) => void;
  errors: Map<string, ErrorItem[]>;
  run?: RunCtx;
  edit?: EditCtx;
  /** Editor: scenario name and path through call (`?from=`), from which "open" on `call` builds breadcrumbs. */
  scenario?: string;
  trail?: string;
}

export const uidOf = (s: Step) => (s as { uid?: string }).uid ?? s.id;

const RUN_ICON: Record<RunStep["status"], Status> = {
  running: "running", succeeded: "succeeded", failed: "failed", cancelled: "cancelled", skipped: "skipped", interrupted: "interrupted",
};

/** Card key: id in the editor, path in a run (`draft/copy`). */
const keyOf = (step: Step, ctx: ListCtx) => (ctx.run ? ctx.run.prefix + step.id : step.id);

/** Selecting a card from the keyboard (Enter/space, `detail` 0) sends focus to the open panel (§6); Esc returns it. */
const focusPanel = (e: MouseEvent) =>
  e.detail === 0 && requestAnimationFrame(() => document.querySelector<HTMLElement>("aside :is(select, input, textarea, [role=tab])")?.focus());

/** ↑/↓ between cards of the column (§6); cards are buttons in document order. */
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
  /** Main card of a container (`parallel`, `switch`, `call` with expansion) — no surface of its own, the wrapper carries the container. */
  shape?: "pill" | "head";
  /** Where to insert a step "above" (editor). */
  above?: Anchor;
}

export function StepCard({ step, ctx, shape = "pill", above }: CardProps) {
  const key = keyOf(step, ctx);
  const rs = ctx.run?.steps.get(key);
  const selected = ctx.selected === key;
  const errors = ctx.errors.get(step.id) ?? [];
  const lines = stepLines(step);
  const title = (ctx.run && runValue(step.type, rs)) || lines.title
    || (ctx.run ? (rs ? t(`rstatus.${rs.status}`) : t("run.notReached")) : "");
  const detail = [lines.detail, step.when ? t("step.when", { expr: step.when }) : ""].filter(Boolean).join(" · ");
  const warn = !!rs?.continued;
  const status: Status | undefined = ctx.run ? (warn ? "warning" : rs ? RUN_ICON[rs.status] : "none") : undefined;
  // not reached and skipped (unselected case, `when`) is dimmed (§3 CaseSection); the reason is carried by the card value.
  // Dimming = dashed outline without a surface and muted text, not transparency (which would drop contrast below 4.5:1).
  const dim = ctx.run && (!rs || rs.status === "skipped");
  // run (design 12, measured from .pen): third row = duration · cost (for containers and call after the description), state 11 px on the right
  let right: ReactNode = null;
  let runDetail: ReactNode = null;
  if (ctx.run) {
    const secs = rs?.status === "running" && rs.started_at ? (ctx.run.now - Date.parse(rs.started_at)) / 1000 : rs?.duration_s;
    const keep = step.type === "parallel" || step.type === "switch" || step.type === "call" ? lines.detail : "";
    runDetail = rs && rs.status !== "skipped" ? (
      <span className="tabular-nums">
        {keep && `${keep} · `}
        <span data-testid={`step-duration-${key}`}>{formatDuration(secs)}</span>
        {rs.cost_usd != null && <> · <span data-testid={`step-cost-${key}`}>{formatCost(rs.cost_usd)} USD</span></>}
      </span>
    ) : keep || null;
    right = <span className={`shrink-0 text-[11px] ${selected ? "text-fg-secondary" : "text-fg-muted"}`}>{rs ? t(`rstatus.${rs.status}`) : t("run.notReached")}</span>;
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
  const head = shape === "head";
  const pr = head || edit ? "pr-14" : ""; // room for ⋯ inside the card
  // design 05 (measured from .pen): pill p 16, gap 14, height 96; selected = `surface-active` surface without a border
  const plane = head ? "rounded-card" : `rounded-full ${dim ? "border border-dashed border-line" : selected ? "bg-surface-active" : "bg-surface"}`;
  return (
    // The card has its own stacking context; popovers are therefore portaled to body.
    <div className={edit ? "group relative focus-within:z-10" : ""}>
      <button
        type="button" data-step-card={key} aria-pressed={selected} aria-label={label}
        onClick={(e) => (ctx.onSelect(key), !selected && focusPanel(e))} onKeyDown={onKey}
        className={`lg:scroll-mt-[calc(var(--page-header-h,5rem)+0.25rem)] flex w-full items-center text-left transition-colors hover:bg-surface-hover ${head ? "gap-2.5 px-4 py-2" : "min-h-24 gap-3.5 p-4 max-md:min-h-20 max-md:py-2.5 in-data-branch:min-h-0 in-data-branch:p-2.5"} ${plane} ${pr} ${isCut ? "opacity-50" : ""}`}
      >
        {/* order only in the editor; a card in a run does not have it (design 12) */}
        {!head && !ctx.run && <span className={`w-4 shrink-0 text-center font-mono text-[11px] in-data-branch:hidden max-md:hidden ${selected ? "text-fg-secondary" : "text-fg-muted"}`}>{step.nn}</span>}
        {/* container: plain 20 px icon; card: 40 px circle (30 in a branch) with a type-color surface */}
        <span className={`grid shrink-0 place-items-center rounded-full ${head ? "" : "size-10 bg-type/7 max-md:size-9 in-data-branch:size-[30px]"}`}>
          {status ? <StatusIcon status={status} label="" className={head ? "size-5" : "size-4"} />
            : <TypeIcon type={step.type} className={`${head ? "size-5" : "size-4"} ${dim ? "text-fg-muted" : "text-type"}`} />}
        </span>
        <span className={`flex min-w-0 flex-1 flex-col gap-1 max-md:gap-0.5 ${head ? "flex-col-reverse" : ""}`}>
          <span className={`flex items-center gap-1.5 font-mono ${head ? "text-[10px] leading-[15px] text-fg-muted" : `text-[11px] leading-4 ${dim ? "text-fg-muted" : "text-type"}`}`}>
            <span className="truncate">{head && `${step.nn} · `}{step.type ?? "?"} · {step.id}{head && detail ? ` · ${detail}` : ""}</span>
            {errors.length > 0 && <span className="size-1.5 shrink-0 rounded-full bg-error" aria-hidden />}
          </span>
          <span className={`block truncate text-[15px] leading-[22px] in-data-branch:text-[13px] in-data-branch:leading-[19px] ${title && !dim ? "font-semibold text-fg" : "font-normal text-fg-muted"}`} title={title || undefined}>
            {title || t("step.value.empty")}
          </span>
          {ctx.run ? runDetail && !head && <span className="block truncate font-mono text-xs leading-[17px] text-fg-secondary">{runDetail}</span>
            : detail && !head && <span className="block truncate font-mono text-xs leading-[17px] text-fg-secondary" title={detail}>{detail}</span>}
        </span>
        {right}
      </button>
      {edit && <CardControls step={step} edit={edit} above={above} />}
      {warn && (
        <p className="mt-1 ml-20 flex items-center gap-1.5 text-[13px] text-warning">
          <TriangleAlert className="size-4" aria-hidden />{t("run.warning")}
        </p>
      )}
      {errors.map((e, i) => (
        <p key={i} className="mt-1 ml-20 flex items-start gap-1.5 text-[13px] text-error">
          <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden /><span className="line-clamp-2">{e.message.split("\n")[0]}</span>
        </p>
      ))}
    </div>
  );
}

/** ⋯ on the right of the pill (fidelity §6), vertically centered on the card (96 px, 50 px in a branch). */
function CardControls({ step, edit, above }: { step: Step; edit: EditCtx; above?: Anchor }) {
  const [picker, setPicker] = useState<Anchor | null>(null);
  const pickerAnchor = useRef<HTMLDivElement>(null);
  const uid = uidOf(step);
  const out = step.type === "output";
  const items = [
    ...(out ? [] : [
      { label: t("edit.moveUp"), shortcut: "Alt+↑", onSelect: () => edit.shift(step, -1) },
      { label: t("edit.moveDown"), shortcut: "Alt+↓", onSelect: () => edit.shift(step, 1) },
      { label: t("edit.cut"), shortcut: "Ctrl+X", onSelect: () => edit.cut(step) },
    ]),
    ...(above ? [{ label: t("edit.insertAbove"), onSelect: () => setPicker(above) }] : []),
    ...(out ? [] : [{ label: t("edit.insertBelow"), onSelect: () => setPicker({ after: uid }) }]),
    { label: t("edit.delete"), shortcut: "Del", onSelect: () => edit.remove(step), danger: true },
  ];
  return (
    <div ref={pickerAnchor} className="absolute top-12 right-3 -translate-y-1/2 max-md:top-10 in-data-branch:top-[25px] in-data-branch:right-1">
      <Menu ghost items={items} label={t("common.menuFor", { name: step.id })} />
      {picker && <TypePicker anchor={pickerAnchor} paste={edit.cut_?.id} onClose={() => setPicker(null)} onPick={(p) => (setPicker(null), edit.add(picker, p))} />}
    </div>
  );
}

/** Arrow between cards; in the editor it turns into (+) on hover/focus (§2.3 Connector). `afterId` = the step above (+). */
export function Connector({ ctx, at, afterId }: { ctx: ListCtx; at: Anchor; afterId?: string }) {
  const edit = ctx.edit;
  if (!edit) return <Arrow />;
  return (
    <div className="group/conn relative flex h-12 items-center justify-center">
      <ArrowDown className={`absolute size-4 text-fg-muted group-focus-within/conn:opacity-0 group-hover/conn:opacity-0 pointer-coarse:opacity-0 ${edit.cut_ ? "opacity-0" : ""}`} aria-hidden />
      <AddButton label={afterId ? t("edit.addAfter", { id: afterId }) : t("edit.addStart")} testid={afterId && `add-after-${afterId}`}
        paste={edit.cut_?.id} always={!!edit.cut_} onPick={(p) => edit.add(at, p)} />
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex h-12 items-center justify-center text-fg-muted" aria-hidden>
      <ArrowDown className="size-4" />
    </div>
  );
}

/** Pseudo-step for steps of the called scenario known only from the run record. */
const fromRun = (rs: RunStep, i: number): Step => ({
  nn: i + 1, address: [], id: rs.step.split("/").pop()!, type: rs.kind, when: null, fields: {}, refs: [],
});

/** Container (design 05, measured from .pen): `surface` r14 p16 gap 16 wrapper, header = icon 20 + title 15 + mono 10
 *  ("3 · parallel · variants"), collapsed with an arrow on the right (the inside disappears, the step count remains). */
function Container({ step, ctx, above, inner, children }: {
  step: Step; ctx: ListCtx; above?: Anchor; inner: Step[]; children: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <div className="relative space-y-4 rounded-tile bg-surface p-4">
      <StepCard step={step} ctx={ctx} shape="head" above={above} />
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        aria-label={t(open ? "step.collapse" : "step.expand", { id: step.id })}
        className={`absolute top-[43px] z-10 grid size-11 -translate-y-1/2 place-items-center rounded-full text-fg-muted hover:bg-surface-hover hover:text-fg ${ctx.edit ? "right-[64px]" : "right-5"}`}>
        <Icon className="size-4" aria-hidden />
      </button>
      {open ? <div>{children}</div>
        : <p className="px-4 font-mono text-xs text-fg-muted">{t("count.steps", { n: flatten(inner).length })}</p>}
    </div>
  );
}

function Branch({ label, testid, children }: { label: string; testid?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-control bg-nested p-3" aria-label={label} data-testid={testid} data-branch="">
      <h4 className="mb-3 font-mono text-[11px] leading-4 text-variable">{label}</h4>
      {children}
    </section>
  );
}

function StepItem({ step, ctx, above }: { step: Step; ctx: ListCtx; above?: Anchor }) {
  const uid = uidOf(step);
  const sub = (key: string[]): ListRef => ({ parent: uid, key });
  const addBranch = ctx.edit && (
    <button type="button" onClick={() => ctx.edit!.addBranch(step)} className={btn.secondary}>
      + {t(step.type === "parallel" ? "edit.addBranch" : "edit.addCase")}
    </button>
  );
  if (step.type === "parallel" && step.branches) {
    const names = Object.keys(step.branches);
    return (
      <Container step={step} ctx={ctx} above={above} inner={Object.values(step.branches).flat()}>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-3">
          {names.map((b) => <Branch key={b} label={b} testid={`branch-${b}`}><StepList steps={step.branches![b]} ctx={ctx} list={sub(["parallel", b])} /></Branch>)}
        </div>
        {addBranch && <div className="mt-3 text-right">{addBranch}</div>}
      </Container>
    );
  }
  if (step.type === "switch" && step.cases) {
    return (
      <Container step={step} ctx={ctx} above={above}
        inner={[...Object.values(step.cases).flat(), ...(step.default ?? [])]}>
        <div className="space-y-3">
          {Object.entries(step.cases).map(([c, steps]) => (
            <Branch key={c} label={`= ${c}`} testid={`case-${c}`}><StepList steps={steps} ctx={ctx} list={sub(["switch", "cases", c])} /></Branch>
          ))}
          {step.default?.length || ctx.edit ? (
            <Branch label={t("step.switch.default")} testid="case-default">
              {!step.default?.length && <p className="font-mono text-xs text-fg-muted">{t("step.switch.elseNothing")}</p>}
              <StepList steps={step.default ?? []} ctx={ctx} list={sub(["switch", "default"])} />
            </Branch>
          ) : (
            <p className="px-3 font-mono text-xs text-fg-muted">{t("step.switch.elseNothing")}</p>
          )}
          {addBranch && <div className="text-right">{addBranch}</div>}
        </div>
      </Container>
    );
  }
  if (step.type === "call") {
    const target = step.call ?? String((step.fields.call as { scenario?: string } | undefined)?.scenario ?? "");
    const path = ctx.run ? ctx.run.prefix + step.id : "";
    // In a run: steps of the called scenario from the snapshot (`callees`), without it only those from the record.
    const children = !ctx.run?.steps.has(path) ? []
      : ctx.run.callees[target] ?? callChildren(ctx.run, path).map(fromRun);
    // In the editor "open" carries the path through call (`?from=ig-post:draft`) for breadcrumbs and returning to the card (§4.7).
    const from = ctx.trail !== undefined ? [ctx.trail, `${ctx.scenario}:${step.id}`].filter(Boolean).join(",") : undefined;
    const open = target && (
      <a href={href(ctx.project, "scenarios", target, { from })} className="font-mono text-xs text-fg-secondary underline hover:text-fg">
        {target} {t("step.call.open")}
      </a>
    );
    if (children.length && ctx.run) {
      const inner = { ...ctx, run: { ...ctx.run, prefix: `${path}/` } };
      return (
        <Container step={step} ctx={ctx} inner={children}>
          <div className="px-4">{open}</div>
          <Branch label={target}><StepList steps={children} ctx={inner} /></Branch>
        </Container>
      );
    }
    return (
      <div>
        <StepCard step={step} ctx={ctx} above={above} />
        {open && <div className="mt-1 ml-[74px]">{open}</div>}
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
        // main list: "+ Add step" and "+ output" as secondary buttons (fidelity §6); branches have (+)
        <li className={`flex items-center justify-center gap-3 ${main ? "pt-6" : "h-14"}`}>
          <AddButton always text={main ? t("edit.addStep") : undefined} label={t("edit.addEnd")} paste={edit.cut_?.id} onPick={(p) => edit.add(end, p)} />
          {main && edit.addOutput && (
            <button type="button" onClick={edit.addOutput} className={btn.secondary}>
              <Plus className="size-4" aria-hidden />output
            </button>
          )}
        </li>
      )}
    </ol>
  );
}

/** Header card: scenario inputs row by row (name, required, type), outputs below them; always first, an icon instead of a number. */
export function HeaderCard({ inputs, outputs, selected, onSelect }: {
  inputs: Record<string, IoSpec> | null; outputs: Record<string, IoSpec> | null; selected: boolean; onSelect: () => void;
}) {
  const i = Object.entries(inputs ?? {});
  const o = Object.keys(outputs ?? {});
  const value = o.length ? `${t("count.outputs", { n: o.length })}: ${o.join(", ")}` : t("step.header.noOutputs");
  return (
    // design 05 (measured from .pen): rectangular card r14 p22 gap 16, icon 24, title 21 semibold, inputs/outputs below it in mono 13
    <button type="button" data-step-card="" aria-pressed={selected} onClick={(e) => (onSelect(), !selected && focusPanel(e))}
      className={`lg:scroll-mt-[calc(var(--page-header-h,5rem)+0.25rem)] flex w-full flex-col gap-4 rounded-tile p-[22px] text-left transition-colors hover:bg-surface-hover ${selected ? "bg-surface-active ring-inset ring-1 ring-accent/70" : "bg-surface"}`}>
      <span className="flex items-center gap-3">
        <AlignJustify className="size-6 shrink-0 text-type" strokeWidth={1.5} aria-hidden />
        <span className="text-[21px] leading-[30px] font-semibold text-fg uppercase">{t("step.header")}</span>
      </span>
      {i.length ? (
        <span className="flex flex-col gap-1.5">
          {i.map(([name, spec]) => (
            <span key={name} className="flex items-center gap-2 rounded-[8px] bg-nested px-3 py-2 font-mono text-[13px] leading-[19px]" title={spec.description}>
              <Variable className="size-4 shrink-0 text-variable" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-fg">{name}</span>
              {spec.required && <span className="text-[11px] text-fg-muted uppercase">{t("step.header.required")}</span>}
              {spec.type && <span className="text-[11px] text-type">{spec.type}</span>}
            </span>
          ))}
        </span>
      ) : <span className="font-mono text-[13px] leading-[19px] text-fg-secondary">{t("step.header.noInputs")}</span>}
      <span className="block truncate font-mono text-[13px] leading-[19px] text-fg-secondary" title={value}>{value}</span>
    </button>
  );
}
