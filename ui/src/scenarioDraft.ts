// Rozpracovaný scénář ve Form režimu (§4.4, §4.6): strom kroků lokálně + v localStorage, krok zpět,
// průběžná validace přes `render` (500 ms), uložení jednou dávkou (edit.ts saveDraft), 409 → konflikt,
// 422 → chyby u karet, hlídání disku přes `HEAD files/`.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, enc, getJson, headEtag } from "./api";
import { deepEqual, draftOf, LocalError, planErrors, planOps, renderDraft, saveDraft, type Draft, type WStep } from "./edit";
import { t } from "./i18n";
import { clock, draftKey, readDraft, useWatch, VALIDATE_MS, writeDraft, type Conflict, type SaveState } from "./textfile";
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
  const edits = useRef(0);
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

  /** `keepEdits`: když uživatel mezitím začal upravovat, načtení nic nepřepíše (změnu na disku pak ohlásí hlídání). */
  const load = useCallback(async (quiet = false, keepEdits = false) => {
    const at = edits.current;
    try {
      const s = await fetchServer();
      if (keepEdits && edits.current !== at) return s;
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
    edits.current++;
    setWork(next);
    persist(next);
    if (state.kind !== "saving") setState({ kind: "idle" });
  };

  const undo = () => {
    const prev = past[past.length - 1];
    if (!prev) return;
    setPast(past.slice(0, -1));
    lastKey.current = undefined;
    edits.current++;
    setWork(prev);
    persist(prev);
    setState({ kind: "idle" });
  };

  // průběžná validace rozpracovaného stavu: `render` vrátí všechny chyby výsledku bez zápisu
  useEffect(() => {
    if (!active || !server || !base || !work) return;
    if (!dirty) {
      setErrors(server.sc.errors);
      return;
    }
    let alive = true;
    const timer = setTimeout(async () => {
      const sim = rebase?.sim ?? base.draft.steps;
      try {
        const r = await renderDraft(url, rebase?.etag ?? base.etag, base.draft, work, sim);
        if (alive) setErrors(r.errors.filter((e) => !e.file || e.file === path));
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 422) setErrors(planErrors(e, planOps(base.draft, work, sim)).filter((x) => !x.file || x.file === path));
        else if (e instanceof LocalError) setErrors([{ message: t(`save.local.${e.code}`, { step: e.step ?? "" }), step: e.step }]);
        // 409 a nedostupný server: konflikt hlásí hlídání disku, spojení ServerBar
      }
    }, VALIDATE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [work, base, rebase, active, server]);

  useWatch(async () => {
    if (!server || busy.current) return;
    try {
      const etag = await headEtag(`/projects/${enc(project)}/files/${path}`);
      if (etag === (rebase?.etag ?? server.sc.etag)) return;
      if (!dirty) {
        await load(true);
        setState({ kind: "reloaded", at: clock() });
      } else if (!conflict) setConflict({ etag });
    } catch {
      /* ServerBar */
    }
  }, active && !!server);

  const save = async (): Promise<boolean> => {
    if (!work || !base || busy.current || conflict) return false;
    busy.current = true;
    setState({ kind: "saving" });
    const sim = rebase?.sim ?? base.draft.steps;
    try {
      const r = await saveDraft(url, rebase?.etag ?? base.etag, base.draft, work, sim);
      writeDraft(key, null);
      const s = await load(true);
      if (s) setErrors(r.errors.filter((e) => !e.file || e.file === path));
      setState({ kind: "saved", at: clock() });
      return true;
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setConflict({ etag: (cause.body.etag as string | null) ?? null });
        setState({ kind: "failed", message: t("save.conflict") });
      } else if (cause instanceof ApiError && cause.status === 422) {
        const errs = planErrors(cause, planOps(base.draft, work, sim)).filter((x) => !x.file || x.file === path);
        setErrors(errs);
        setState({ kind: "failed", message: t("save.rejected", { n: errs.length }) });
      } else if (cause instanceof LocalError) {
        setState({ kind: "failed", message: t(`save.local.${cause.code}`, { step: cause.step ?? "" }) });
      } else {
        setState({ kind: "failed", message: cause instanceof Error ? cause.message : String(cause) });
      }
      return false;
    } finally {
      busy.current = false;
    }
  };

  return {
    path, server, loadError, base, work, dirty, errors, state, conflict, overwrite: !!rebase, canUndo: past.length > 0,
    change, undo, save,
    reload: () => load(true, true),
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
    /** Rozpracovaný stav jako YAML text (`render`) — pro přechod do YAML bez uložení. */
    renderText: async () => {
      if (!base || !work) return undefined;
      const etag = rebase?.etag ?? base.etag;
      return { etag, text: (await renderDraft(url, etag, base.draft, work, rebase?.sim ?? base.draft.steps)).text };
    },
  };
}

export type ScenarioDraft = ReturnType<typeof useScenarioDraft>;
