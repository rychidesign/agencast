import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { getJson, saveToken, useConnection } from "../api";

const ConnectionState = () => <span data-testid="offline">{useConnection().offline ? "yes" : "no"}</span>;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("a brief outage does not show offline; two failures do and a success clears it", async () => {
  vi.useFakeTimers();
  saveToken("test");
  render(<ConnectionState />);
  const ok = () => Promise.resolve(new Response("{}"));
  const fail = () => Promise.reject(new TypeError("Failed to fetch"));
  const fetch = vi.fn().mockImplementationOnce(fail).mockImplementationOnce(ok)
    .mockImplementationOnce(fail).mockImplementationOnce(fail).mockImplementation(ok);
  vi.stubGlobal("fetch", fetch);

  let first!: Promise<unknown>;
  await act(async () => { first = getJson("/first"); await Promise.resolve(); });
  expect(screen.getByTestId("offline").textContent).toBe("no");
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); await first; });
  expect(screen.getByTestId("offline").textContent).toBe("no");

  let second!: Promise<unknown>;
  await act(async () => { second = getJson("/second").catch(() => undefined); await Promise.resolve(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); await second; });
  expect(screen.getByTestId("offline").textContent).toBe("yes");

  await act(async () => { await getJson("/third"); });
  expect(screen.getByTestId("offline").textContent).toBe("no");
  expect(fetch).toHaveBeenCalledTimes(5);
});
