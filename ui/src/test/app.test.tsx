import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  it("no token → token screen, nothing is requested", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    expect(screen.getByRole("heading", { name: "Server token" })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("the token screen has the language switch; picking Czech saves it and reloads", () => {
    vi.stubGlobal("fetch", vi.fn());
    const reload = vi.fn();
    vi.stubGlobal("location", { ...location, reload });
    render(<App />);
    const lang = screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement;
    expect(lang.value).toBe("en");
    fireEvent.change(lang, { target: { value: "cs" } });
    expect(localStorage.getItem("agencast.lang")).toBe("cs");
    expect(reload).toHaveBeenCalled();
  });

  it("Czech locale: the token screen in Czech", async () => {
    localStorage.setItem("agencast.lang", "cs");
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn());
    const { App: CzechApp } = await import("../App");
    render(<CzechApp />);
    expect(screen.getByRole("heading", { name: "Token serveru" })).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "Jazyk" }) as HTMLSelectElement).value).toBe("cs");
    expect(screen.getByRole("button", { name: "Uložit" })).toBeTruthy();
    vi.resetModules();
  });

  it("401 → token screen with a message; the token goes only to the header", async () => {
    const fetch = vi.fn(() => json(401, { error: "missing or invalid token (Authorization: Bearer … header)" }));
    vi.stubGlobal("fetch", fetch);
    saveToken("secret-token");
    await act(async () => render(<App />));
    expect(await screen.findByText(/The server token doesn't match/)).toBeTruthy();
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain("secret-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
  });
});

describe("run list", () => {
  const running: RunListItem = {
    run_id: "20260926-091502-ig-post-3c1f", status: "running", state: "running", scenario: "ig-post", current_nn: 4, steps_done: 3,
    started_at: "2026-09-26T09:15:02.000Z", current_step: "photo_prompt", steps_total: 8,
  };
  const done: RunListItem = { ...running, status: "succeeded", state: "succeeded", cost_usd: 0.0021, duration_s: 17.5, finished_at: "2026-09-26T09:15:20.000Z", current_step: null };

  it(`refreshes every ${RUNS_POLL_MS / 1000} s while something is running`, async () => {
    vi.useFakeTimers();
    let runs = [running];
    const fetch = vi.fn((url: string) =>
      url.includes("/runs?") ? json(200, { runs }) : url.includes("/spend") ? json(200, { day: "x", total_usd: 0, runs: [] }) : json(200, { limits: {}, scenarios: [] }));
    vi.stubGlobal("fetch", fetch);
    saveToken("t");
    const runCalls = () => fetch.mock.calls.filter(([u]) => String(u).includes("/runs?")).length;

    await act(async () => render(<RunsTab project="lumen" header={(x) => x?.meta} />));
    expect(runCalls()).toBe(1);
    expect(screen.getByText("step 4/8 · photo_prompt")).toBeTruthy();

    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS)));
    expect(runCalls()).toBe(2);

    runs = [done];
    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS)));
    expect(runCalls()).toBe(3);
    expect(screen.getByText("0.0021 USD")).toBeTruthy();

    // Nothing is running → no further request.
    await act(async () => void (await vi.advanceTimersByTimeAsync(RUNS_POLL_MS * 3)));
    expect(runCalls()).toBe(3);
  });
});
