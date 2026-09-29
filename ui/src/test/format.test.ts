import { afterEach, describe, expect, it, vi } from "vitest";
import { formatCost, formatDuration, formatElapsed, formatSpend, formatWhen, runIdParts } from "../format";
import { format, t } from "../i18n";
import { href, parseHash } from "../router";

describe("cost: four decimal places (fidelity §8)", () => {
  it.each([
    [0, "0.0000"],
    [0.0404, "0.0404"],
    [0.0812, "0.0812"],
    [1, "1.0000"],
    [0.000013128, "0.0000"],
    [0.30000000000000004, "0.3000"],
    [12.5, "12.5000"],
    [1234.5, "1234.5000"],
    [null, "–"],
  ])("%s → %s", (usd, text) => expect(formatCost(usd)).toBe(text));
  it.each([
    [0, "0.00"],
    [1.2, "1.20"],
    [0.032425, "0.03"],
    [0.0032, "0.00"],
  ])("spend %s → %s", (usd, text) => expect(formatSpend(usd)).toBe(text));
});

describe("time", () => {
  it("duration (no-break spaces)", () => {
    expect(formatDuration(17.5)).toBe("17.5 s");
    expect(formatDuration(0.004)).toBe("0.0 s");
    expect(formatDuration(72)).toBe("1 min 12 s");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });
  it("since a running run started", () => {
    const start = "2026-09-26T12:00:00Z";
    expect(formatElapsed(start, Date.parse(start) + 42_000)).toBe("00:42");
    expect(formatElapsed(start, Date.parse(start) + 725_000)).toBe("12:05");
    expect(formatElapsed(null)).toBe("–");
  });
  it("when", () => {
    const now = new Date(2026, 8, 26, 12, 0);
    expect(formatWhen(new Date(2026, 8, 26, 11, 59, 40).toISOString(), now)).toBe("just now");
    expect(formatWhen(new Date(2026, 8, 26, 11, 48).toISOString(), now)).toBe("12 min ago");
    // `\s`: newer ICU puts a narrow no-break space before AM/PM
    expect(formatWhen(new Date(2026, 8, 26, 9, 5).toISOString(), now)).toMatch(/^today 9:05\sAM$/);
    expect(formatWhen(new Date(2026, 8, 25, 14, 3).toISOString(), now)).toMatch(/^yesterday 2:03\sPM$/);
    expect(formatWhen(new Date(2026, 8, 20, 14, 3).toISOString(), now)).toMatch(/^9\/20 2:03\sPM$/);
    expect(formatWhen(new Date(2025, 8, 20, 14, 3).toISOString(), now)).toMatch(/^9\/20\/2025 2:03\sPM$/);
  });
});

describe("ICU plurals", () => {
  it.each([[0, "0 steps"], [1, "1 step"], [3, "3 steps"], [5, "5 steps"], [1234, "1,234 steps"]])("%s", (n, text) =>
    expect(t("count.steps", { n })).toBe(text));
  it("exact value and a variable inside a form", () => {
    expect(format("{n, plural, =0 {none} one {# by {who}} other {# by {who}}}", { n: 0, who: "x" })).toBe("none");
    expect(format("{n, plural, =0 {none} one {# by {who}} other {# by {who}}}", { n: 1, who: "x" })).toBe("1 by x");
    expect(format("{n, plural, =0 {none} one {# by {who}} other {# by {who}}}", { n: 2, who: "x" })).toBe("2 by x");
  });
});

describe("runs", () => {
  it("run_id", () => {
    expect(runIdParts("20260925-141502-ig-post-9f3c")).toEqual({ scenario: "ig-post", startedAt: "2026-09-25T14:15:02Z" });
    expect(runIdParts("nonsense")).toBeNull();
  });
});

describe("hash router", () => {
  it.each([
    ["", { page: "projects" }],
    ["#/", { page: "projects" }],
    ["#/p/lumen", { page: "project", project: "lumen", tab: "scenarios", item: undefined }],
    ["#/p/lumen/agents/copywriter", { page: "project", project: "lumen", tab: "agents", item: "copywriter" }],
    ["#/p/lumen/scenarios/ig-post?step=check", { page: "scenario", project: "lumen", scenario: "ig-post" }],
    ["#/p/lumen/runs/20260925-141502-ig-post-9f3c", { page: "run", project: "lumen", runId: "20260925-141502-ig-post-9f3c" }],
    ["#/p/lumen/missing", { page: "notFound" }],
    ["#/x", { page: "notFound" }],
  ])("%s", (hash, route) => expect(parseHash(hash).route).toEqual(route));

  it("query and encoding", () => {
    expect(parseHash("#/p/a/runs/r?step=draft/copy").query.get("step")).toBe("draft/copy");
    expect(href("café crème", "scenarios", "ig-post", { step: "copy", mode: undefined })).toBe("#/p/caf%C3%A9%20cr%C3%A8me/scenarios/ig-post?step=copy");
    expect(parseHash(href("café crème", "runs")).route).toEqual({ page: "project", project: "café crème", tab: "runs", item: undefined });
  });
});

describe("Czech locale (agencast.lang = cs)", () => {
  afterEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("decimal comma, Czech plurals and times", async () => {
    localStorage.setItem("agencast.lang", "cs");
    vi.resetModules();
    const f = await import("../format");
    const i18n = await import("../i18n");
    expect(f.formatCost(0.0812)).toBe("0,0812");
    expect(f.formatSpend(1.2)).toBe("1,20");
    expect(f.formatDuration(17.5)).toBe("17,5 s");
    const now = new Date(2026, 8, 26, 12, 0);
    expect(f.formatWhen(new Date(2026, 8, 26, 11, 48).toISOString(), now)).toBe("před 12 min");
    expect(f.formatWhen(new Date(2026, 8, 26, 9, 5).toISOString(), now)).toBe("dnes 9:05");
    expect(f.formatWhen(new Date(2026, 8, 20, 14, 3).toISOString(), now)).toBe("20. 9. 14:03");
    expect([0, 1, 3, 5, 1234].map((n) => i18n.t("count.steps", { n }))).toEqual(["0 kroků", "1 krok", "3 kroky", "5 kroků", "1 234 kroků"]);
  });
});
