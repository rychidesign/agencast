// Rozpracovaný scénář (§4 návrhu, model ukládání): GUI drží strom kroků lokálně a při Uložit
// ho převede na editační operace API (api.md „Editace“) v pořadí, každou s otiskem `etag`.
// Soubor je pravda — YAML GUI nesestavuje, posílá jen pole kroků a adresy.
import { send, type Saved } from "./api";
import type { ErrorItem, IoSpec, Scenario, Step, StepType } from "./types";

type Obj = Record<string, unknown>;

/** Krok rozpracovaného stromu: `uid` drží identitu přes přejmenování (u kroků z disku = původní id). */
export type WStep = Step & {
  uid: string;
  branches?: Record<string, WStep[]>;
  cases?: Record<string, WStep[]>;
  default?: WStep[] | null;
};

export interface Header {
  description: string;
  inputs: Record<string, IoSpec> | null;
  outputs: Record<string, IoSpec> | null;
  callable: boolean;
}

export interface Draft {
  header: Header;
  steps: WStep[];
}

/** Seznam kroků: hlavní (`parent: null`), nebo větev kontejneru (`key` jako v adrese kroku). */
export interface ListRef {
  parent: string | null;
  key: string[];
}

/** Kam vložit: za krok, nebo na začátek seznamu. */
export type Anchor = { after: string } | { list: ListRef };

export const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const clone = <T>(v: T): T => structuredClone(v);
export const deepEqual = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

// --- převod z API a zpět -----------------------------------------------------------------

export function adopt(steps: Step[]): WStep[] {
  return steps.map(({ branches, cases, default: def, ...rest }) => {
    const w: WStep = { ...clone(rest), uid: rest.id };
    if (branches) w.branches = mapValues(branches, adopt);
    if (cases) w.cases = mapValues(cases, adopt);
    if (def !== undefined) w.default = def && adopt(def);
    return w;
  });
}

export function draftOf(s: Scenario): Draft {
  return {
    header: { description: s.description, inputs: s.inputs, outputs: s.outputs, callable: s.callable },
    steps: adopt(s.steps),
  };
}

const mapValues = <A, B>(o: Record<string, A>, f: (a: A) => B): Record<string, B> =>
  Object.fromEntries(Object.entries(o).map(([k, v]) => [k, f(v)]));

/** Seznamy kroků uvnitř kontejneru s klíčem pro adresu. */
export function listsOf(s: WStep): [string[], WStep[]][] {
  const out: [string[], WStep[]][] = [];
  for (const [b, l] of Object.entries(s.branches ?? {})) out.push([["parallel", b], l]);
  for (const [c, l] of Object.entries(s.cases ?? {})) out.push([["switch", "cases", c], l]);
  if (s.type === "switch") out.push([["switch", "default"], s.default ?? []]);
  return out;
}

export const flat = (steps: WStep[]): WStep[] => steps.flatMap((s) => [s, ...listsOf(s).flatMap(([, l]) => flat(l))]);

/** Krok jako v souboru, bez vnořených seznamů (pro merge patch). */
function rawFlat(s: WStep): Obj {
  const out: Obj = { id: s.id };
  if (s.when != null) out.when = s.when;
  return { ...out, ...s.fields };
}

/** Celý krok jako v souboru (`POST …/steps`); `keep` vybere vnořené kroky, které se posílají. */
export function raw(s: WStep, keep: (s: WStep) => boolean = () => true): Obj {
  const { [s.type ?? ""]: body, ...rest } = s.fields;
  const out: Obj = { id: s.id };
  if (s.when != null) out.when = s.when;
  Object.assign(out, rest);
  const list = (l: WStep[]) => l.filter(keep).map((x) => raw(x, keep));
  if (s.type === "parallel") out.parallel = mapValues(s.branches ?? {}, list);
  else if (s.type === "switch")
    out.switch = { ...(isObj(body) ? body : {}), cases: mapValues(s.cases ?? {}, list), default: list(s.default ?? []) };
  else if (s.type) out[s.type] = body ?? {};
  return out;
}

/** Kopie kroku jen s vnořenými kroky, které projdou `keep` (co po vložení opravdu je na disku). */
function pruned(s: WStep, keep: (s: WStep) => boolean): WStep {
  const c: WStep = { ...s };
  const list = (l: WStep[]) => l.filter(keep).map((x) => pruned(x, keep));
  if (s.branches) c.branches = mapValues(s.branches, list);
  if (s.cases) c.cases = mapValues(s.cases, list);
  if (s.default) c.default = list(s.default);
  return c;
}

/** Hodnota `null` merge patch zapsat neumí (smaže klíč, api.md) — takový krok jde upravit jen v YAML. */
export const hasNull = (v: unknown): boolean =>
  v === null || (Array.isArray(v) ? v.some(hasNull) : isObj(v) && Object.values(v).some(hasNull));

/** JSON Merge Patch (RFC 7396) z `a` na `b`; undefined = beze změny. */
export function mergePatch(a: Obj, b: Obj): Obj | undefined {
  const out: Obj = {};
  for (const k of Object.keys(a)) if (!(k in b)) out[k] = null;
  for (const [k, v] of Object.entries(b)) {
    if (deepEqual(a[k], v)) continue;
    if (isObj(a[k]) && isObj(v)) {
      const p = mergePatch(a[k] as Obj, v);
      if (p) out[k] = p;
    } else {
      if (hasNull(v)) throw new LocalError("null");
      out[k] = v;
    }
  }
  return Object.keys(out).length ? out : undefined;
}

/** Hlavička jako v souboru: prázdné mapy a `callable: false` se nepíšou (schéma prázdné `outputs` nepovolí). */
function rawHeader(h: Header): Obj {
  const out: Obj = { description: h.description };
  if (h.inputs && Object.keys(h.inputs).length) out.inputs = h.inputs;
  if (h.outputs && Object.keys(h.outputs).length) out.outputs = h.outputs;
  if (h.callable) out.callable = true;
  return out;
}

/** Chyba, kterou GUI pozná před odesláním (`code` = klíč v cs.json `save.local.*`). */
export class LocalError extends Error {
  constructor(readonly code: string, readonly step?: string) {
    super(code);
  }
}

// --- hledání a adresy ---------------------------------------------------------------------

interface Place {
  list: WStep[];
  index: number;
  ref: ListRef;
}

export function locate(steps: WStep[], uid: string, ref: ListRef = { parent: null, key: [] }): Place | undefined {
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    if (s.uid === uid) return { list: steps, index: i, ref };
    for (const [key, l] of listsOf(s)) {
      const found = locate(l, uid, { parent: s.uid, key });
      if (found) return found;
    }
  }
  return undefined;
}

export const findStep = (steps: WStep[], uid: string) => {
  const p = locate(steps, uid);
  return p && p.list[p.index];
};

export function getList(steps: WStep[], ref: ListRef): WStep[] | undefined {
  if (ref.parent === null) return steps;
  const p = findStep(steps, ref.parent);
  if (!p) return undefined;
  return listsOf(p).find(([k]) => k.join("/") === ref.key.join("/"))?.[1];
}

/** Adresa kroku v dokumentu (api.md „Adresa kroku“). */
export function addressOf(steps: WStep[], uid: string): (string | number)[] {
  const p = locate(steps, uid);
  if (!p) throw new LocalError("missing", uid);
  return [...listAddress(steps, p.ref), p.index];
}

function listAddress(steps: WStep[], ref: ListRef): (string | number)[] {
  return ref.parent === null ? ["steps"] : [...addressOf(steps, ref.parent), ...ref.key];
}

const anchorAddress = (steps: WStep[], a: Anchor) => ("after" in a ? addressOf(steps, a.after) : listAddress(steps, a.list));
export const urlOf = (address: (string | number)[]) => address.slice(1).map((x) => encodeURIComponent(String(x))).join("/");

// --- úpravy stromu (vždy nová kopie) -------------------------------------------------------

/** Odkazy `steps.<id>.<pole>` z polí kroku (jen pro čipy „Čte z“; validuje server). */
export function refsOf(s: Pick<Step, "fields" | "when">): string[] {
  const text = JSON.stringify([s.when, s.fields]);
  return [...new Set(text.match(/\bsteps\.[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?/g) ?? [])];
}

function withDerived(s: WStep): WStep {
  const body = s.type ? s.fields[s.type] : undefined;
  const b = isObj(body) ? body : {};
  return {
    ...s, refs: refsOf(s),
    agent: typeof b.agent === "string" ? b.agent : undefined,
    call: s.type === "call" && typeof b.scenario === "string" ? b.scenario : undefined,
  };
}

export function insert(steps: WStep[], at: Anchor, step: WStep): WStep[] {
  const next = clone(steps);
  const p = "after" in at ? locate(next, at.after) : undefined;
  const list = p ? p.list : "list" in at ? getList(next, at.list) : undefined;
  if (!list) throw new LocalError("missing");
  list.splice(p ? p.index + 1 : 0, 0, step);
  return next;
}

export function remove(steps: WStep[], uid: string): WStep[] {
  const next = clone(steps);
  const p = locate(next, uid);
  if (p) p.list.splice(p.index, 1);
  return next;
}

export function update(steps: WStep[], uid: string, change: (s: WStep) => WStep): WStep[] {
  const next = clone(steps);
  const p = locate(next, uid);
  if (p) p.list[p.index] = withDerived(change(p.list[p.index]));
  return next;
}

/** Leží seznam `ref` uvnitř kroku `uid` (nebo je jeho)? Přesun do vlastní větve nejde. */
function inside(steps: WStep[], ref: ListRef, uid: string): boolean {
  for (let parent = ref.parent; parent !== null; parent = locate(steps, parent)?.ref.parent ?? null)
    if (parent === uid) return true;
  return false;
}

export function move(steps: WStep[], uid: string, to: Anchor): WStep[] {
  const target = "after" in to ? locate(steps, to.after)?.ref : to.list;
  if (!target || inside(steps, target, uid) || ("after" in to && to.after === uid)) return steps;
  const step = findStep(steps, uid);
  if (!step) return steps;
  return insert(remove(steps, uid), to, step);
}

/** Posun o jedno místo ve vlastním seznamu (Alt+↑/↓); `output` zůstává poslední. */
export function shift(steps: WStep[], uid: string, delta: -1 | 1): WStep[] {
  const next = clone(steps);
  const p = locate(next, uid);
  if (!p) return steps;
  const j = p.index + delta;
  if (j < 0 || j >= p.list.length || p.list[j].type === "output" || p.list[p.index].type === "output") return steps;
  [p.list[p.index], p.list[j]] = [p.list[j], p.list[p.index]];
  return next;
}

/** Očíslování kroků hloubkově (jako `nn` z API) pro karty. */
export function numbered(steps: WStep[]): WStep[] {
  let n = 0;
  const walk = (l: WStep[]): WStep[] =>
    l.map((s) => {
      const c: WStep = { ...s, nn: ++n };
      if (s.branches) c.branches = mapValues(s.branches, walk);
      if (s.cases) c.cases = mapValues(s.cases, walk);
      if (s.default) c.default = walk(s.default);
      return c;
    });
  return walk(steps);
}

// --- nový krok ------------------------------------------------------------------------------

let seq = 0;
/** Id nového kroku `<typ>_<n>` (§2.3, jako `step_2` v Buzz), unikátní v souboru. */
export function newId(steps: WStep[], type: StepType): string {
  const ids = new Set(flat(steps).map((s) => s.id));
  let n = 1;
  while (ids.has(`${type}_${n}`)) n++;
  return `${type}_${n}`;
}

/** Prázdné tělo typu; kontejnery začínají prázdnými větvemi (před uložením potřebují kroky). */
export function blankStep(steps: WStep[], type: StepType, keep?: Pick<WStep, "id" | "when" | "uid">): WStep {
  const id = keep?.id ?? newId(steps, type);
  const s: WStep = {
    uid: keep?.uid ?? `new:${++seq}:${id}`, nn: 0, address: [], id, type, when: keep?.when ?? null, refs: [],
    fields: type === "fail" ? { fail: "" } : type === "switch" ? { switch: { value: "" } } : type === "parallel" ? {} : { [type]: {} },
  };
  if (type === "parallel") s.branches = { a: [], b: [] };
  if (type === "switch") {
    s.cases = {};
    s.default = [];
  }
  return withDerived(s);
}

// --- uložení -------------------------------------------------------------------------------

/** Selhání uprostřed řady operací: `done` operací je na disku (s otiskem `etag`), další už ne. */
export class SaveError extends Error {
  constructor(readonly cause: unknown, readonly etag: string | null, readonly done: number) {
    super(cause instanceof Error ? cause.message : String(cause));
  }
}

/**
 * Převede rozdíl `base` → `work` na operace API a pošle je po jedné s otiskem.
 * `sim` = strom, jak je právě na disku (obvykle `base`; po „Ponechat moje“ čerstvě načtený),
 * z něj se počítají adresy. Pořadí: hlavička, změněná pole, nové větve, vložení a přesuny
 * v pořadí cílového stromu, nakonec mazání (od konce souboru, ať čtenáři zmizí dřív než čtený).
 */
export async function saveDraft(path: string, etag: string, base: Draft, work: Draft, simStart: WStep[]): Promise<Saved> {
  let tag: string | null = etag;
  let errors: ErrorItem[] = [];
  let done = 0;
  let sim = clone(simStart);
  const baseIds = new Set(flat(base.steps).map((s) => s.uid));
  const workIds = new Set(flat(work.steps).map((s) => s.uid));
  const inSim = (uid: string) => !!findStep(sim, uid);
  const isNew = (s: WStep) => !baseIds.has(s.uid) && !inSim(s.uid);
  const call = async (method: string, sub: string, body: Obj) => {
    try {
      const r = await send<Saved>(method, path + sub, { ...body, etag: tag });
      tag = r.etag;
      errors = r.errors;
      done++;
    } catch (e) {
      throw new SaveError(e, tag, done);
    }
  };
  const local = (fn: () => void) => {
    try {
      fn();
    } catch (e) {
      throw new SaveError(e, tag, done);
    }
  };

  const hp = mergePatch(rawHeader(base.header), rawHeader(work.header));
  if (hp) await call("PUT", "", { fields: hp });

  // 1) pole existujících kroků (i id, when, změna typu)
  for (const w of flat(work.steps)) {
    const b = findStep(base.steps, w.uid);
    const cur = findStep(sim, w.uid);
    if (!b || !cur) continue;
    let fields: Obj | undefined;
    const retyped = b.type !== w.type;
    local(() => (fields = retyped ? mergePatch(rawFlat(b), raw(w, isNew)) : mergePatch(rawFlat(b), rawFlat(w))));
    if (!fields) continue;
    await call("PATCH", `/steps/${urlOf(addressOf(sim, w.uid))}`, { fields });
    sim = retyped
      ? update(sim, w.uid, () => pruned(w, isNew))
      : update(sim, w.uid, (s) => ({ ...s, id: w.id, when: w.when, type: w.type, fields: w.fields }));
  }

  // 2) nové větve a případy u kontejnerů, které na disku jsou
  for (const w of flat(work.steps)) {
    const cur = findStep(sim, w.uid);
    if (!cur || !listsOf(w).length) continue;
    const have = new Set(listsOf(cur).map(([k]) => k.join("/")));
    for (const [key, list] of listsOf(w)) {
      if (have.has(key.join("/"))) continue;
      const first = list[0];
      if (!first || !isNew(first)) {
        local(() => {
          throw new LocalError("emptyBranch", w.id);
        });
        continue;
      }
      const branch = [raw(first, isNew)];
      const fields = key[0] === "parallel" ? { parallel: { [key[1]]: branch } } : { switch: { cases: { [key[2]]: branch } } };
      await call("PATCH", `/steps/${urlOf(addressOf(sim, w.uid))}`, { fields });
      sim = update(sim, w.uid, (s) => {
        const c = { ...s };
        if (key[0] === "parallel") c.branches = { ...s.branches, [key[1]]: [pruned(first, isNew)] };
        else c.cases = { ...s.cases, [key[2]]: [pruned(first, isNew)] };
        return c;
      });
    }
  }

  // 3) vložení a přesuny: každý seznam cílového stromu odshora, krok po kroku na své místo.
  // Kroky, které v seznamu nezůstanou (odejdou jinam nebo se smažou), se přeskakují — jinak by
  // se kvůli nim přesouvalo všechno pod nimi (i `output`, který musí zůstat poslední).
  const place = async (list: WStep[], ref: ListRef) => {
    const members = new Set(list.map((s) => s.uid));
    for (let i = 0; i < list.length; i++) {
      const w = list[i];
      const at: Anchor = i === 0 ? { list: ref } : { after: list[i - 1].uid };
      let to: (string | number)[] = [];
      local(() => (to = anchorAddress(sim, at)));
      if (!inSim(w.uid)) {
        await call("POST", "/steps", { after: to, step: raw(w, isNew) });
        sim = insert(sim, at, pruned(w, isNew));
      } else {
        const p = locate(sim, w.uid)!;
        const prev = p.list.slice(0, p.index).filter((s) => members.has(s.uid)).pop()?.uid;
        if (p.ref.parent === ref.parent && p.ref.key.join("/") === ref.key.join("/") && prev === list[i - 1]?.uid) continue;
        await call("POST", `/steps/${urlOf(addressOf(sim, w.uid))}/move`, { to });
        sim = move(sim, w.uid, at);
      }
    }
    for (const s of list) for (const [key, l] of listsOf(s)) await place(l, { parent: s.uid, key });
  };
  await place(work.steps, { parent: null, key: [] });

  // 4) mazání: nejvyšší smazané kroky (s nimi i vnořené), od konce souboru
  const gone = flat(sim).filter((s) => !workIds.has(s.uid)).reverse();
  for (const s of gone) {
    if (!inSim(s.uid)) continue;
    const p = locate(sim, s.uid)!;
    if (p.ref.parent !== null && !workIds.has(p.ref.parent)) continue; // smaže se s rodičem
    await call("DELETE", `/steps/${urlOf(addressOf(sim, s.uid))}`, {});
    sim = remove(sim, s.uid);
  }
  return { etag: tag, errors };
}

/** Po částečném uložení / znovunačtení: kroky, které už jsou na disku, převezmou `uid` = id z disku. */
export function rekey(work: WStep[], fresh: WStep[]): WStep[] {
  const ids = new Set(flat(fresh).map((s) => s.uid));
  const walk = (l: WStep[]): WStep[] =>
    l.map((s) => {
      const c: WStep = { ...s, uid: ids.has(s.uid) ? s.uid : ids.has(s.id) ? s.id : s.uid };
      if (s.branches) c.branches = mapValues(s.branches, walk);
      if (s.cases) c.cases = mapValues(s.cases, walk);
      if (s.default) c.default = walk(s.default);
      return c;
    });
  return walk(work);
}

/** Kroky, které smí krok `uid` číst: nad ním ve stejném seznamu a nad každým jeho kontejnerem (i s vnitřkem). */
export function visibleBefore(steps: WStep[], uid: string): WStep[] {
  const p = locate(steps, uid);
  if (!p) return [];
  const above = flat(p.list.slice(0, p.index));
  return p.ref.parent === null ? above : [...visibleBefore(steps, p.ref.parent), ...above];
}

/** Pole výstupu kroku (pro našeptávač `steps.<id>.`): podle typu, jen z polí souboru. */
export function outputFields(s: WStep, callOutputs?: Record<string, IoSpec> | null): string[] {
  const body = s.type ? s.fields[s.type] : undefined;
  const b = isObj(body) ? body : {};
  switch (s.type) {
    case "ask":
    case "task":
      return isObj(b.schema) ? Object.keys(b.schema) : ["text"];
    case "jev":
      return [...Object.keys(isObj(b.questions) ? b.questions : {}), "details"];
    case "image":
      return ["file"];
    case "set":
      return Object.keys(b);
    case "call":
      return Object.keys(callOutputs ?? {});
    default:
      return [];
  }
}
