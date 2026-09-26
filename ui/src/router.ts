// Hash routing (§1 návrhu): GUI běží i v iframe Skynet Soul, proto `#/…`.
import { useSyncExternalStore } from "react";

export type Tab = "scenare" | "agenti" | "config" | "skilly" | "behy";
export const TABS: Tab[] = ["scenare", "agenti", "config", "skilly", "behy"];

export type Route =
  | { page: "projects" }
  | { page: "project"; project: string; tab: Tab; item?: string }
  | { page: "scenario"; project: string; scenario: string }
  | { page: "run"; project: string; runId: string }
  | { page: "notFound" };

export interface Location {
  route: Route;
  query: URLSearchParams;
}

export function parseHash(hash: string): Location {
  const raw = hash.replace(/^#/, "");
  const [path, qs = ""] = raw.split("?", 2);
  const seg = path.split("/").filter(Boolean).map(decodeURIComponent);
  const query = new URLSearchParams(qs);
  const at = (route: Route) => ({ route, query });
  if (seg.length === 0) return at({ page: "projects" });
  if (seg[0] !== "p" || !seg[1]) return at({ page: "notFound" });
  const project = seg[1];
  const tab = (seg[2] ?? "scenare") as Tab;
  if (!TABS.includes(tab) || seg.length > 4) return at({ page: "notFound" });
  if (tab === "scenare" && seg[3]) return at({ page: "scenario", project, scenario: seg[3] });
  if (tab === "behy" && seg[3]) return at({ page: "run", project, runId: seg[3] });
  return at({ page: "project", project, tab, item: seg[3] });
}

/** `href("repo", "scenare", "ig-post", {krok: "copy"})` → `#/p/repo/scenare/ig-post?krok=copy`. */
export function href(project?: string, tab?: Tab, item?: string, query?: Record<string, string | undefined>): string {
  const parts = project ? ["p", project, tab, item].filter(Boolean) as string[] : [];
  const qs = new URLSearchParams(Object.entries(query ?? {}).filter((e): e is [string, string] => !!e[1]));
  const q = qs.toString();
  return `#/${parts.map(encodeURIComponent).join("/")}${q ? `?${q}` : ""}`;
}

// Deep link z dashboardu: iframe hlásí rodiči aktuální cestu (§1).
window.addEventListener("hashchange", () => {
  if (window.parent !== window) window.parent.postMessage({ type: "agencast:route", hash: location.hash }, "*");
});

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (opts.replace) {
    history.replaceState(null, "", to);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    location.hash = to;
  }
}

/** Změní jen query aktuální cesty (bez nového záznamu historie). */
export function setQuery(patch: Record<string, string | undefined>) {
  const { query } = parseHash(location.hash);
  for (const [k, v] of Object.entries(patch)) v ? query.set(k, v) : query.delete(k);
  const path = location.hash.split("?")[0] || "#/";
  const q = query.toString();
  navigate(`${path}${q ? `?${q}` : ""}`, { replace: true });
}

let cached = { hash: "\0", loc: parseHash("") };
function snapshot(): Location {
  if (cached.hash !== location.hash) cached = { hash: location.hash, loc: parseHash(location.hash) };
  return cached.loc;
}

export function useLocation(): Location {
  return useSyncExternalStore((cb) => {
    window.addEventListener("hashchange", cb);
    return () => window.removeEventListener("hashchange", cb);
  }, snapshot);
}
