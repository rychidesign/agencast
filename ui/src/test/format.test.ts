import { describe, expect, it } from "vitest";
import { formatCost, formatDuration, formatElapsed, formatSpend, formatWhen, runIdParts } from "../format";
import { format, t } from "../i18n";
import { href, parseHash } from "../router";

describe("cena: čtyři desetinná místa (fidelity §8)", () => {
  it.each([
    [0, "0,0000"],
    [0.0404, "0,0404"],
    [0.0812, "0,0812"],
    [1, "1,0000"],
    [0.000013128, "0,0000"],
    [0.30000000000000004, "0,3000"],
    [12.5, "12,5000"],
    [null, "–"],
  ])("%s → %s", (usd, text) => expect(formatCost(usd)).toBe(text));
  it.each([
    [0, "0,00"],
    [1.2, "1,20"],
    [0.032425, "0,03"],
    [0.0032, "0,00"],
  ])("útrata %s → %s", (usd, text) => expect(formatSpend(usd)).toBe(text));
});

describe("čas", () => {
  it("trvání", () => {
    expect(formatDuration(17.5)).toBe("17,5 s");
    expect(formatDuration(0.004)).toBe("0,0 s");
    expect(formatDuration(72)).toBe("1 min 12 s");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });
  it("od startu běžícího běhu", () => {
    const start = "2026-09-26T12:00:00Z";
    expect(formatElapsed(start, Date.parse(start) + 42_000)).toBe("00:42");
    expect(formatElapsed(start, Date.parse(start) + 725_000)).toBe("12:05");
    expect(formatElapsed(null)).toBe("–");
  });
  it("kdy", () => {
    const now = new Date(2026, 8, 26, 12, 0);
    expect(formatWhen(new Date(2026, 8, 26, 11, 48).toISOString(), now)).toBe("před 12 min");
    expect(formatWhen(new Date(2026, 8, 26, 9, 5).toISOString(), now)).toBe("dnes 9:05");
    expect(formatWhen(new Date(2026, 8, 25, 14, 3).toISOString(), now)).toBe("včera 14:03");
    expect(formatWhen(new Date(2026, 8, 20, 14, 3).toISOString(), now)).toBe("20. 9. 14:03");
  });
});

describe("ICU plurály", () => {
  it.each([[0, "0 kroků"], [1, "1 krok"], [3, "3 kroky"], [5, "5 kroků"], [1234, "1 234 kroků"]])("%s", (n, text) =>
    expect(t("count.steps", { n })).toBe(text));
  it("přesná hodnota a proměnná uvnitř tvaru", () => {
    expect(format("{n, plural, =0 {nic} one {# od {who}} other {# od {who}}}", { n: 0, who: "x" })).toBe("nic");
    expect(format("{n, plural, =0 {nic} one {# od {who}} other {# od {who}}}", { n: 1, who: "x" })).toBe("1 od x");
  });
});

describe("běhy", () => {
  it("run_id", () => {
    expect(runIdParts("20260925-141502-ig-post-9f3c")).toEqual({ scenario: "ig-post", startedAt: "2026-09-25T14:15:02Z" });
    expect(runIdParts("nesmysl")).toBeNull();
  });
});

describe("hash router", () => {
  it.each([
    ["", { page: "projects" }],
    ["#/", { page: "projects" }],
    ["#/p/thtd", { page: "project", project: "thtd", tab: "scenare", item: undefined }],
    ["#/p/thtd/agenti/copywriter", { page: "project", project: "thtd", tab: "agenti", item: "copywriter" }],
    ["#/p/thtd/scenare/ig-post?krok=kontrola", { page: "scenario", project: "thtd", scenario: "ig-post" }],
    ["#/p/thtd/behy/20260925-141502-ig-post-9f3c", { page: "run", project: "thtd", runId: "20260925-141502-ig-post-9f3c" }],
    ["#/p/thtd/nic", { page: "notFound" }],
    ["#/x", { page: "notFound" }],
  ])("%s", (hash, route) => expect(parseHash(hash).route).toEqual(route));

  it("query a kódování", () => {
    expect(parseHash("#/p/a/behy/r?krok=navrh/copy").query.get("krok")).toBe("navrh/copy");
    expect(href("můj projekt", "scenare", "ig-post", { krok: "copy", rezim: undefined })).toBe("#/p/m%C5%AFj%20projekt/scenare/ig-post?krok=copy");
    expect(parseHash(href("můj projekt", "behy")).route).toEqual({ page: "project", project: "můj projekt", tab: "behy", item: undefined });
  });
});
