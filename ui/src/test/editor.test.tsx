// Editor scénáře, YAML režim, spuštění a formulář agenta proti falešnému API (fetch mock).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { App } from "../App";
import { filterTypes, TypePicker } from "../components/TypePicker";
import { runInputs } from "../components/RunPanel";
import type { Project, Scenario } from "../types";

const TEXT = "version: 1\nname: s\n# komentář\nsteps:\n  - id: copy\n    ask: {agent: copywriter, prompt: ahoj}\n  - id: out\n    output: {text: x}\n";

const scenario = (etag = "e0"): Scenario => ({
  name: "s", etag, description: "Test", inputs: { tema: { type: "string", required: true } },
  outputs: { text: { type: "string" } }, callable: false, steps_count: 2, types: ["ask", "output"], last_run: null, errors: [],
  steps: [
    { nn: 1, address: ["steps", 0], id: "copy", type: "ask", when: null, fields: { ask: { agent: "copywriter", prompt: "ahoj" } }, refs: [], agent: "copywriter" },
    { nn: 2, address: ["steps", 1], id: "out", type: "output", when: null, fields: { output: { text: "{{ steps.copy.text }}" } }, refs: ["steps.copy.text"] },
  ],
});

const project: Project = {
  name: "p", root: "/tmp/p", models: { chytry: "anthropic/claude-haiku-4.5" },
  limits: { run_budget_usd: 1, run_timeout: "1h", daily_budget_usd: 5 },
  scenarios: [{ ...scenario(), steps: undefined } as unknown as Scenario],
  agents: [
    { name: "copywriter", etag: "a0", description: "Píše", model: "chytry", model_id: null, skills: [], mcp: [], tools: {}, errors: [] },
    { name: "publisher", etag: "a1", description: "Publikuje", model: "chytry", model_id: null, skills: [], mcp: [], tools: {}, errors: [] },
  ],
  skills: [], errors: [],
  mcp_servers: [{ name: "instagram", type: "http", agents: ["publisher"], tools: ["publish_media"], scenarios: null }],
  links: { scenario_agent: [["s", "copywriter"]], scenario_step_agent: [["s", "copy", "copywriter"]], scenario_scenario: [], agent_skill: [], agent_server: [] },
  env: { OPENROUTER_API_KEY: true },
};

type Handler = (method: string, url: string, body: Record<string, unknown>) => [number, unknown] | undefined;
let calls: { method: string; url: string; body: Record<string, unknown> }[];
let etag: string;
let text: string;
let extra: Handler | undefined;

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  calls = [];
  etag = "e0";
  text = TEXT;
  extra = undefined;
  localStorage.clear();
  saveToken("t");
  vi.stubGlobal("fetch", vi.fn(async (u: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const url = u.replace(/^https?:\/\/[^/]+/, "");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    if (method !== "GET" && method !== "HEAD" && !url.endsWith("/render")) calls.push({ method, url, body });
    const hit = extra?.(method, url, body);
    if (hit) return json(...hit);
    if (method === "HEAD") return new Response(null, { status: 200, headers: { ETag: `"${etag}"` } });
    if (url.endsWith("/render")) return json(200, { text, tree: [], errors: [] });
    if (url === "/projects/p") return json(200, project);
    if (url === "/projects/p/scenarios/s") return json(200, scenario(etag));
    if (url.startsWith("/projects/p/files/")) {
      const path = url.slice("/projects/p/files/".length);
      if (path.startsWith("agents/"))
        return json(200, { path, etag: "a1", text: "---\n…", errors: [], frontmatter: { version: 1, name: "publisher", description: "Publikuje", model: "chytry", limits: { budget_usd: 0.2 } }, body: "Jsi správce.\n" });
      return json(200, { path, etag, text, errors: [] });
    }
    if (url === "/projects/p/validate") return json(200, { errors: [] });
    if (url === "/projects/p/spend") return json(200, { day: "x", total_usd: 0.42, runs: [] });
    if (url.endsWith("/scenarios/s/batch")) {
      etag = `e${Number(etag.slice(1)) + 1}`;
      return json(200, { etag, errors: [] });
    }
    return json(404, { error: `neznámé ${method} ${url}` });
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function openEditor(hash = "#/p/p/scenare/s") {
  location.hash = hash;
  await act(async () => void render(<App />));
  if (!hash.includes("rezim=yaml")) await screen.findByRole("button", { name: /Krok 1: ask copy/ });
}

const save = async () => {
  await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Uložit" })));
};

describe("TypePicker", () => {
  it("psaní filtruje, šipky a Enter vybírají, Esc zavře", () => {
    expect(filterTypes("j")).toEqual(["jev"]);
    expect(filterTypes("s")).toEqual(["switch", "set"]);
    expect(filterTypes("obráz")).toEqual(["image"]);
    const pick = vi.fn();
    const close = vi.fn();
    render(<TypePicker onPick={pick} onClose={close} paste="kontrola" />);
    const list = screen.getByRole("listbox");
    expect(screen.getAllByRole("option")[0].textContent).toBe("Vložit „kontrola“ sem");
    expect(screen.queryByText("output")).toBeNull();
    fireEvent.keyDown(list, { key: "s" });
    fireEvent.keyDown(list, { key: "e" });
    expect(screen.getAllByRole("option").map((o) => o.textContent?.slice(0, 3))).toEqual(["set"]);
    fireEvent.keyDown(list, { key: "Backspace" });
    fireEvent.keyDown(list, { key: "ArrowDown" });
    fireEvent.keyDown(list, { key: "Enter" });
    expect(pick).toHaveBeenCalledWith("set");
    fireEvent.keyDown(list, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});

describe("editor scénáře", () => {
  it("vložení kroku: + → typ → panel; Uložit = jedna dávka s otiskem, pak Uloženo", async () => {
    await openEditor();
    fireEvent.click(screen.getAllByRole("button", { name: "Vložit krok sem" })[1]); // mezi copy a out
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "f" });
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" });
    const panel = await screen.findByRole("complementary");
    fireEvent.change(within(panel).getByRole("combobox", { name: /Zpráva/ }), { target: { value: "Konec" } });
    expect(screen.getByText("Neuloženo")).toBeTruthy();
    await save();
    expect(calls).toEqual([{
      method: "POST", url: "/projects/p/scenarios/s/batch",
      body: { etag: "e0", ops: [{ op: "add_step", after: ["steps", 0], step: { id: "fail_1", fail: "Konec" } }] },
    }]);
    expect(await screen.findByText(/Uloženo ✓/)).toBeTruthy();
  });

  it("přesun Alt+↓, smazání klávesou Delete a krok zpět", async () => {
    await openEditor();
    fireEvent.click(screen.getAllByRole("button", { name: "Vložit krok sem" })[1]);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" }); // ask_1 za copy
    const copy = screen.getByRole("button", { name: /Krok 1: ask copy/ });
    fireEvent.keyDown(copy, { key: "ArrowDown", altKey: true });
    expect(screen.getByRole("button", { name: /Krok 2: ask copy/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Vrátit zpět" }));
    expect(screen.getByRole("button", { name: /Krok 1: ask copy/ })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("button", { name: /ask ask_1/ }), { key: "Delete" });
    expect(screen.queryByRole("button", { name: /ask ask_1/ })).toBeNull();
    // copy čte out → mazání se ptá
    fireEvent.keyDown(screen.getByRole("button", { name: /ask copy/ }), { key: "Delete" });
    expect(screen.getByRole("dialog").textContent).toContain("čtou out");
    fireEvent.click(screen.getByRole("button", { name: "Smazat i tak" }));
    await save();
    expect(calls).toEqual([{ method: "POST", url: "/projects/p/scenarios/s/batch", body: { etag: "e0", ops: [{ op: "delete_step", address: ["steps", 0] }] } }]);
  });

  it("409 → ConflictBar; Ponechat moje → Uložit se ptá na přepsání a pošle aktuální otisk", async () => {
    await openEditor();
    extra = (m, u, b) => (u.endsWith("/batch") && b.etag === "e0" ? [409, { error: "změněno", etag: "e5" }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Krok 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "nový" } });
    await save();
    expect(screen.getByRole("alert").textContent).toContain("Soubor se na disku změnil");
    etag = "e5";
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Ponechat moje" })));
    await save();
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Přepsat verzi na disku" })));
    expect(calls.map((c) => [c.method, c.body.etag])).toEqual([["POST", "e0"], ["POST", "e5"]]);
    expect(calls[1].body.ops).toEqual([{ op: "update_step", address: ["steps", 0], fields: { ask: { prompt: "nový" } } }]);
  });

  it("422 → chyba u karty i u pole, nic se nezapsalo, zůstává Neuloženo", async () => {
    await openEditor();
    const err = { message: "s.yaml: krok \"copy\", ask.prompt: krok 'nic' neexistuje", file: "scenarios/s.yaml", step: "copy", field: "ask.prompt" };
    extra = (_m, u) => (u.endsWith("/batch") ? [422, { error: "neprošla", errors: [err] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Krok 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "{{ steps.nic.text }}" } });
    await save();
    expect(screen.getByText(/neprošla kontrolou \(1 chyba\)/)).toBeTruthy();
    expect(screen.getAllByText(/krok 'nic' neexistuje/).length).toBe(2); // pod kartou a pod polem
    expect(screen.getByRole("combobox", { name: /Prompt/ }).getAttribute("aria-invalid")).toBe("true");
  });

  it("chyba operace dávky (422 s op) se ukáže u karty kroku, kterého se operace týká", async () => {
    await openEditor();
    extra = (_m, u) => (u.endsWith("/batch")
      ? [422, { error: "operace 0 dávky nejde provést", op: 0, errors: [{ message: "ops[0] update_step: adresa kroku neexistuje" }] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Krok 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "jinak" } });
    await save();
    expect(screen.getByText(/neprošla kontrolou \(1 chyba\)/)).toBeTruthy();
    const card = screen.getByRole("button", { name: /Krok 1: ask copy/ }).parentElement!;
    expect(card.textContent).toContain("ops[0] update_step");
  });

  it("průběžná validace ve Form režimu: render 500 ms po změně, chyba u karty ještě před Uložit", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await openEditor();
    const err = { message: "krok 'nic' neexistuje", file: "scenarios/s.yaml", step: "copy", field: "ask.prompt" };
    extra = (_m, u) => (u.endsWith("/render") ? [200, { text, tree: [], errors: [err] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Krok 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "{{ steps.nic.text }}" } });
    expect(screen.queryAllByText(/krok 'nic' neexistuje/).length).toBe(0);
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    expect(screen.getAllByText(/krok 'nic' neexistuje/).length).toBe(2);
    expect(calls).toEqual([]); // nic se nezapsalo
  });

  it("přejmenování čteného kroku se ptá a uloží rename_step s přepisem odkazů", async () => {
    await openEditor("#/p/p/scenare/s?krok=copy");
    fireEvent.click(await screen.findByRole("button", { name: /Podrobnosti kroku/ }));
    const id = screen.getByRole("textbox", { name: "id" });
    fireEvent.change(id, { target: { value: "text" } });
    fireEvent.blur(id);
    expect(screen.getByRole("dialog").textContent).toContain("Přepsat odkazy v 1 kroku?");
    fireEvent.click(screen.getByRole("button", { name: "Přejmenovat a přepsat odkazy" }));
    expect(screen.getByRole("button", { name: /Krok 1: ask text/ })).toBeTruthy();
    await save();
    expect(calls[0].body.ops).toEqual([
      { op: "rename_step", address: ["steps", 0], new_id: "text", rename_refs: true },
      { op: "update_step", address: ["steps", 1], fields: { output: { text: "{{ steps.text.text }}" } } },
    ]);
  });

  it("rozpracovaný stav přežije obnovení stránky (localStorage se stejným otiskem)", async () => {
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: /Krok 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "rozpracováno" } });
    cleanup();
    await openEditor();
    expect(screen.getByText(/rozpracováno/)).toBeTruthy();
    expect(screen.getByText("Neuloženo")).toBeTruthy();
  });
});

describe("YAML režim", () => {
  it("syntaktická chyba blokuje návrat do Form i Uložit; oprava je pustí a Uložit jde přes files/", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await openEditor("#/p/p/scenare/s?krok=copy&rezim=yaml");
    const area = await screen.findByRole("textbox", { name: "scenarios/s.yaml" });
    extra = (_m, u, b) => (u === "/projects/p/validate" && String(b.text).includes("[")
      ? [200, { errors: [{ message: "řádek 5: YAML nejde přečíst", file: "scenarios/s.yaml", line: 5 }] }] : undefined);
    fireEvent.change(area, { target: { value: TEXT.replace("  - id: copy", "  - id: [copy") } });
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    const form = screen.getByRole("radio", { name: "Form" });
    expect(form.getAttribute("aria-disabled")).toBe("true");
    expect(form.getAttribute("title")).toBe("Oprav YAML: řádek 5");
    fireEvent.click(form);
    expect(screen.getByRole("radio", { name: /YAML/ }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByRole("button", { name: "Uložit" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(area, { target: { value: TEXT.replace("# komentář", "# upraveno") } });
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    expect(form.getAttribute("aria-disabled")).toBeNull();
    extra = (m, u) => (m === "PUT" && u.startsWith("/projects/p/files/") ? [200, { etag: "e1", errors: [] }] : undefined);
    await save();
    expect(calls.filter((c) => c.method === "PUT")).toEqual([
      { method: "PUT", url: "/projects/p/files/scenarios/s.yaml", body: { text: TEXT.replace("# komentář", "# upraveno"), etag: "e0" } },
    ]);
  });
});

describe("spuštění z GUI", () => {
  it("povinné vstupy a výchozí hodnoty", () => {
    const specs = { tema: { type: "string", required: true }, jazyk: { type: "string", default: "cs" }, n: { type: "integer", default: 2 } };
    expect(runInputs(specs, { jazyk: "cs", n: 2 })).toEqual({ inputs: { jazyk: "cs", n: 2 }, missing: ["tema"] });
    expect(runInputs(specs, { tema: "káva", jazyk: "", n: 3 })).toEqual({ inputs: { tema: "káva", n: 3 }, missing: [] });
  });

  it("formulář: povinný vstup, limity před ostrým během, POST bez callbacku a přechod na běh", async () => {
    await openEditor();
    extra = (m, u) => (m === "POST" && u === "/projects/p/runs" ? [202, { run_id: "20260926-120000-s-ab12", queue_position: 1 }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: "Spustit" }));
    const panel = screen.getByRole("complementary");
    fireEvent.click(within(panel).getByRole("button", { name: "Spustit dry-run" }));
    expect(within(panel).getByText("Povinný vstup.")).toBeTruthy();
    expect(calls).toEqual([]);
    fireEvent.change(within(panel).getByRole("textbox", { name: /tema/ }), { target: { value: "káva" } });
    await act(async () => void fireEvent.click(within(panel).getByRole("radio", { name: /Ostrý běh/ })));
    expect(within(panel).getByText("1,00 USD")).toBeTruthy();
    expect(await within(panel).findByText(/0,4200/)).toBeTruthy();
    await act(async () => void fireEvent.click(within(panel).getByRole("button", { name: "Spustit ostrý běh" })));
    expect(calls).toEqual([{ method: "POST", url: "/projects/p/runs", body: { scenario: "s", inputs: { tema: "káva" } } }]);
    expect(location.hash).toBe("#/p/p/behy/20260926-120000-s-ab12");
  });
});

describe("formulář agenta", () => {
  it("MCP jen u povolených serverů; zaškrtnutý server → max_turns povinné a v patchi", async () => {
    location.hash = "#/p/p/agenti/publisher";
    await act(async () => void render(<App />));
    const ig = await screen.findByRole("checkbox", { name: /instagram/ });
    const turns = screen.getByRole("spinbutton", { name: /max_turns/ });
    expect(turns.getAttribute("aria-required")).toBe("false");
    fireEvent.click(ig);
    expect(turns.getAttribute("aria-required")).toBe("true");
    expect(screen.getByText("Povinné: agent má MCP server.")).toBeTruthy();
    fireEvent.change(turns, { target: { value: "6" } });
    extra = (m) => (m === "PUT" ? [200, { etag: "a2", errors: [] }] : undefined);
    await save();
    expect(calls).toEqual([{
      method: "PUT", url: "/projects/p/agents/publisher",
      body: { etag: "a1", frontmatter: { mcp: ["instagram"], tools: { instagram: ["publish_media"] }, limits: { max_turns: 6 } } },
    }]);
  });
});
