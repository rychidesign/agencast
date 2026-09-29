import { afterEach, describe, expect, it, vi } from "vitest";
import cs from "../locales/cs.json";
import en from "../locales/en.json";
import { pickLocale } from "../i18n";

const LOCALES: Record<string, Record<string, string>> = { en, cs };

/** Placeholder names (`{name}`, `{n, plural, …}`), not plural form bodies (`one {# step}`). */
const placeholders = (msg: string) =>
  new Set([...msg.matchAll(/(?<!(?:zero|one|two|few|many|other|=\d+)\s*)\{\s*([A-Za-z_]\w*)\s*[,}]/g)].map((m) => m[1]));

/** Fresh i18n module for a saved locale choice. */
async function load(lang: string | null) {
  if (lang) localStorage.setItem("agencast.lang", lang);
  else localStorage.removeItem("agencast.lang");
  vi.resetModules();
  return import("../i18n");
}

afterEach(() => localStorage.clear());

describe("locale files", () => {
  it("en and cs have the same keys", () => {
    expect(Object.keys(cs).sort()).toEqual(Object.keys(en).sort());
  });

  it("each key has the same placeholders in both locales", () => {
    const same = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every((p) => b.has(p));
    expect(Object.keys(en).filter((k) => !same(placeholders(LOCALES.cs[k] ?? ""), placeholders(LOCALES.en[k])))).toEqual([]);
    expect([...placeholders("{n, plural, =0 {none} one {# of {who}} other {# of {who}}} {x}")].sort()).toEqual(["n", "who", "x"]);
  });

  it.each(["en", "cs"])("every plural message in %s formats for 0, 1, 2 and 5", async (lang) => {
    const { t } = await load(lang);
    for (const [key, msg] of Object.entries(LOCALES[lang]).filter(([, m]) => m.includes(", plural,"))) {
      for (const n of [0, 1, 2, 5]) {
        const vars = Object.fromEntries([...placeholders(msg)].map((p) => [p, n]));
        const out = t(key, vars);
        expect(out, `${lang} ${key} n=${n}`).toContain(String(n));
        expect(out, `${lang} ${key} n=${n}`).not.toMatch(/[{}#]|plural/);
      }
    }
  });
});

describe("locale detection", () => {
  it.each([
    ["cs", ["en-US"], "cs"],
    ["en", ["cs-CZ"], "en"],
    [null, ["cs-CZ", "en"], "cs"],
    [null, ["sk", "cs"], "cs"],
    [null, ["en-US", "cs"], "en"],
    [null, ["de-DE"], "en"],
    [null, [], "en"],
    ["xx", ["cs"], "cs"],
  ] as const)("saved %s, browser %j → %s", (saved, languages, expected) => {
    expect(pickLocale(saved, languages)).toBe(expected);
  });

  it("uses the saved choice, English by default", async () => {
    expect((await load(null)).locale).toBe("en");
    expect((await load(null)).t("common.save")).toBe("Save");
    const czech = await load("cs");
    expect(czech.locale).toBe("cs");
    expect(czech.t("common.save")).toBe("Uložit");
    expect(czech.t("count.steps", { n: 3 })).toBe("3 kroky");
  });

  it("setLocale saves the choice and reloads", async () => {
    const { setLocale } = await load(null);
    const reload = vi.fn();
    vi.stubGlobal("location", { ...location, reload });
    setLocale("cs");
    expect(localStorage.getItem("agencast.lang")).toBe("cs");
    expect(reload).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("a missing key warns and returns the key", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect((await load(null)).t("no.such.key")).toBe("no.such.key");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
