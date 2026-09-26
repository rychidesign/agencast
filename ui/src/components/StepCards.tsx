// Sloupec karet kroků (§2.3, §2.4) — stejný pro editor (jen ke čtení) a prohlížeč běhu (§2.5).
import { AlignJustify, ArrowDown, CircleX, TriangleAlert } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { formatCost, formatDuration } from "../format";
import { t } from "../i18n";
import { href } from "../router";
import { callChildren, continued, runValue, type RunCtx } from "../run";
import { stepValue } from "../steps";
import type { ErrorItem, IoSpec, RunStep, Step } from "../types";
import { TypeIcon } from "./TypeIcon";
import { StatusIcon, type Status } from "./ui";

export interface ListCtx {
  project: string;
  selected?: string;
  onSelect: (key: string) => void;
  errors: Map<string, ErrorItem[]>;
  run?: RunCtx;
}

const RUN_ICON: Record<RunStep["status"], Status> = {
  running: "running", succeeded: "succeeded", failed: "failed", cancelled: "cancelled", skipped: "skipped",
};

/** Klíč karty: id v editoru, cesta v běhu (`navrh/copy`). */
const keyOf = (step: Step, ctx: ListCtx) => (ctx.run ? ctx.run.prefix + step.id : step.id);

/** ↑/↓ mezi kartami sloupce (§6); karty jsou tlačítka v pořadí dokumentu. */
export function onColumnKey(e: KeyboardEvent<HTMLElement>) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
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
}

export function StepCard({ step, ctx, shape = "pill", meta }: CardProps) {
  const key = keyOf(step, ctx);
  const rs = ctx.run?.steps.get(key);
  const selected = ctx.selected === key;
  const errors = ctx.errors.get(step.id) ?? [];
  const value = (ctx.run && runValue(step.type, key, ctx.run)) || meta || stepValue(step)
    || (ctx.run ? (rs ? t(`rstatus.${rs.status}`) : t("run.notReached")) : "");
  const warn = ctx.run && continued(ctx.run.events, key);
  const status: Status | undefined = ctx.run ? (warn ? "warning" : rs ? RUN_ICON[rs.status] : "none") : undefined;
  const notReached = ctx.run && !rs;
  let right: ReactNode = step.when ? <span className="font-mono">{t("step.when", { expr: step.when })}</span> : null;
  if (ctx.run) {
    const secs = rs?.status === "running" && rs.started_at ? (ctx.run.now - Date.parse(rs.started_at)) / 1000 : rs?.duration_s;
    right = rs && rs.status !== "skipped" ? (
      <span className="inline-flex gap-4 font-mono tabular-nums">
        <span>{formatDuration(secs)}</span>
        {rs.cost_usd != null && <span>{formatCost(rs.cost_usd)}</span>}
      </span>
    ) : null;
  }
  const label = `${t("step.number", { n: step.nn })}: ${step.type ?? "?"} ${step.id}${status ? ` — ${rs ? t(`rstatus.${rs.status}`) : t("run.notReached")}` : ""}`;
  return (
    <div className={notReached ? "opacity-40" : ""}>
      <button
        type="button" data-step-card={key} aria-pressed={selected} aria-label={label}
        onClick={() => ctx.onSelect(key)}
        className={`flex w-full items-center gap-3 px-5 py-3 text-left transition-colors ${shape === "pill" ? "rounded-full" : "rounded-xl"} ${
          selected ? "bg-zinc-800 ring-1 ring-zinc-400/60 ring-offset-2 ring-offset-zinc-900" : shape === "pill" ? "bg-zinc-800/60 hover:bg-zinc-800" : "hover:bg-zinc-800"
        } ${rs?.status === "running" ? "motion-safe:animate-pulse" : ""}`}
      >
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-zinc-900 text-sm font-semibold text-zinc-200">
          {status ? <StatusIcon status={status} label="" className="size-5" /> : step.nn}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-[11px] tracking-wider text-zinc-400 uppercase">
            <TypeIcon type={step.type} className="size-3.5" />
            {step.type ?? "?"} · <span className="font-mono normal-case tracking-normal text-zinc-300">{step.id}</span>
            {errors.length > 0 && <span className="size-1.5 rounded-full bg-rose-400" aria-hidden />}
          </span>
          <span className={`block truncate text-sm font-semibold ${value ? "text-zinc-100" : "font-normal text-zinc-500"}`}>
            {value || t("step.value.empty")}
          </span>
        </span>
        {right && <span className="max-w-[40%] shrink-0 truncate text-[13px] text-zinc-400">{right}</span>}
      </button>
      {warn && (
        <p className="mt-1 ml-14 flex items-center gap-1.5 text-[13px] text-amber-400">
          <TriangleAlert className="size-4" aria-hidden />{t("run.warning")}
        </p>
      )}
      {errors.map((e, i) => (
        <p key={i} className="mt-1 ml-14 flex items-start gap-1.5 text-[13px] text-rose-400">
          <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden /><span className="line-clamp-2">{e.message.split("\n")[0]}</span>
        </p>
      ))}
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex h-10 items-center justify-center text-zinc-400" aria-hidden>
      <ArrowDown className="size-4" />
    </div>
  );
}

/** Pseudo-krok pro kroky volaného scénáře, které známe jen ze záznamu běhu. */
const fromRun = (rs: RunStep, i: number): Step => ({
  nn: i + 1, address: [], id: rs.step.split("/").pop()!, type: rs.kind, when: null, fields: {}, refs: [],
});

function Container({ step, ctx, meta, children }: { step: Step; ctx: ListCtx; meta: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl bg-zinc-800/60 p-2">
      <StepCard step={step} ctx={ctx} shape="head" meta={meta} />
      <div className="p-2">{children}</div>
    </div>
  );
}

function Branch({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-xl bg-zinc-900/60 p-3" aria-label={label}>
      <h4 className="mb-2 font-mono text-[13px] text-zinc-400">{label}</h4>
      {children}
    </section>
  );
}

function StepItem({ step, ctx }: { step: Step; ctx: ListCtx }) {
  if (step.type === "parallel" && step.branches) {
    const names = Object.keys(step.branches);
    return (
      <Container step={step} ctx={ctx} meta={`${names.join(" ∥ ")} · ${t("step.parallel.meta", { n: names.length })}`}>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          {names.map((b) => <Branch key={b} label={b}><StepList steps={step.branches![b]} ctx={ctx} /></Branch>)}
        </div>
      </Container>
    );
  }
  if (step.type === "switch" && step.cases) {
    return (
      <Container step={step} ctx={ctx} meta={stepValue(step)}>
        <div className="space-y-3">
          {Object.entries(step.cases).map(([c, steps]) => (
            <Branch key={c} label={`= ${c}`}><StepList steps={steps} ctx={ctx} /></Branch>
          ))}
          {step.default?.length ? (
            <Branch label={t("step.switch.default")}><StepList steps={step.default} ctx={ctx} /></Branch>
          ) : (
            <p className="px-3 font-mono text-[13px] text-zinc-500">{t("step.switch.elseNothing")}</p>
          )}
        </div>
      </Container>
    );
  }
  if (step.type === "call") {
    const target = step.call ?? String((step.fields.call as { scenario?: string } | undefined)?.scenario ?? "");
    const path = ctx.run ? ctx.run.prefix + step.id : "";
    const children = ctx.run ? callChildren(ctx.run, path) : [];
    const open = target && (
      <a href={href(ctx.project, "scenare", target)} className="text-[13px] text-zinc-400 underline hover:text-zinc-100">
        {target} {t("step.call.open")}
      </a>
    );
    if (children.length && ctx.run) {
      const inner = { ...ctx, run: { ...ctx.run, prefix: `${path}/` } };
      return (
        <Container step={step} ctx={ctx} meta={stepValue(step)}>
          <div className="mb-2 px-3">{open}</div>
          <Branch label={target}><StepList steps={children.map(fromRun)} ctx={inner} /></Branch>
        </Container>
      );
    }
    return (
      <div>
        <StepCard step={step} ctx={ctx} />
        {open && <div className="mt-1 ml-16">{open}</div>}
      </div>
    );
  }
  return <StepCard step={step} ctx={ctx} />;
}

export function StepList({ steps, ctx }: { steps: Step[]; ctx: ListCtx }) {
  return (
    <ol>
      {steps.map((s, i) => (
        <li key={s.id}>
          {i > 0 && <Arrow />}
          <StepItem step={s} ctx={ctx} />
        </li>
      ))}
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
    <button type="button" data-step-card="" aria-pressed={selected} onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-full px-5 py-3 text-left ${selected ? "bg-zinc-800 ring-1 ring-zinc-400/60 ring-offset-2 ring-offset-zinc-900" : "bg-zinc-800/60 hover:bg-zinc-800"}`}>
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-zinc-900 text-zinc-300">
        <AlignJustify className="size-4" strokeWidth={1.5} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] tracking-wider text-zinc-400 uppercase">{t("step.header")}</span>
        <span className="block truncate text-sm font-semibold">{value}</span>
      </span>
    </button>
  );
}

export { Arrow };
