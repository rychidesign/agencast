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

/** Řetězec ikon typů na kartě scénáře: nejvýš 5, pak čip „+N“ (§2.2). */
export function IconChain({ types, max = 5 }: { types: (StepType | null)[]; max?: number }) {
  const shown = types.slice(0, max);
  const rest = types.length - shown.length;
  return (
    <ol className="flex items-center gap-1.5" aria-label={t("scenario.chain", { types: types.join(", ") })}>
      {shown.map((type, i) => (
        <li key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-fg-muted" aria-hidden>→</span>}
          <span className="grid size-7 place-items-center rounded-full bg-nested text-type" title={type ?? "?"}>
            <TypeIcon type={type} />
          </span>
        </li>
      ))}
      {rest > 0 && (
        <li className="rounded-full bg-nested px-2 py-1 text-xs text-fg-secondary">+{rest}</li>
      )}
    </ol>
  );
}
