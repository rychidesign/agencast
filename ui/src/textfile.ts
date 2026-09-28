// Soubor jako text (YAML/Markdown režim, §4.5–4.6): rozpracovaný text v localStorage, průběžná
// validace přes `POST …/validate`, uložení s otiskem, hlídání změn na disku (`HEAD`, fokus okna + 5 s).
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, enc, getJson, headEtag, send, type Saved } from "./api";
import { deepEqual } from "./edit";
import { t } from "./i18n";
import type { ErrorItem, FileDoc } from "./types";

export const POLL_MS = 5000;
export const VALIDATE_MS = 500;

/** Rozpracovaný stav v localStorage (klíč soubor, uvnitř otisk verze, ke které patří). */
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

export const clock = () => new Date().toLocaleTimeString("cs", { hour: "numeric", minute: "2-digit" });

/** Stav uložení pro hlavičku a `aria-live`. */
export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: string }
  | { kind: "reloaded"; at: string }
  | { kind: "failed"; message: string };

/** Konflikt: `etag` = otisk na disku; `stale` = rozpracovaný text patří ke starší verzi (po obnovení stránky). */
export interface Conflict {
  etag: string | null;
  stale?: boolean;
}

/** Hlídá otisk souboru: při fokusu okna a každých 5 s zavolá `check`. */
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

/** Varování před odchodem s neuloženými změnami: obnovení/zavření stránky i odkaz na jinou stránku GUI
 *  (`#/…` s jinou cestou; změna jen `?krok=` se neptá). Rozpracovaný stav přesto zůstává v localStorage. */
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

/** Syntaktická chyba = chyba loaderu s číslem řádku (api.md: `line` jen u syntaxe a duplicitního klíče). */
export const syntaxError = (errors: ErrorItem[]) => errors.find((e) => e.line != null);

export interface FileDraft<T> {
  doc?: FileDoc;
  loadError?: ApiError;
  value: T;
  setValue: (v: T) => void;
  dirty: boolean;
  /** Chyby tohoto souboru (průběžná validace textu, nebo z poslední operace). */
  errors: ErrorItem[];
  validating: boolean;
  state: SaveState;
  conflict?: Conflict;
  /** Po „Ponechat moje“ uloží přes verzi na disku (vyžaduje potvrzení). */
  overwrite: boolean;
  save: () => Promise<boolean>;
  reloadFromDisk: () => void;
  keepMine: () => void;
  discard: () => void;
  diskText: () => Promise<string>;
}

export interface FileDraftOptions<T> {
  /** Hodnota formuláře z načteného souboru (u textu `doc.text`). */
  fromDoc: (doc: FileDoc) => T;
  /** Zápis: metoda, cesta a tělo bez `etag`; null = není co poslat. */
  request: (doc: FileDoc, value: T) => { method: string; url: string; body: Record<string, unknown> } | null;
  /** Text k průběžné validaci (`POST …/validate`), jen v textovém režimu. */
  validateText?: (value: T) => string;
}

/**
 * Soubor `path` ve `workflows/` (api.md `files/`) jako rozpracovaná hodnota: draft v localStorage,
 * hlídání disku, uložení s otiskem (409 → konflikt, 422 → chyby). `path: null` = neaktivní.
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

  // průběžná validace textu (500 ms po posledním úhozu); text jako na disku má chyby už z GET files/ (0.8.0)
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
      /* ServerBar ukáže nedostupný server */
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

/** Soubor jako text (YAML / Markdown režim) s průběžnou validací; `saveUrl` = jiný zápis se stejným tělem
 *  `{etag, text}` (skilly: `PUT …/skills/<n>`). */
export function useTextFile(project: string, path: string | null, saveUrl?: string) {
  const f = useFileDraft<string>(project, path, {
    fromDoc: (d) => d.text,
    request: (_d, text) => ({ method: "PUT", url: saveUrl ?? `/projects/${enc(project)}/files/${path}`, body: { text } }),
    validateText: (text) => text,
  });
  return { ...f, text: f.value ?? "", setText: f.setValue };
}

/** Řádkový rozdíl (LCS) pro „Zobrazit rozdíl“ (§4.6); soubory scénářů mají stovky řádků. */
export function lineDiff(a: string, b: string): { op: " " | "-" | "+"; text: string }[] {
  const x = a.replace(/\n$/, "").split("\n");
  const y = b.replace(/\n$/, "").split("\n");
  const n = x.length;
  const m = y.length;
  // ponytail: O(n·m) paměť; pro soubory nad ~5000 řádků by chtělo Myers
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
