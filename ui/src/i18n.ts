// UI strings from locales/<locale>.json with a small ICU formatter: `{name}` and
// `{n, plural, one {# step} other {# steps}}` (also `=0 {…}`). English is primary and the per-key fallback.
import cs from "./locales/cs.json";
import en from "./locales/en.json";

export type Locale = "en" | "cs";

const LANG_KEY = "agencast.lang";

const isLocale = (l: string | null | undefined): l is Locale => l === "en" || l === "cs";

/** Saved choice > browser (first `navigator.languages` entry we have: `cs-CZ` → cs, `en-US` → en) > English. */
export function pickLocale(saved: string | null, languages: readonly string[]): Locale {
  if (isLocale(saved)) return saved;
  return languages.map((l) => l.slice(0, 2).toLowerCase()).find(isLocale) ?? "en";
}

export const locale: Locale = pickLocale(localStorage.getItem(LANG_KEY), navigator.languages ?? []);

/** Saves the choice and reloads the page (`t()` is a plain function; nothing re-renders on its own). */
export function setLocale(l: Locale) {
  localStorage.setItem(LANG_KEY, l);
  location.reload();
}

const messages: Record<string, string> = locale === "cs" ? { ...en, ...cs } : en;
const rules = new Intl.PluralRules(locale);
export const nf = new Intl.NumberFormat(locale);

type Vars = Record<string, string | number | null | undefined>;

/** Index of the `}` closing the `{` at position `open`. */
function closing(s: string, open: number): number {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    if (s[i] === "{") depth++;
    else if (s[i] === "}" && --depth === 0) return i;
  }
  throw new Error(`unclosed brace: ${s}`);
}

function plural(n: number, options: string, vars: Vars): string {
  const forms: Record<string, string> = {};
  let i = 0;
  while (i < options.length) {
    const open = options.indexOf("{", i);
    if (open < 0) break;
    const end = closing(options, open);
    forms[options.slice(i, open).trim()] = options.slice(open + 1, end);
    i = end + 1;
  }
  const form = forms[`=${n}`] ?? forms[rules.select(n)] ?? forms.other ?? "";
  return format(form.replaceAll("#", nf.format(n)), vars);
}

export function format(msg: string, vars: Vars = {}): string {
  let out = "";
  let i = 0;
  while (i < msg.length) {
    const open = msg.indexOf("{", i);
    if (open < 0) return out + msg.slice(i);
    out += msg.slice(i, open);
    const end = closing(msg, open);
    const inner = msg.slice(open + 1, end);
    const [name, kind] = inner.split(",", 2).map((s) => s.trim());
    if (kind === "plural") {
      const rest = inner.slice(inner.indexOf(",", inner.indexOf(",") + 1) + 1);
      out += plural(Number(vars[name]), rest, vars);
    } else {
      out += String(vars[name] ?? "");
    }
    i = end + 1;
  }
  return out;
}

export function t(key: string, vars?: Vars): string {
  const msg = messages[key];
  if (msg === undefined) {
    console.warn(`missing string ${key}`);
    return key;
  }
  return format(msg, vars);
}

/** The string if it exists (field labels keyed by the API), otherwise `fallback`. */
export const tOr = (key: string, fallback: string) => (key in messages ? t(key) : fallback);
