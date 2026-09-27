import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { saveToken, useConnection } from "./api";
import { PageHeader } from "./components/PageHeader";
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
    <Shell project={project} tab={tab} offline={conn.offline}>
      {route.page === "projects" && <ProjectsPage />}
      {route.page === "project" && <ProjectPage key={route.project} {...route} />}
      {route.page === "scenario" && <ScenarioPage key={`${route.project}/${route.scenario}`} {...route} />}
      {route.page === "run" && <RunPage key={`${route.project}/${route.runId}`} {...route} />}
      {route.page === "notFound" && (
        <PageHeader title={t("app.notFound")} actions={<a className={btn.secondary} href="#/">{t("projects.title")}</a>} />
      )}
    </Shell>
  );
}

/** Obrazovka „Token serveru“: bez tokenu nebo po 401. Token jde jen do localStorage a hlavičky. */
export function TokenScreen({ bad }: { bad: boolean }) {
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) saveToken(value.trim());
  };
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-md space-y-4 rounded-panel bg-surface p-6 ring-1 ring-line" aria-labelledby="token-title">
        <h1 id="token-title" className="flex items-center gap-2 text-lg font-semibold">
          <KeyRound className="size-5 text-fg-secondary" aria-hidden /> {t("token.title")}
        </h1>
        {bad && <p role="alert" className="text-sm text-error">{t("token.bad")}</p>}
        <div className="space-y-1.5">
          <label htmlFor="token" className="text-[13px] font-medium text-fg-secondary">{t("token.label")}</label>
          <input
            id="token" type="password" autoComplete="off" autoFocus value={value} onChange={(e) => setValue(e.target.value)}
            aria-describedby="token-help"
            className="h-9 w-full rounded-control bg-nested px-3 font-mono text-[13px] ring-1 ring-line focus:ring-accent focus:outline-none pointer-coarse:h-11"
          />
          <p id="token-help" className="text-xs text-fg-muted">{t("token.help")}</p>
        </div>
        <button type="submit" className={btn.primary} disabled={!value.trim()}>{t("common.save")}</button>
      </form>
    </main>
  );
}
