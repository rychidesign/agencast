// Tenký fetch nad HTTP API `agencast serve`: token, stav spojení, chyby jako typy.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { t } from "./i18n";
import type { ErrorItem } from "./types";

const TOKEN_KEY = "agencast.token";

/** Při `npm run dev` běží GUI na jiném originu než `serve` (proto `serve --cors`). */
export const API_BASE: string = import.meta.env.DEV
  ? (import.meta.env.VITE_AGENCAST_URL as string | undefined) ?? "http://127.0.0.1:8787"
  : "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly errors: ErrorItem[] = [],
    readonly details: string[] = [],
    /** Celé tělo chyby (409 nese aktuální `etag`). */
    readonly body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

// --- stav spojení (ServerBar, obrazovka tokenu) -------------------------------------------

export interface Connection {
  /** `missing` = token není uložený, `bad` = server vrátil 401. */
  auth: "ok" | "missing" | "bad";
  offline: boolean;
}

let conn: Connection = { auth: localStorage.getItem(TOKEN_KEY) ? "ok" : "missing", offline: false };
const listeners = new Set<() => void>();

function setConn(patch: Partial<Connection>) {
  const next = { ...conn, ...patch };
  if (next.auth === conn.auth && next.offline === conn.offline) return;
  conn = next;
  listeners.forEach((l) => l());
}

export function useConnection(): Connection {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => conn,
  );
}

export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  setConn({ auth: "ok" });
}

// --- požadavky ---------------------------------------------------------------------------

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    setConn({ auth: "missing" });
    throw new ApiError(401, "chybí token");
  }
  let res: Response;
  try {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (init.body) headers["Content-Type"] = "application/json";
    res = await fetch(API_BASE + path, { ...init, headers });
  } catch {
    setConn({ offline: true });
    // hláška prohlížeče („Failed to fetch“) je anglicky a nic neříká; ukazuje ji SaveNote
    throw new ApiError(0, t("server.unreachable"));
  }
  setConn({ offline: false });
  if (res.status === 401) setConn({ auth: "bad" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      typeof body.error === "string" ? body.error : `HTTP ${res.status}`,
      Array.isArray(body.errors) ? body.errors : [],
      Array.isArray(body.details) ? body.details : [],
      body,
    );
  }
  return res;
}

export const getJson = async <T>(path: string): Promise<T> => (await request(path)).json();
export const getText = async (path: string): Promise<string> => (await request(path)).text();
export const getBlob = async (path: string): Promise<Blob> => (await request(path)).blob();

/** Otisk souboru bez stahování (`HEAD …/files/<cesta>`, hlavička `ETag` v uvozovkách). */
export const headEtag = async (path: string): Promise<string | null> =>
  (await request(path, { method: "HEAD" })).headers.get("ETag")?.replace(/^(W\/)?"|"$/g, "") ?? null;

/** Zápis (editační operace, spuštění běhu): JSON tělo, odpověď JSON; chyba → ApiError. */
export const send = async <T>(method: string, path: string, body?: unknown): Promise<T> =>
  (await request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })).json();

/** Odpověď editační operace (api.md „Editace“). */
export interface Saved {
  etag: string | null;
  errors: ErrorItem[];
}

export const enc = encodeURIComponent;

// --- hook pro čtení ----------------------------------------------------------------------

export interface Loaded<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/** Načte `path` (null = nic); `poll(data)` vrací za kolik ms načíst znovu (null = nečekat).
 *  Nedostupný server se zkouší znovu po 5 s (ServerBar „zkouším znovu…“). */
export function useApi<T>(
  path: string | null,
  poll?: (data: T) => number | null,
  load: (path: string) => Promise<T> = getJson,
): Loaded<T> {
  const [state, setState] = useState<{ data?: T; error?: ApiError; path?: string | null }>({});
  const [tick, setTick] = useState(0);
  const pollRef = useRef(poll);
  pollRef.current = poll;
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (!path) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = () => {
      loadRef.current(path).then(
        (data) => {
          if (!alive) return;
          setState({ data, path });
          const next = pollRef.current?.(data);
          if (next != null) timer = setTimeout(run, next);
        },
        (error: ApiError) => {
          if (!alive) return;
          setState((s) => ({ data: s.path === path ? s.data : undefined, error, path }));
          if (error.status === 0) timer = setTimeout(run, 5000);
        },
      );
    };
    run();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = state.path === path;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !!path && (!current || (state.data === undefined && state.error === undefined)),
    reload,
  };
}
