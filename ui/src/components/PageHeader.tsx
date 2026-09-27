// Hlavička stránky (redesign G1, G3, G4): H1 + popis + akce vpravo, zbytek akcí v menu ⋯,
// druhý řádek pro přepínač režimu, stav uložení nebo záložky.
import { ArrowLeft } from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { t } from "../i18n";
import { Menu, type MenuItem } from "./ui";

/** Odkaz zpět nad titulem („← Scénáře“). */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="inline-flex items-center gap-1.5 text-sm text-fg-secondary hover:text-fg">
      <ArrowLeft className="size-4" aria-hidden /> {children}
    </a>
  );
}

export function PageHeader({ title, description, meta, actions, menu, menuLabel, back, sticky, children }: {
  title: ReactNode;
  description?: ReactNode;
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
    <header ref={ref}
      className={`space-y-3 pb-4 ${sticky ? "sticky top-0 z-20 -mx-4 bg-canvas px-4 pt-4 sm:-mx-8 sm:px-8" : ""}`}>
      {back && <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{back}</div>}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="min-w-0 text-xl font-semibold break-words">{title}</h1>
            {meta}
          </div>
          {description && <div className="mt-1 truncate text-sm text-fg-secondary">{description}</div>}
        </div>
        {(actions || menu?.length) && (
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            {!!menu?.length && <Menu items={menu} label={menuLabel ?? t("common.moreActions")} />}
          </div>
        )}
      </div>
      {children && <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{children}</div>}
    </header>
  );
}
