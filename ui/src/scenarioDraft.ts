// Rozpracovaný scénář ve Form režimu (§4.4, §4.6): strom kroků lokálně + v localStorage, krok zpět,
// uložení řadou operací (edit.ts saveDraft), 409 → konflikt, 422 → chyby u karet, hlídání disku.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, enc, getJson } from "./api";
import { deepEqual, draftOf, LocalError, rekey, saveDraft, SaveError, type Draft, type WStep } from "./edit";
import { t } from "./i18n";
import { clock, draftKey, readDraft, useWatch, writeDraft, type Conflict, type SaveState } from "./textfile";
import type { ErrorItem, FileDoc, Scenario } from "./types";

/** Obsah kroků bez odvozených polí (nn, refs) — podle něj se pozná neuložená změna. */
const canon = (d: Draft): unknown => {
  const step = (s: WStep): unknown => [
    s.uid, s.id, s.type, s.when, s.fields,
    s.branches && Object.entries(s.branches).map(([k, l]) => [k, l.map(step)]),
    s.cases && Object.entries(s.cases).map(([k, l]) => [k, l.map(step)]),
    s.default?.map(step),
  ];
  return [d.header, d.steps.map(step)];
};
export const sameDraft = (a: Draft, b: Draft) => deepEqual(canon(a), canon(b));

interface Snapshot {
  sc: Scenario;
  draft: Draft;
  text: string;
}

interface Stored {
  base: Draft;
  work: Draft;
  text: string;
}

export function useScenarioDraft(project: string, scenario: string, active: boolean) {
  const path = `scenarios/${scenario}.yaml`;
  const url = `/projects/${enc(project)}/scenarios/${enc(scenario)}`;
  const key = draftKey(project, path, "form");
  const [server, setServer] = useState<Snapshot>();
  const [loadError, setLoadError] = useState<ApiError>();
  /** Verze, ke které patří rozpracované změny (obvykle = server; po obnovení stránky může být starší). */
  const [base, setBase] = useState<{ etag: string; draft: Draft; text: string }>();
  const [work, setWork] = useState<Draft>();
  const [past, setPast] = useState<Draft[]>([]);
  const lastKey = useRef<string>();
  const [errors, setErrors] = useState<ErrorItem[]>([]);
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const [conflict, setConflict] = useState<Conflict>();
  /** Po „Ponechat moje“: změny se pošlou nad tuto verzi disku. */
  const [rebase, setRebase] = useState<{ etag: string; sim: WStep[] }>();
  const busy = useRef(false);
  const dirty = !!work && !!base && !sameDraft(work, base.draft);

  const fetchServer = useCallback(async (): Promise<Snapshot> => {
    for (let i = 0; ; i++) {
      const [sc, doc] = await Promise.all([getJson<Scenario>(url), getJson<FileDoc>(`/projects/${enc(project)}/files/${path}`)]);
      if (sc.etag === doc.etag || i === 2) return { sc, draft: draftOf(sc), text: doc.text };
    }
  }, [url, project, path]);

  const adoptServer = (s: Snapshot) => {
    setServer(s);
    setBase({ etag: s.sc.etag, draft: s.draft, text: s.text });
    setErrors(s.sc.errors);
  };

  const load = useCallback(async (quiet = false) => {
    try {
      const s = await fetchServer();
      setLoadError(undefined);
      adoptServer(s);
      setPast([]);
      setRebase(undefined);
      const d = quiet ? null : readDraft<Stored>(key);
      if (d && !sameDraft(d.work, d.base)) {
        setWork(d.work);
        if (d.etag !== s.sc.etag) {
          setBase({ etag: d.etag, draft: d.base, text: d.text });
          setConflict({ etag: s.sc.etag, stale: true });
        } else setConflict(undefined);
      } else {
        writeDraft(key, null);
        setWork(s.draft);
        setConflict(undefined);
      }
      return s;
    } catch (e) {
      setLoadError(e as ApiError);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchServer, key]);

  useEffect(() => {
    void load();
  }, [load]);

  const persist = (next: Draft) => {
    if (!base) return;
    writeDraft(key, sameDraft(next, base.draft) ? null : { etag: base.etag, base: base.draft, work: next, text: base.text });
  };

  /** Změna rozpracovaného stavu; stejné `coalesce` po sobě = jeden krok zpět (psaní do pole). */
  const change = (fn: (d: Draft) => Draft, coalesce?: string) => {
    if (!work) return;
    const next = fn(work);
    if (!coalesce || coalesce !== lastKey.current) setPast((p) => [...p.slice(-99), work]);
    lastKey.current = coalesce;
    setWork(next);
    persist(next);
    if (state.kind !== "saving") setState({ kind: "idle" });
  };

  const undo = () => {
    const prev = past[past.length - 1];
    if (!prev) return;
    setPast(past.slice(0, -1));
    lastKey.current = undefined;
    setWork(prev);
    persist(prev);
    setState({ kind: "idle" });
  };

  useWatch(async () => {
    if (!server || busy.current) return;
    try {
      const sc = await getJson<Scenario>(url);
      if (sc.etag === (rebase?.etag ?? server.sc.etag)) return;
      if (!dirty) {
        await load(true);
        setState({ kind: "reloaded", at: clock() });
      } else if (!conflict) setConflict({ etag: sc.etag });
    } catch {
      /* ServerBar */
    }
  }, active && !!server);

  const save = async (): Promise<boolean> => {
    if (!work || !base || busy.current || conflict) return false;
    busy.current = true;
    setState({ kind: "saving" });
    try {
      const r = await saveDraft(url, rebase?.etag ?? base.etag, base.draft, work, rebase?.sim ?? base.draft.steps);
      writeDraft(key, null);
      const s = await load(true);
      if (s) setErrors(r.errors.filter((e) => !e.file || e.file === path));
      setState({ kind: "saved", at: clock() });
      return true;
    } catch (e) {
      const err = e instanceof SaveError ? e : new SaveError(e, null, 0);
      const cause = err.cause;
      if (err.done > 0) {
        // část operací je na disku: nová základna a kroky, které už na disku jsou, převezmou uid
        const s = await fetchServer();
        adoptServer(s);
        setRebase(undefined);
        const next = { header: work.header, steps: rekey(work.steps, s.draft.steps) };
        setWork(next);
        writeDraft(key, { etag: s.sc.etag, base: s.draft, work: next, text: s.text });
      }
      const done = err.done ? ` ${t("save.partial", { n: err.done })}` : "";
      if (cause instanceof ApiError && cause.status === 409) {
        setConflict({ etag: (cause.body.etag as string | null) ?? null });
        setState({ kind: "failed", message: t("save.conflict") + done });
      } else if (cause instanceof ApiError && cause.status === 422) {
        setErrors(cause.errors);
        setState({ kind: "failed", message: t("save.rejected", { n: cause.errors.length }) + done });
      } else if (cause instanceof LocalError) {
        setState({ kind: "failed", message: t(`save.local.${cause.code}`, { step: cause.step ?? "" }) + done });
      } else {
        setState({ kind: "failed", message: (cause instanceof Error ? cause.message : String(cause)) + done });
      }
      return false;
    } finally {
      busy.current = false;
    }
  };

  return {
    path, server, loadError, base, work, dirty, errors, state, conflict, overwrite: !!rebase, canUndo: past.length > 0,
    change, undo, save,
    reload: () => load(true),
    reloadFromDisk: () => {
      writeDraft(key, null);
      void load(true);
    },
    keepMine: async () => {
      const s = await fetchServer();
      setServer(s);
      setRebase({ etag: s.sc.etag, sim: s.draft.steps });
      setConflict(undefined);
    },
    diskText: async () => (await getJson<FileDoc>(`/projects/${enc(project)}/files/${path}`)).text,
  };
}

export type ScenarioDraft = ReturnType<typeof useScenarioDraft>;
