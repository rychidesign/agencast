// Řetězce z locales/cs.json s malým ICU formátovačem: `{jmeno}` a
// `{n, plural, one {# krok} few {# kroky} other {# kroků}}` (i `=0 {…}`).
import cs from "./locales/cs.json";

const messages: Record<string, string> = cs;
const rules = new Intl.PluralRules("cs");
export const nf = new Intl.NumberFormat("cs");

type Vars = Record<string, string | number | null | undefined>;

/** Index uzavírací `}` k `{` na pozici `open`. */
function closing(s: string, open: number): number {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    if (s[i] === "{") depth++;
    else if (s[i] === "}" && --depth === 0) return i;
  }
  throw new Error(`neuzavřená závorka: ${s}`);
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
    console.warn(`chybí řetězec ${key}`);
    return key;
  }
  return format(msg, vars);
}

/** Řetězec, když existuje (štítky polí podle klíče z API), jinak `fallback`. */
export const tOr = (key: string, fallback: string) => (key in messages ? t(key) : fallback);
