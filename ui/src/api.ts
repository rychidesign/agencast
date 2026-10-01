// Thin fetch over the `agencast serve` HTTP API: token, connection state, typed errors.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { t } from "./i18n";
import type { ErrorItem } from "./types";

const TOKEN_KEY = "agencast.token";

/** With `npm run dev` the GUI runs on a different origin than `serve` (hence `serve --cors`). */
export const API_BASE: string = import.meta.env.DEV
  ? (import.meta.env.VITE_AGENCAST_URL as string | undefined) ?? "http://127.0.0.1:8787"
  : "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly errors: ErrorItem[] = [],
    readonly details: string[] = [],
    /** Full error body (409 carries the current `etag`). */
    readonly body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

// --- connection state (ServerBar, token screen) -------------------------------------------

export interface Connection {
  /** `missing` = no token saved, `bad` = the server returned 401. */
  auth: "ok" | "missing" | "bad";
  offline: boolean;
}

let conn: Connection = { auth: localStorage.getItem(TOKEN_KEY) ? "ok" : "missing", offline: false };
let connectionVersion = 0;
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

// --- requests ----------------------------------------------------------------------------

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    setConn({ auth: "missing" });
    throw new ApiError(401, t("token.missing"));
  }
  const reading = !init.method || init.method === "GET" || init.method === "HEAD";
  const version = connectionVersion;
  let res: Response;
  try {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (init.body && !(init.body instanceof Blob)) headers["Content-Type"] = "application/json";  // a Blob = raw upload
    const fetchOnce = () => fetch(API_BASE + path, { ...init, headers, ...(reading && { signal: AbortSignal.timeout(20_000) }) });
    try {
      res = await fetchOnce();
    } catch (error) {
      if (!reading) throw error;
      await new Promise((resolve) => setTimeout(resolve, 1500));
      res = await fetchOnce();
    }
  } catch {
    if (reading && version === connectionVersion) setConn({ offline: true });
    // the browser's message (“Failed to fetch”) says nothing useful; SaveNote shows this one
    throw new ApiError(0, t("server.unreachable"));
  }
  connectionVersion++;
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

/** File ETag without downloading it (`HEAD …/files/<path>`, quoted `ETag` header). */
export const headEtag = async (path: string): Promise<string | null> =>
  (await request(path, { method: "HEAD" })).headers.get("ETag")?.replace(/^(W\/)?"|"$/g, "") ?? null;

/** Write (edit operation, starting a run): JSON body, JSON response; error → ApiError. */
export const send = async <T>(method: string, path: string, body?: unknown): Promise<T> =>
  (await request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })).json();

/** `POST /projects/<p>/uploads` (api.md Uploads): the raw bytes of one image for a `file`/`files` input. */
export interface Uploaded { upload_id: string; format: string; width: number; height: number; bytes: number }
export const upload = async (project: string, file: Blob): Promise<Uploaded> =>
  (await request(`/projects/${enc(project)}/uploads`, { method: "POST", body: file })).json();

/** Response of an edit operation (api.md “Editing”). */
export interface Saved {
  etag: string | null;
  errors: ErrorItem[];
}

export const enc = encodeURIComponent;

// --- read hook ---------------------------------------------------------------------------

export interface Loaded<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/** Loads `path` (null = nothing); `poll(data)` returns in how many ms to load again (null = don't).
 *  An unreachable server is retried after 5 s (ServerBar “retrying…”). */
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
    const revalidate = () => { clearTimeout(timer); run(); };
    const visible = () => { if (!document.hidden) revalidate(); };
    window.addEventListener("online", revalidate);
    document.addEventListener("visibilitychange", visible);
    return () => {
      alive = false;
      clearTimeout(timer);
      window.removeEventListener("online", revalidate);
      document.removeEventListener("visibilitychange", visible);
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
