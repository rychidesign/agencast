import {
  Bot, Columns2, CornerDownRight, Equal, Image, MessageSquare, OctagonX, PackageCheck, Scale, Split,
  type LucideIcon, CircleHelp,
} from "lucide-react";
import { t } from "../i18n";
import type { StepType } from "../types";

// Ikony typů podle §5 návrhu (lucide, 16 px, tah 1,5).
const ICONS: Record<StepType, LucideIcon> = {
  ask: MessageSquare, task: Bot, jev: Scale, image: Image, parallel: Columns2,
  switch: Split, call: CornerDownRight, set: Equal, fail: OctagonX, output: PackageCheck,
};

export function TypeIcon({ type, className = "size-4" }: { type: StepType | null; className?: string }) {
  const Icon = (type && ICONS[type]) || CircleHelp;
  return <Icon className={className} strokeWidth={1.5} aria-hidden />;
}

/** Řetězec ikon typů na kartě scénáře: prosté ikony 16 px bez koleček a šipek, nejvýš 5, pak „+N“ (fidelity §5). */
export function IconChain({ types, max = 5 }: { types: (StepType | null)[]; max?: number }) {
  const shown = types.slice(0, max);
  const rest = types.length - shown.length;
  return (
    <ol className="flex h-8 items-center gap-3 text-type" aria-label={t("scenario.chain", { types: types.join(", ") })}>
      {shown.map((type, i) => (
        <li key={i} title={type ?? "?"}><TypeIcon type={type} /></li>
      ))}
      {rest > 0 && <li className="font-mono text-xs text-fg-muted">+{rest}</li>}
    </ol>
  );
}
