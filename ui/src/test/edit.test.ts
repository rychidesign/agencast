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
  st("copy", "ask", { ask: { agent: "copywriter", prompt: "Write {{ inputs.topic }}" } }),
  st("check", "jev", { jev: { state: "{{ steps.copy.text }}", questions: { ok: { type: "noul", instructions: "?" } } } }),
  st("variants", "parallel", {}, {
    branches: { a: [st("short", "ask", { ask: { agent: "c", prompt: "k" } })], b: [st("long", "ask", { ask: { agent: "c", prompt: "d" } })] },
  }),
  st("out", "output", { output: { text: "{{ steps.copy.text }}" } }),
];
const header = { description: "x", inputs: null, outputs: { text: { type: "string" } }, callable: false };
const draft = (steps: WStep[]): Draft => ({ header, steps });

const plan = (work: WStep[], base = adopt(BASE)) => planOps(draft(base), draft(work), base);

describe("save = one batch of operations (api.md “Batch”)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("a new step with filled-in fields = add_step of the whole step; saveDraft sends the batch with the etag", async () => {
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

  it("update, move and delete; addresses apply to the state after the previous operations", () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, when: "inputs.x", fields: { ask: { agent: "copywriter", prompt: "New" } } }));
    w = shift(w, "check", -1);
    w = remove(w, "short");
    expect(plan(w)).toEqual([
      { op: "update_step", address: ["steps", 0], fields: { when: "inputs.x", ask: { prompt: "New" } } },
      { op: "move_step", address: ["steps", 1], to: ["steps"] },
      { op: "delete_step", address: ["steps", 2, "parallel", "a", 0] },
    ]);
  });

  it("move into a branch and a new container with steps inside; a new branch = add_branch and steps into it", () => {
    let w = adopt(BASE);
    w = move(w, "copy", { list: { parent: "variants", key: ["parallel", "b"] } });
    const par = blankStep(w, "parallel");
    w = insert(w, { after: "check" }, par);
    const inner = blankStep(w, "fail");
    w = insert(w, { list: { parent: par.uid, key: ["parallel", "a"] } }, { ...inner, fields: { fail: "x" } });
    w = update(w, "variants", (x) => ({ ...x, branches: { ...x.branches, c: [] } }));
    w = insert(w, { list: { parent: "variants", key: ["parallel", "c"] } }, { ...blankStep(w, "fail"), fields: { fail: "y" } });
    const ops = plan(w);
    expect(ops.map((o) => o.op)).toEqual(["add_branch", "add_step", "move_step", "add_step"]);
    expect(ops[0]).toEqual({ op: "add_branch", address: ["steps", 2], name: "c", steps: [] });
    // copy stays on top until it leaves for the branch — nothing else moves because of it
    expect(ops[1]).toMatchObject({ after: ["steps", 1], step: { id: "parallel_1", parallel: { a: [{ id: "fail_1", fail: "x" }], b: [] } } });
    expect(ops[2].to).toEqual(["steps", 3, "parallel", "b"]);
    expect(ops[3]).toMatchObject({ after: ["steps", 2, "parallel", "c"], step: { fail: "y" } });
  });

  it("deleting a field = null in the merge patch; a null value → replace_step of the whole step", () => {
    let w = adopt(BASE);
    w = update(w, "copy", (x) => ({ ...x, fields: { ask: { agent: "copywriter", prompt: "Write {{ inputs.topic }}" }, timeout: "1m" } }));
    expect(plan(w)).toEqual([{ op: "update_step", address: ["steps", 0], fields: { timeout: "1m" } }]);
    expect(mergePatch({ a: 1, b: { c: 1, d: 2 } }, { b: { c: 1 } })).toEqual({ a: null, b: { d: null } });
    expect(() => mergePatch({}, { default: { file: null } })).toThrow();
    w = update(adopt(BASE), "copy", (x) => ({ ...x, fields: { ...x.fields, default: { text: null } } }));
    expect(plan(w)).toEqual([{ op: "replace_step", address: ["steps", 0], step: { id: "copy", ask: BASE[0].fields.ask, default: { text: null } } }]);
  });

  it("renaming a step that is read = rename_step with rename_refs; readers already have their references rewritten in the draft", () => {
    const w = renameStep(adopt(BASE), "copy", "text");
    expect(findStep(w, "out")!.fields).toEqual({ output: { text: "{{ steps.text.text }}" } });
    expect(findStep(w, "check")!.refs).toEqual(["steps.text.text"]);
    const ops = plan(w);
    expect(ops[0]).toEqual({ op: "rename_step", address: ["steps", 0], new_id: "text", rename_refs: true });
    // rewriting the readers also sends update_step with the same value (idempotent after rename_refs)
    expect(ops.slice(1).map((o) => o.op)).toEqual(["update_step", "update_step"]);
  });

  it("no change, no operation", () => {
    expect(plan(adopt(BASE))).toEqual([]);
  });
});

describe("autocomplete sees only steps above and in the same branch", () => {
  it("step in branch b", () => {
    const w = adopt(BASE);
    expect(visibleBefore(w, "long").map((s) => s.id)).toEqual(["copy", "check"]);
    expect(visibleBefore(w, "out").map((s) => s.id)).toEqual(["copy", "check", "variants", "short", "long"]);
  });
});
