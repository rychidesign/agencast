import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import {
  adopt, blankStep, insert, mergePatch, move, remove, saveDraft, shift, update, visibleBefore, type Draft, type WStep,
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

let calls: { method: string; url: string; body: Record<string, unknown> }[];
beforeEach(() => {
  calls = [];
  let n = 0;
  saveToken("t");
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ method: init.method!, url: url.replace(/^.*\/scenarios\/s/, ""), body: JSON.parse(String(init.body)) });
    return new Response(JSON.stringify({ etag: `e${++n}`, errors: [] }), { status: 200 });
  }));
});
afterEach(() => vi.unstubAllGlobals());

const save = (work: WStep[], base = adopt(BASE)) => saveDraft("/projects/p/scenarios/s", "e0", draft(base), draft(work), base);

describe("uložení = operace API v pořadí s otiskem", () => {
  it("nový krok s vyplněnými poli = jeden POST celého kroku", async () => {
    let w = adopt(BASE);
    const s = blankStep(w, "ask");
    w = insert(w, { after: "copy" }, s);
    w = update(w, s.uid, (x) => ({ ...x, fields: { ask: { agent: "copywriter", prompt: "p" } } }));
    await save(w);
    expect(calls).toEqual([
      { method: "POST", url: "/steps", body: { after: ["steps", 0], step: { id: "ask_1", ask: { agent: "copywriter", prompt: "p" } }, etag: "e0" } },
    ]);
  });

  it("úprava, přesun a smazání; každá operace nese otisk předchozí", async () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, when: "inputs.x", fields: { ask: { agent: "copywriter", prompt: "Nový" } } }));
    w = shift(w, "kontrola", -1);
    w = remove(w, "kratky");
    await save(w);
    expect(calls.map((c) => [c.method, c.url, c.body.etag])).toEqual([
      ["PATCH", "/steps/0", "e0"],
      ["POST", "/steps/1/move", "e1"],
      ["DELETE", "/steps/2/parallel/a/0", "e2"],
    ]);
    expect(calls[0].body.fields).toEqual({ when: "inputs.x", ask: { prompt: "Nový" } });
    expect(calls[1].body.to).toEqual(["steps"]);
  });

  it("přesun do větve a nový kontejner s kroky uvnitř", async () => {
    let w = adopt(BASE);
    w = move(w, "copy", { list: { parent: "varianty", key: ["parallel", "b"] } });
    const par = blankStep(w, "parallel");
    w = insert(w, { after: "kontrola" }, par);
    const inner = blankStep(w, "fail");
    w = insert(w, { list: { parent: par.uid, key: ["parallel", "a"] } }, { ...inner, fields: { fail: "x" } });
    await save(w);
    expect(calls.map((c) => [c.method, c.url])).toEqual([
      ["POST", "/steps"],
      ["POST", "/steps/0/move"],
    ]);
    // copy zůstává nahoře, dokud neodejde do větve — kvůli ní se nic jiného nepřesouvá
    expect(calls[0].body).toMatchObject({ after: ["steps", 1], step: { id: "parallel_1", parallel: { a: [{ id: "fail_1", fail: "x" }], b: [] } } });
    expect(calls[1].body.to).toEqual(["steps", 3, "parallel", "b"]);
  });

  it("smazání pole = null v merge patch; hodnotu null zapsat nejde", async () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, fields: { ask: { agent: "copywriter", prompt: "Napiš {{ inputs.tema }}" }, timeout: "1m" } }));
    await save(w);
    expect(calls[0].body.fields).toEqual({ timeout: "1m" });
    expect(mergePatch({ a: 1, b: { c: 1, d: 2 } }, { b: { c: 1 } })).toEqual({ a: null, b: { d: null } });
    expect(() => mergePatch({}, { default: { file: null } })).toThrow();
  });

  it("beze změny se nic neposílá", async () => {
    await save(adopt(BASE));
    expect(calls).toEqual([]);
  });
});

describe("našeptávač vidí jen kroky nad a ve stejné větvi", () => {
  it("krok ve větvi b", () => {
    const w = adopt(BASE);
    expect(visibleBefore(w, "dlouhy").map((s) => s.id)).toEqual(["copy", "kontrola"]);
    expect(visibleBefore(w, "out").map((s) => s.id)).toEqual(["copy", "kontrola", "varianty", "kratky", "dlouhy"]);
  });
});
