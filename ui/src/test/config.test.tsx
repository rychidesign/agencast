// Config (§2.8): alias modelu má jméno jako agent (kebab, s pomlčkou), ne identifikátor výrazu (ladění 2026-09-26).
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { ConfigTab } from "../pages/Config";
import type { Project } from "../types";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const TEXT = "version: 1\nmodels:\n  chytry: { id: anthropic/claude-haiku-4.5 }\n";
const doc = { path: "config.yaml", etag: "c1", text: TEXT, data: { version: 1, models: { chytry: { id: "anthropic/claude-haiku-4.5" } } }, errors: [] };
const project: Project = {
  name: "p", root: "/tmp/p", models: { chytry: "anthropic/claude-haiku-4.5" }, limits: {}, scenarios: [], skills: [], mcp_servers: [],
  agents: [{ name: "pisatel", etag: "a0", description: "Píše", model: "chytry", model_id: null, skills: [], mcp: [], tools: {}, errors: [] }],
  links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] },
  env: {}, errors: [],
};

describe("Config: alias modelu", () => {
  beforeEach(() => saveToken("t"));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("nový alias jde přejmenovat s pomlčkou; neplatné jméno se vrátí a má pravidlo v title", async () => {
    const calls: { method?: string; url: string; body?: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((u: string, init?: RequestInit) => {
      const url = u.replace(/^https?:\/\/[^/]+/, "");
      calls.push({ method: init?.method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === "/projects/p/files/config.yaml" && (!init?.method || init.method === "GET")) return json(200, doc);
      if (url === "/projects/p/config" && init?.method === "PUT") return json(200, { etag: "c2", errors: [] });
      return json(404, { error: `není ${url}` });
    }));
    await act(async () => render(<ConfigTab name="p" project={project} />));
    fireEvent.click(await screen.findByRole("button", { name: "+ alias" }));
    // G3/G5: jeden přepínač, jedno Uložit, cesta projektu místo „config.yaml · mcp.yaml“
    expect(screen.getAllByRole("radiogroup", { name: "Zobrazení" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Uložit" })).toHaveLength(1);
    expect(screen.getByText("/tmp/p")).toBeTruthy();
    expect(screen.queryByText("config.yaml · mcp.yaml")).toBeNull();
    expect(screen.getByText("používá pisatel")).toBeTruthy();
    expect(screen.getByText("nepoužívá se")).toBeTruthy();
    // chytry používá agent → jen text; jediné pole Alias je nový model-1
    const alias = screen.getByRole("textbox", { name: "Alias" }) as HTMLInputElement;
    expect(alias.value).toBe("model-1");

    fireEvent.change(alias, { target: { value: "GPT image" } });
    expect(alias.getAttribute("aria-invalid")).toBe("true");
    expect(alias.title).toContain("malá písmena");
    fireEvent.blur(alias);
    expect(alias.value).toBe("model-1");
    expect(alias.title).toBe("");

    fireEvent.change(alias, { target: { value: "gpt-image" } });
    expect(alias.getAttribute("aria-invalid")).toBeNull();
    fireEvent.blur(alias);
    const renamed = screen.getByRole("textbox", { name: "Alias" }) as HTMLInputElement;
    expect(renamed.value).toBe("gpt-image");
    fireEvent.change(screen.getByRole("textbox", { name: "Id modelu gpt-image" }), { target: { value: "openai/gpt-image-2" } });

    fireEvent.click(screen.getByRole("button", { name: "Uložit" }));
    await act(async () => {});
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toBe("/projects/p/config");
    expect(put?.body).toEqual({ fields: { models: { "gpt-image": { id: "openai/gpt-image-2" } } }, etag: "c1" });
  });
});
