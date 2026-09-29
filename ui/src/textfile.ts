// A file as text (YAML/Markdown mode, §4.5–4.6): work in progress in localStorage, live
// validation via `POST …/validate`, saving with an ETag, watching for changes on disk (`HEAD`, window focus + 5 s).
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, enc, getJson, headEtag, send, type Saved } from "./api";
import { deepEqual } from "./edit";
import { locale, t } from "./i18n";
import type { ErrorItem, FileDoc } from "./types";

export const POLL_MS = 5000;
export const VALIDATE_MS = 500;

/** Work in progress in localStorage (keyed by file; stores the ETag of the version it belongs to). */
export const draftKey = (project: string, path: string, kind = "text") => `agencast.draft.${kind}:${project}/${path}`;
export function readDraft<T>(key: string): (T & { etag: string }) | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null");
  } catch {
    return null;
  }
}
export const writeDraft = (key: string, value: object | null) =>
  value ? localStorage.setItem(key, JSON.stringify(value)) : localStorage.removeItem(key);

export const clock = () => new Date().toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });

/** Save state for the header and `aria-live`. */
export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: string }
  | { kind: "reloaded"; at: string }
  | { kind: "failed"; message: string };

/** Conflict: `etag` = ETag on disk; `stale` = the work in progress belongs to an older version (after a page reload). */
export interface Conflict {
  etag: string | null;
  stale?: boolean;
}

/** Watches the file's ETag: calls `check` on window focus and every 5 s. */
export function useWatch(check: () => void, active: boolean) {
  const ref = useRef(check);
  ref.current = check;
  useEffect(() => {
    if (!active) return;
    const run = () => { if (!document.hidden) ref.current(); };
    const timer = setInterval(run, POLL_MS);
    window.addEventListener("focus", run);
    window.addEventListener("online", run);
    document.addEventListener("visibilitychange", run);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", run);
      window.removeEventListener("online", run);
      document.removeEventListener("visibilitychange", run);
    };
  }, [active]);
}

/** Warning before leaving with unsaved changes: page reload/close and links to another GUI page
 *  (`#/…` with a different path; changing only `?step=` does not ask). The work in progress stays in localStorage anyway. */
export function useLeaveGuard(dirty: boolean) {
  const lastHash = useRef(location.hash);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    const link = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a[href^='#']");
      const href = a?.getAttribute("href");
      if (!href || e.defaultPrevented || href.split("?")[0] === location.hash.split("?")[0]) return;
      if (!window.confirm(t("leave.confirm"))) e.preventDefault();
      else lastHash.current = href;
    };
    const hash = (e: HashChangeEvent) => {
      const current = location.hash;
      const previous = lastHash.current;
      lastHash.current = current;
      if (!dirty || previous.split("?")[0] === current.split("?")[0]) return;
      if (window.confirm(t("leave.confirm"))) return;
      e.stopImmediatePropagation();
      lastHash.current = previous;
      location.hash = previous;
    };
    if (dirty) {
      window.addEventListener("beforeunload", warn);
      document.addEventListener("click", link, true);
    }
    window.addEventListener("hashchange", hash, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", link, true);
      window.removeEventListener("hashchange", hash, true);
    };
  }, [dirty]);
}

/** Syntax error = a loader error with a line number (api.md: `line` only for syntax errors and duplicate keys). */
export const syntaxError = (errors: ErrorItem[]) => errors.find((e) => e.line != null);

export interface FileDraft<T> {
  doc?: FileDoc;
  loadError?: ApiError;
  value: T;
  setValue: (v: T) => void;
  dirty: boolean;
  /** Errors of this file (live text validation, or from the last operation). */
  errors: ErrorItem[];
  validating: boolean;
  state: SaveState;
  conflict?: Conflict;
  /** After “Keep mine”, saving overwrites the version on disk (requires confirmation). */
  overwrite: boolean;
  save: () => Promise<boolean>;
  reloadFromDisk: () => void;
  keepMine: () => void;
  discard: () => void;
  diskText: () => Promise<string>;
}

export interface FileDraftOptions<T> {
  /** Form value from the loaded file (`doc.text` for text). */
  fromDoc: (doc: FileDoc) => T;
  /** Write request: method, path and body without `etag`; null = nothing to send. */
  request: (doc: FileDoc, value: T) => { method: string; url: string; body: Record<string, unknown> } | null;
  /** Text for live validation (`POST …/validate`), text mode only. */
  validateText?: (value: T) => string;
}

/**
 * File `path` in `workflows/` (api.md `files/`) as a value being edited: draft in localStorage,
 * disk watching, saving with an ETag (409 → conflict, 422 → errors). `path: null` = inactive.
 */
export function useFileDraft<T>(project: string, path: string | null, opts: FileDraftOptions<T>, kind = "text"): FileDraft<T> {
  const base = `/projects/${enc(project)}`;
  const key = path ? draftKey(project, path, kind) : "";
  const o = useRef(opts);
  o.current = opts;
  const [doc, setDoc] = useState<FileDoc>();
  const [loadError, setLoadError] = useState<ApiError>();
  const [value, setValueState] = useState<T>(undefined as T);
  const [errors, setErrors] = useState<ErrorItem[]>([]);
  const [validating, setValidating] = useState(false);
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const [conflict, setConflict] = useState<Conflict>();
  const [override, setOverride] = useState<string | null>();
  const busy = useRef(false);
  const dirty = !!doc && !deepEqual(value, o.current.fromDoc(doc));

  const load = useCallback(async (quiet = false) => {
    if (!path) return;
    try {
      const d = await getJson<FileDoc>(`${base}/files/${path}`);
      setDoc(d);
      setLoadError(undefined);
      const draft = readDraft<{ value: T }>(key);
      if (draft && !quiet && !deepEqual(draft.value, o.current.fromDoc(d))) {
        setValueState(draft.value);
        if (draft.etag !== d.etag) setConflict({ etag: d.etag, stale: true });
      } else {
        setValueState(o.current.fromDoc(d));
        writeDraft(key, null);
      }
      setErrors(d.errors);
      return d;
    } catch (e) {
      setLoadError(e as ApiError);
    }
  }, [base, path, key]);

  useEffect(() => {
    setDoc(undefined);
    setConflict(undefined);
    setOverride(undefined);
    setState({ kind: "idle" });
    void load();
  }, [load]);

  const setValue = (v: T) => {
    setValueState(v);
    if (state.kind === "failed" || state.kind === "saved") setState({ kind: "idle" });
    if (doc) writeDraft(key, deepEqual(v, o.current.fromDoc(doc)) ? null : { etag: doc.etag, value: v });
  };

  // live text validation (500 ms after the last keystroke); text equal to the disk already has errors from GET files/ (0.8.0)
  const text = doc && opts.validateText ? opts.validateText(value) : undefined;
  useEffect(() => {
    if (!doc || !path || text === undefined) return;
    if (text === doc.text) {
      setErrors(doc.errors);
      setValidating(false);
      return;
    }
    setValidating(true);
    let alive = true;
    const timer = setTimeout(async () => {
      try {
        const r = await send<{ errors: ErrorItem[] }>("POST", `${base}/validate`, { path, text });
        if (alive) setErrors(r.errors.filter((e) => e.file === path));
      } catch (e) {
        if (alive) setErrors([{ message: (e as Error).message }]);
      } finally {
        if (alive) setValidating(false);
      }
    }, VALIDATE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [text, doc, base, path]);

  useWatch(async () => {
    if (!doc || busy.current || !path) return;
    try {
      const etag = await headEtag(`${base}/files/${path}`);
      if (etag === (override ?? doc.etag)) return;
      if (!dirty) {
        const d = await getJson<FileDoc>(`${base}/files/${path}`);
        setDoc(d);
        setValueState(o.current.fromDoc(d));
        setErrors(d.errors);
        setState({ kind: "reloaded", at: clock() });
      } else if (!conflict) setConflict({ etag });
    } catch {
      /* ServerBar shows the unreachable server */
    }
  }, !!doc);

  const save = async () => {
    if (!doc || !path || busy.current) return false;
    const req = o.current.request(doc, value);
    if (!req) return true;
    busy.current = true;
    setState({ kind: "saving" });
    try {
      const r = await send<Saved>(req.method, req.url, { ...req.body, etag: override === undefined ? doc.etag : override });
      writeDraft(key, null);
      setOverride(undefined);
      setConflict(undefined);
      await load(true);
      setErrors(r.errors.filter((e) => e.file === path));
      setState({ kind: "saved", at: clock() });
      return true;
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409) setConflict({ etag: (err.body.etag as string | null) ?? null });
      if (err.status === 422) setErrors(err.errors);
      setState({ kind: "failed", message: err.status === 422 ? t("save.rejected", { n: err.errors.length }) : err.message });
      return false;
    } finally {
      busy.current = false;
    }
  };

  return {
    doc, loadError, value, setValue, dirty, errors, validating, state, conflict, overwrite: override !== undefined, save,
    reloadFromDisk: () => {
      writeDraft(key, null);
      setConflict(undefined);
      setOverride(undefined);
      return load(true);
    },
    keepMine: () => {
      setOverride(conflict?.etag ?? null);
      setConflict(undefined);
    },
    discard: () => {
      if (doc) setValue(o.current.fromDoc(doc));
    },
    diskText: async () => (await getJson<FileDoc>(`${base}/files/${path}`)).text,
  };
}

/** A file as text (YAML / Markdown mode) with live validation; `saveUrl` = a different write endpoint with the same body
 *  `{etag, text}` (skills: `PUT …/skills/<n>`). */
export function useTextFile(project: string, path: string | null, saveUrl?: string) {
  const f = useFileDraft<string>(project, path, {
    fromDoc: (d) => d.text,
    request: (_d, text) => ({ method: "PUT", url: saveUrl ?? `/projects/${enc(project)}/files/${path}`, body: { text } }),
    validateText: (text) => text,
  });
  return { ...f, text: f.value ?? "", setText: f.setValue };
}

/** Line diff (LCS) for “Show diff” (§4.6); scenario files have hundreds of lines. */
export function lineDiff(a: string, b: string): { op: " " | "-" | "+"; text: string }[] {
  const x = a.replace(/\n$/, "").split("\n");
  const y = b.replace(/\n$/, "").split("\n");
  const n = x.length;
  const m = y.length;
  // ponytail: O(n·m) memory; files over ~5000 lines would need Myers
  const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) lcs[i][j] = x[i] === y[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const out: { op: " " | "-" | "+"; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) out.push({ op: " ", text: x[i++] }), j++;
    else if (j < m && (i === n || lcs[i][j + 1] >= lcs[i + 1][j])) out.push({ op: "+", text: y[j++] });
    else out.push({ op: "-", text: x[i++] });
  }
  return out;
}
