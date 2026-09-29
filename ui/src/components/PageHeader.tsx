// Page header (redesign G1, G3, G4; fidelity §1; mobile: H1 24, primary action + ⋯): H1 28 px + description 14 + mono 13 meta row, actions on the right,
// remaining actions in the ⋯ menu, second row for the mode toggle, save state or tabs.
import { ArrowLeft } from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { t } from "../i18n";
import { btn, Menu, useMedia, type MenuItem } from "./ui";

/** Icon button in the page header: 44 × 44, `bg-control`, icon 20 px (measured from .pen). */
export const headerIconBtn = `${btn.icon} [&>svg]:size-5`;

/** Back link above the title ("← Scenarios"). */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="inline-flex items-center gap-3 text-xs text-fg-secondary hover:text-fg pointer-coarse:min-h-11">
      <ArrowLeft className="size-4" aria-hidden /> {children}
    </a>
  );
}

export function PageHeader({ title, description, detail, meta, actions, compact = [], menu, menuLabel, back, sticky, children }: {
  title: ReactNode;
  description?: ReactNode;
  /** Row right below the title, mono 13 `fg-muted`: run_id. */
  detail?: ReactNode;
  /** Next to the title: error chip, run state. */
  meta?: ReactNode;
  /** At most a primary + one secondary button. */
  actions?: ReactNode;
  /** Up to 767 px only the primary action + ⋯: the secondary button from `actions` has `max-md:hidden` and its counterpart goes here
   *  (at the start of ⋯). */
  compact?: MenuItem[];
  /** Secondary actions (G4); a dangerous `danger` one comes last. */
  menu?: MenuItem[];
  /** Accessible name of ⋯, default "More actions". */
  menuLabel?: string;
  /** Row above the title: back link, breadcrumbs. */
  back?: ReactNode;
  /** Sticky header (editor, run); reports its height in `--page-header-h` for card spacing when jumping. */
  sticky?: boolean;
  /** Second row: mode toggle, SaveNote, tabs. */
  children?: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const narrow = useMedia("(max-width: 767px)");
  const items = narrow ? [...compact, ...(menu ?? [])] : menu;
  useLayoutEffect(() => {
    const el = ref.current;
    if (!sticky || !el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--page-header-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.removeProperty("--page-header-h");
    };
  }, [sticky]);
  return (
    // z-30: the ⋯ menu from the header must sit above the sticky panel (z-20)
    <header ref={ref}
      className={`space-y-5 pb-6 max-md:space-y-4 ${sticky ? "z-30 bg-app lg:sticky lg:top-0 lg:-mx-8 lg:-mt-4 lg:px-8 lg:pt-4" : ""}`}>
      {back && <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{back}</div>}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className={`min-w-0 flex-1 ${description || detail ? "max-md:basis-full" : ""}`}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {/* the title is never clipped: long mono names (without spaces) wrap anywhere */}
            <h1 className="text-h1 min-w-0 [overflow-wrap:anywhere] max-md:text-2xl max-md:leading-8">{title}</h1>
            {meta}
          </div>
          {description && <div className="mt-3 truncate text-sm leading-[21px] text-fg-secondary max-md:mt-2 max-md:line-clamp-3 max-md:text-[13px] max-md:leading-5 max-md:whitespace-normal" title={typeof description === "string" ? description : undefined}>{description}</div>}
          {detail && <div className="mt-2 truncate font-mono text-[13px] leading-5 text-fg-muted max-md:text-xs">{detail}</div>}
        </div>
        {(actions || items?.length) && (
          // ⋯ in the header as a `bg-control` icon button, 44 × 44 (measured from .pen)
          <div className="flex flex-wrap items-center gap-3">
            {actions}
            {!!items?.length && <Menu items={items} label={menuLabel ?? t("common.moreActions")} />}
          </div>
        )}
      </div>
      {children && <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{children}</div>}
    </header>
  );
}
