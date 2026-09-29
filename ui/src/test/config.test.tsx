// Config (§2.8): a model alias is named like an agent (kebab case, with hyphens), not like an expression identifier (tuning 2026-09-26).
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { PageHeader } from "../components/PageHeader";
import { ConfigTab } from "../pages/Config";
import type { Project } from "../types";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const TEXT = "version: 1\nmodels:\n  smart: { id: anthropic/claude-haiku-4.5 }\n";
const doc = { path: "config.yaml", etag: "c1", text: TEXT, data: { version: 1, models: { smart: { id: "anthropic/claude-haiku-4.5" } } }, errors: [] };
const project: Project = {
  name: "p", root: "/tmp/p", models: { smart: "anthropic/claude-haiku-4.5" }, limits: {}, scenarios: [], skills: [], mcp_servers: [],
  agents: [{ name: "writer", etag: "a0", description: "Writes", model: "smart", model_id: null, skills: [], mcp: [], tools: {}, errors: [] }],
  links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] },
  env: {}, errors: [],
};

describe("Config: model alias", () => {
  beforeEach(() => saveToken("t"));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("a new alias gets hyphens while typing; an invalid name reverts and has the rule in its title", async () => {
    const calls: { method?: string; url: string; body?: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((u: string, init?: RequestInit) => {
      const url = u.replace(/^https?:\/\/[^/]+/, "");
      calls.push({ method: init?.method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === "/projects/p/files/config.yaml" && (!init?.method || init.method === "GET")) return json(200, doc);
      if (url === "/projects/p/config" && init?.method === "PUT") return json(200, { etag: "c2", errors: [] });
      return json(404, { error: `not found ${url}` });
    }));
    await act(async () => render(<ConfigTab name="p" project={project} header={(x) => <PageHeader title="Config" {...x} />} />));
    fireEvent.click(await screen.findByRole("button", { name: "+ alias" }));
    // G3/G5: one switch, one Save, the project path instead of “config.yaml · mcp.yaml”
    expect(screen.getAllByRole("radiogroup", { name: "View" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
    expect(screen.getByText("/tmp/p")).toBeTruthy();
    expect(screen.queryByText("config.yaml · mcp.yaml")).toBeNull();
    expect(screen.getByText("used by writer")).toBeTruthy();
    expect(screen.getByText("unused")).toBeTruthy();
    // smart is used by an agent → text only; the only Alias field is the new model-1
    const alias = screen.getByRole("textbox", { name: "Alias" }) as HTMLInputElement;
    expect(alias.value).toBe("model-1");

    fireEvent.change(alias, { target: { value: "1 " } }); // without a leading letter the name ends up empty
    expect(alias.value).toBe("");
    expect(alias.getAttribute("aria-invalid")).toBe("true");
    expect(alias.title).toContain("lowercase letters");
    fireEvent.blur(alias);
    expect(alias.value).toBe("model-1");
    expect(alias.title).toBe("");

    fireEvent.change(alias, { target: { value: "GPT image" } });
    expect(alias.value).toBe("gpt-image");
    expect(alias.getAttribute("aria-invalid")).toBeNull();
    fireEvent.blur(alias);
    const renamed = screen.getByRole("textbox", { name: "Alias" }) as HTMLInputElement;
    expect(renamed.value).toBe("gpt-image");
    fireEvent.change(screen.getByRole("textbox", { name: "Model id for gpt-image" }), { target: { value: "openai/gpt-image-2" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toBe("/projects/p/config");
    expect(put?.body).toEqual({ fields: { models: { "gpt-image": { id: "openai/gpt-image-2" } } }, etag: "c1" });
  });
});
