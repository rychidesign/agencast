import { ArrowLeft, Check, CircleAlert, Eye, EyeOff, Layers2, LockKeyhole, MapPinX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { API_BASE, saveToken, useConnection } from "./api";
import { Shell } from "./components/Shell";
import { btn } from "./components/ui";
import { t } from "./i18n";
import { useLocation } from "./router";
import { ProjectsPage } from "./pages/Projects";
import { ProjectPage } from "./pages/Project";
import { ScenarioPage } from "./pages/Scenario";
import { RunPage } from "./pages/Run";

export function App() {
  const conn = useConnection();
  const { route } = useLocation();
  if (conn.auth !== "ok") return <TokenScreen bad={conn.auth === "bad"} />;
  const project = "project" in route ? route.project : undefined;
  const tab = route.page === "project" ? route.tab : route.page === "scenario" ? "scenare" : route.page === "run" ? "behy" : undefined;
  return (
    <Shell project={project} tab={tab} back={route.page === "notFound"} offline={conn.offline}>
      {route.page === "projects" && <ProjectsPage />}
      {route.page === "project" && <ProjectPage key={route.project} {...route} />}
      {route.page === "scenario" && <ScenarioPage key={`${route.project}/${route.scenario}`} {...route} />}
      {route.page === "run" && <RunPage key={`${route.project}/${route.runId}`} {...route} />}
      {route.page === "notFound" && <NotFound />}
    </Shell>
  );
}

/** 404 adresy (návrh V3 / 14): na střed, ikona, velké „404“ mono, titul a cesta zpět. */
function NotFound() {
  return (
    <div className="flex min-h-[calc(100vh-6rem)] flex-col items-center justify-center gap-6 text-center">
      <MapPinX className="size-4 text-type" aria-hidden />
      <p className="font-mono text-[72px] leading-none text-fg-muted" aria-hidden>404</p>
      <h1 className="text-h1">{t("app.notFound")}</h1>
      <p className="text-sm text-fg-secondary">{t("app.notFoundHelp")}</p>
      <a className={btn.primary} href="#/"><ArrowLeft className="size-4" aria-hidden />{t("projects.title")}</a>
    </div>
  );
}

/** Obrazovka „Token serveru“: bez tokenu nebo po 401. Token jde jen do localStorage a hlavičky.
 *  Návrh V3 / 01 (změřeno z .pen): karta 480 px, radius 16, padding 32, mezery 22, značka nahoře, adresa serveru dole. */
export function TokenScreen({ bad }: { bad: boolean }) {
  const [value, setValue] = useState("");
  const [shown, setShown] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) saveToken(value.trim());
  };
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <form onSubmit={submit} className="flex w-full max-w-[480px] flex-col items-start gap-[22px] rounded-panel bg-surface p-8" aria-labelledby="token-title">
        <p className="flex items-center gap-2.5 text-[22px] font-semibold tracking-[-0.7px]">
          <Layers2 className="size-[25px] text-type" aria-hidden />agencast
        </p>
        <h1 id="token-title" className="text-h1">{t("token.title")}</h1>
        <p id="token-help" className="text-sm leading-[22px] text-fg-secondary">{t("token.help")}</p>
        <div className="w-full space-y-2">
          <label htmlFor="token" className="block text-[13px] font-medium text-fg-secondary">{t("token.label")}</label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-fg-muted" aria-hidden />
            <input
              id="token" type={shown ? "text" : "password"} autoComplete="off" autoFocus value={value} onChange={(e) => setValue(e.target.value)}
              aria-describedby="token-help"
              className="h-11 w-full rounded-[6px] bg-nested pr-11 pl-10 font-mono text-sm focus:ring-2 focus:ring-accent focus:ring-offset-0 focus:outline-none pointer-coarse:text-base"
            />
            <button type="button" onClick={() => setShown(!shown)} aria-label={t(shown ? "token.hide" : "token.show")} aria-pressed={shown}
              className="absolute top-1/2 right-1.5 grid size-8 -translate-y-1/2 place-items-center rounded-control text-fg-muted hover:text-fg">
              {shown ? <EyeOff className="size-[18px]" aria-hidden /> : <Eye className="size-[18px]" aria-hidden />}
            </button>
          </div>
        </div>
        {bad && (
          <p role="alert" className="inline-flex items-center gap-2 rounded-full bg-nested px-2.5 py-[7px] text-xs font-medium text-error">
            <CircleAlert className="size-3.5 shrink-0" aria-hidden />{t("token.bad")}
          </p>
        )}
        <button type="submit" className={btn.primary} disabled={!value.trim()}><Check className="size-4" aria-hidden />{t("common.save")}</button>
        <p className="font-mono text-xs text-fg-muted">{API_BASE || location.origin}</p>
      </form>
    </main>
  );
}
