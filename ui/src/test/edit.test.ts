import { afterEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import {
  adopt, blankStep, findStep, insert, mergePatch, move, planOps, remove, renameStep, saveDraft, shift, update, visibleBefore,
  type Draft, type WStep,
} from "../edit";
import type { Step } from "../types";

const st = (id: string, type: Step["type"], fields: Record<string, unknown>, extra: Partial<Step> = {}): Step => ({
  nn: 0, address: [], id, type, when: null, fields, refs: [], ...extra,
});

const BASE: Step[] = [
  st("copy", "ask", { ask: { agent: "copywriter", prompt: "Napiš {{ inputs.tema }}" } }),
  st("kontrola", "jev", { jev: { state: "{{ steps.copy.text }}", questions: { ok: { type: "noul", instructions: "?" } } } }),
  st("varianty", "parallel", {}, {
    branches: { a: [st("kratky", "ask", { ask: { agent: "c", prompt: "k" } })], b: [st("dlouhy", "ask", { ask: { agent: "c", prompt: "d" } })] },
  }),
  st("out", "output", { output: { text: "{{ steps.copy.text }}" } }),
];
const header = { description: "x", inputs: null, outputs: { text: { type: "string" } }, callable: false };
const draft = (steps: WStep[]): Draft => ({ header, steps });

const plan = (work: WStep[], base = adopt(BASE)) => planOps(draft(base), draft(work), base);

describe("uložení = jedna dávka operací (api.md „Dávka“)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("nový krok s vyplněnými poli = add_step celého kroku; saveDraft pošle dávku s otiskem", async () => {
    let w = adopt(BASE);
    const s = blankStep(w, "ask");
    w = insert(w, { after: "copy" }, s);
    w = update(w, s.uid, (x) => ({ ...x, fields: { ask: { agent: "copywriter", prompt: "p" } } }));
    const ops = [{ op: "add_step", after: ["steps", 0], step: { id: "ask_1", ask: { agent: "copywriter", prompt: "p" } } }];
    expect(plan(w)).toEqual(ops);
    const fetch = vi.fn(async () => new Response(JSON.stringify({ etag: "e1", errors: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    saveToken("t");
    const base = adopt(BASE);
    expect((await saveDraft("/projects/p/scenarios/s", "e0", draft(base), draft(w), base)).etag).toBe("e1");
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/projects\/p\/scenarios\/s\/batch$/);
    expect(JSON.parse(String(init.body))).toEqual({ etag: "e0", ops });
  });

  it("úprava, přesun a smazání; adresy platí pro stav po předchozích operacích", () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, when: "inputs.x", fields: { ask: { agent: "copywriter", prompt: "Nový" } } }));
    w = shift(w, "kontrola", -1);
    w = remove(w, "kratky");
    expect(plan(w)).toEqual([
      { op: "update_step", address: ["steps", 0], fields: { when: "inputs.x", ask: { prompt: "Nový" } } },
      { op: "move_step", address: ["steps", 1], to: ["steps"] },
      { op: "delete_step", address: ["steps", 2, "parallel", "a", 0] },
    ]);
  });

  it("přesun do větve a nový kontejner s kroky uvnitř; nová větev = add_branch a kroky do ní", () => {
    let w = adopt(BASE);
    w = move(w, "copy", { list: { parent: "varianty", key: ["parallel", "b"] } });
    const par = blankStep(w, "parallel");
    w = insert(w, { after: "kontrola" }, par);
    const inner = blankStep(w, "fail");
    w = insert(w, { list: { parent: par.uid, key: ["parallel", "a"] } }, { ...inner, fields: { fail: "x" } });
    w = update(w, "varianty", (x) => ({ ...x, branches: { ...x.branches, c: [] } }));
    w = insert(w, { list: { parent: "varianty", key: ["parallel", "c"] } }, { ...blankStep(w, "fail"), fields: { fail: "y" } });
    const ops = plan(w);
    expect(ops.map((o) => o.op)).toEqual(["add_branch", "add_step", "move_step", "add_step"]);
    expect(ops[0]).toEqual({ op: "add_branch", address: ["steps", 2], name: "c", steps: [] });
    // copy zůstává nahoře, dokud neodejde do větve — kvůli ní se nic jiného nepřesouvá
    expect(ops[1]).toMatchObject({ after: ["steps", 1], step: { id: "parallel_1", parallel: { a: [{ id: "fail_1", fail: "x" }], b: [] } } });
    expect(ops[2].to).toEqual(["steps", 3, "parallel", "b"]);
    expect(ops[3]).toMatchObject({ after: ["steps", 2, "parallel", "c"], step: { fail: "y" } });
  });

  it("smazání pole = null v merge patch; hodnota null → replace_step celého kroku", () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, fields: { ask: { agent: "copywriter", prompt: "Napiš {{ inputs.tema }}" }, timeout: "1m" } }));
    expect(plan(w)).toEqual([{ op: "update_step", address: ["steps", 0], fields: { timeout: "1m" } }]);
    expect(mergePatch({ a: 1, b: { c: 1, d: 2 } }, { b: { c: 1 } })).toEqual({ a: null, b: { d: null } });
    expect(() => mergePatch({}, { default: { file: null } })).toThrow();
    w = update(adopt(BASE), "copy", (x) => ({ ...x, fields: { ...x.fields, default: { text: null } } }));
    expect(plan(w)).toEqual([{ op: "replace_step", address: ["steps", 0], step: { id: "copy", ask: BASE[0].fields.ask, default: { text: null } } }]);
  });

  it("přejmenování čteného kroku = rename_step s rename_refs; čtenáři mají odkazy přepsané už v rozpracovaném stavu", () => {
    const w = renameStep(adopt(BASE), "copy", "text");
    expect(findStep(w, "out")!.fields).toEqual({ output: { text: "{{ steps.text.text }}" } });
    expect(findStep(w, "kontrola")!.refs).toEqual(["steps.text.text"]);
    const ops = plan(w);
    expect(ops[0]).toEqual({ op: "rename_step", address: ["steps", 0], new_id: "text", rename_refs: true });
    // přepis čtenářů pošle i update_step se stejnou hodnotou (idempotentní po rename_refs)
    expect(ops.slice(1).map((o) => o.op)).toEqual(["update_step", "update_step"]);
  });

  it("beze změny žádná operace", () => {
    expect(plan(adopt(BASE))).toEqual([]);
  });
});

describe("našeptávač vidí jen kroky nad a ve stejné větvi", () => {
  it("krok ve větvi b", () => {
    const w = adopt(BASE);
    expect(visibleBefore(w, "dlouhy").map((s) => s.id)).toEqual(["copy", "kontrola"]);
    expect(visibleBefore(w, "out").map((s) => s.id)).toEqual(["copy", "kontrola", "varianty", "kratky", "dlouhy"]);
  });
});
