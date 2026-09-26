import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { API_BASE, saveToken, useConnection } from "./api";
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
  return (
    <>
      {conn.offline && <ServerBar />}
      {route.page === "projects" && <ProjectsPage />}
      {route.page === "project" && <ProjectPage key={route.project} {...route} />}
      {route.page === "scenario" && <ScenarioPage key={`${route.project}/${route.scenario}`} {...route} />}
      {route.page === "run" && <RunPage key={`${route.project}/${route.runId}`} {...route} />}
      {route.page === "notFound" && (
        <main className="p-8">
          <p>{t("app.notFound")}</p>
          <a className="underline" href="#/">{t("projects.title")}</a>
        </main>
      )}
    </>
  );
}

/** ServerBar: server neodpovídá — `useApi` zkouší znovu po 5 s. */
function ServerBar() {
  return (
    <div role="alert" data-testid="server-bar" className="sticky top-0 z-30 bg-zinc-800 px-6 py-2 text-sm text-amber-400">
      {t("server.offline", { host: API_BASE || location.host })}
    </div>
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
      <form onSubmit={submit} className="w-full max-w-md space-y-4 rounded-2xl bg-zinc-800 p-6" aria-labelledby="token-title">
        <h1 id="token-title" className="flex items-center gap-2 text-lg font-semibold">
          <KeyRound className="size-5" aria-hidden /> {t("token.title")}
        </h1>
        {bad && <p role="alert" className="text-sm text-rose-400">{t("token.bad")}</p>}
        <div className="space-y-1">
          <label htmlFor="token" className="text-[13px] font-semibold text-zinc-300">{t("token.label")}</label>
          <input
            id="token" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)}
            aria-describedby="token-help"
            className="h-10 w-full rounded-lg bg-zinc-900 px-3 font-mono text-sm ring-1 ring-zinc-700 focus:ring-zinc-300 focus:outline-none"
          />
          <p id="token-help" className="text-xs text-zinc-400">{t("token.help")}</p>
        </div>
        <button type="submit" className={btn.primary} disabled={!value.trim()}>{t("common.save")}</button>
      </form>
    </main>
  );
}
