// Hlavička stránky (redesign G1, G3, G4; fidelity §1): H1 32 px + popis 14 + meta řádek mono 13, akce vpravo,
// zbytek akcí v menu ⋯, druhý řádek pro přepínač režimu, stav uložení nebo záložky.
import { ArrowLeft } from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { t } from "../i18n";
import { Menu, type MenuItem } from "./ui";

/** Ikonové tlačítko v hlavičce stránky (fidelity §2, §4): 48 × 48, `bg-control`, ikona 20 px. */
export const headerIconBtn =
  "grid size-12 shrink-0 place-items-center rounded-[10px] bg-control text-fg hover:bg-control-hover disabled:opacity-50 [&>svg]:size-5";

/** Odkaz zpět nad titulem („← Scénáře“). */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="inline-flex items-center gap-1.5 text-sm text-fg-secondary hover:text-fg pointer-coarse:min-h-11">
      <ArrowLeft className="size-4" aria-hidden /> {children}
    </a>
  );
}

export function PageHeader({ title, description, detail, meta, actions, menu, menuLabel, back, sticky, children }: {
  title: ReactNode;
  description?: ReactNode;
  /** Řádek pod popisem, mono 13 `fg-muted`: cesta registru, run_id. */
  detail?: ReactNode;
  /** Vedle titulu: čip chyb, stav běhu. */
  meta?: ReactNode;
  /** Nejvýš primární + jedno sekundární tlačítko. */
  actions?: ReactNode;
  /** Sekundární akce (G4); nebezpečné `danger` a poslední. */
  menu?: MenuItem[];
  /** Přístupné jméno ⋯, výchozí „Další akce“. */
  menuLabel?: string;
  /** Řádek nad titulem: odkaz zpět, drobečky. */
  back?: ReactNode;
  /** Přilepená hlavička (editor, běh); výšku hlásí v `--page-header-h` pro přilepený panel. */
  sticky?: boolean;
  /** Druhý řádek: přepínač režimu, SaveNote, záložky. */
  children?: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
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
    // z-30: menu ⋯ z hlavičky musí ležet nad přilepeným panelem (z-20)
    <header ref={ref}
      className={`space-y-5 pb-6 ${sticky ? "sticky top-0 z-30 -mx-4 bg-canvas px-4 pt-4 sm:-mx-8 sm:px-8" : ""}`}>
      {back && <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{back}</div>}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="min-w-0 text-[32px] leading-10 font-semibold tracking-[-0.5px] break-words">{title}</h1>
            {meta}
          </div>
          {description && <div className="mt-3 truncate text-sm text-fg-secondary" title={typeof description === "string" ? description : undefined}>{description}</div>}
          {detail && <div className="mt-3 truncate font-mono text-[13px] text-fg-muted">{detail}</div>}
        </div>
        {(actions || menu?.length) && (
          // ⋯ v hlavičce jako ikonové tlačítko `bg-control` (fidelity §2): 48 × 48, v editoru 40 × 40 (§6)
          <div className={`flex flex-wrap items-center gap-3 [&_[aria-haspopup=menu]]:rounded-[10px] [&_[aria-haspopup=menu]]:bg-control [&_[aria-haspopup=menu]]:text-fg [&_[aria-haspopup=menu]:hover]:bg-control-hover ${sticky ? "[&_[aria-haspopup=menu]]:size-10" : "[&_[aria-haspopup=menu]]:size-12"}`}>
            {actions}
            {!!menu?.length && <Menu items={menu} label={menuLabel ?? t("common.moreActions")} />}
          </div>
        )}
      </div>
      {children && <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{children}</div>}
    </header>
  );
}
