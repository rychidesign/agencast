import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { App } from "../App";
import { RUNS_POLL_MS, RunsTab } from "../pages/Runs";
import type { RunListItem } from "../types";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  location.hash = "#/";
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("token", () => {
  it("bez tokenu obrazovka tokenu, nic se nevolá", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    expect(screen.getByRole("heading", { name: /Token serveru/ })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("401 → obrazovka tokenu s hláškou; token jde jen do hlavičky", async () => {
    const fetch = vi.fn(() => json(401, { error: "chybí nebo nesedí token" }));
    vi.stubGlobal("fetch", fetch);
    saveToken("tajny-token");
    await act(async () => render(<App />));
    expect(await screen.findByText(/Token serveru nesedí/)).toBeTruthy();
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain("tajny-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tajny-token");
  });
});

describe("seznam běhů", () => {
  const running: RunListItem = {
    run_id: "20260926-091502-ig-post-3c1f", status: "běží", state: "running", scenario: "ig-post", current_nn: 4, steps_done: 3,
    started_at: "2026-09-26T09:15:02.000Z", current_step: "foto_prompt", steps_total: 8,
  };
  const done: RunListItem = { ...running, status: "succeeded", state: "succeeded", cost_usd: 0.0021, duration_s: 17.5, finished_at: "2026-09-26T09:15:20.000Z", current_step: null };

  it(`obnovuje se každých ${RUNS_POLL_MS / 1000} s, dokud něco běží`, async () => {
    vi.useFakeTimers();
    let runs = [running];
    const fetch = vi.fn((url: string) =>
      url.includes("/runs?") ? json(200, { runs }) : url.includes("/spend") ? json(200, { day: "x", total_usd: 0, runs: [] }) : json(200, { limits: {}, scenarios: [] }));
    vi.stubGlobal("fetch", fetch);
    saveToken("t");
    const runCalls = () => fetch.mock.calls.filter(([u]) => String(u).includes("/runs?")).length;

    await act(async () => render(<RunsTab project="thtd" />));
    expect(runCalls()).toBe(1);
    expect(screen.getByText("krok 4/8 · foto_prompt")).toBeTruthy();

    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS)));
    expect(runCalls()).toBe(2);

    runs = [done];
    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS)));
    expect(runCalls()).toBe(3);
    expect(screen.getByText("0,0021")).toBeTruthy();

    // Nic neběží → další dotaz už nepřijde.
    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS * 3)));
    expect(runCalls()).toBe(3);
  });
});
