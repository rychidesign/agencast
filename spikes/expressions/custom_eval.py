"""Vlastní evaluátor výrazů D1c nad modulem ast (prototyp pro spike c).

Whitelist uzlů, žádné getattr ani eval: tečka i [] jsou jen čtení klíče
z dictu / prvku z listu. Typy jsou přísné (§5.4): bool není číslo,
porovnání napříč typy je chyba, and/or/not chtějí bool.
"""
import ast

MAX_LEN = 2000   # znaků výrazu
MAX_DEPTH = 100  # hloubka vnoření AST


class ExprError(Exception):
    # ponytail: stříška předpokládá jednořádkový výraz; víceřádkové až bude potřeba
    def __init__(self, kind: str, msg: str, expr: str, col: int | None = None):
        self.kind, self.msg, self.col = kind, msg, col
        text = f"{kind}: {msg}"
        if col is not None:
            text += f"\n  {expr}\n  {' ' * col}^"
        super().__init__(text)


def tname(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return {str: "string", list: "list", dict: "object"}.get(type(v), type(v).__name__)


def isnum(v) -> bool:
    return type(v) in (int, float)


def _join(items, sep=""):
    if not isinstance(items, list) or not isinstance(sep, str):
        raise TypeError(f"join(list, string), dostal join({tname(items)}, {tname(sep)})")
    for i, x in enumerate(items):
        if not isinstance(x, str):
            raise TypeError(f"join: prvek [{i}] je {tname(x)}, ne string")
    return sep.join(items)


def _minmax(fn):
    def f(*args):
        vals = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
        if not vals:
            raise ValueError(f"{fn.__name__}() z prázdného seznamu")
        kinds = {tname(v) for v in vals}
        if kinds not in ({"number"}, {"string"}):
            raise TypeError(f"{fn.__name__}() chce jen čísla nebo jen texty, dostal {sorted(kinds)}")
        return fn(vals)
    return f


def _conv(fn, allowed):
    def f(x):
        if tname(x) not in allowed:
            raise TypeError(f"{fn.__name__}() nepřijímá {tname(x)}")
        try:
            return fn(x)
        except ValueError:
            raise ValueError(f"{fn.__name__}({x!r}): nelze převést")
    return f


def _round(x, nd=0):
    if not isnum(x) or type(nd) is not int:
        raise TypeError(f"round(number, int), dostal round({tname(x)}, {tname(nd)})")
    return round(x) if nd == 0 else round(x, nd)


FUNCS = {
    "len": _conv(len, {"string", "list", "object"}),
    "min": _minmax(min),
    "max": _minmax(max),
    "round": _round,
    "str": _conv(str, {"string", "number", "bool", "null"}),
    "int": _conv(int, {"string", "number"}),
    "float": _conv(float, {"string", "number"}),
    "join": _join,
}

_CMP = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}


def evaluate(expr: str, ctx: dict):
    if len(expr) > MAX_LEN:
        raise ExprError("limit", f"výraz má {len(expr)} znaků, max {MAX_LEN}", expr)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        eof = not e.offset  # Python u neočekávaného konce vrací offset 0
        msg = "neočekávaný konec výrazu" if eof else e.msg
        raise ExprError("syntax", msg, expr, len(expr) if eof else e.offset - 1) from None
    except (RecursionError, MemoryError):
        raise ExprError("limit", "výraz je příliš hluboko vnořený", expr) from None
    return _Eval(expr, ctx).ev(tree.body, 0)


class _Eval:
    def __init__(self, expr, ctx):
        self.expr, self.ctx = expr, ctx

    def err(self, kind, msg, node, end_minus=None):
        """Pozice uzlu ve znacích (ast dává bajty UTF-8); end_minus = ukaž na posledních N znaků."""
        b = self.expr.encode()
        if end_minus is None:
            col = len(b[: node.col_offset].decode(errors="ignore"))
        else:
            col = len(b[: node.end_col_offset].decode(errors="ignore")) - end_minus
        return ExprError(kind, msg, self.expr, col)

    def ev(self, n, depth):
        if depth > MAX_DEPTH:
            raise self.err("limit", f"vnoření hlubší než {MAX_DEPTH}", n)
        d = depth + 1
        match n:
            case ast.Constant(value=v) if v is None or type(v) in (bool, int, float, str):
                return v
            case ast.Name(id=name):
                if name not in self.ctx:
                    raise self.err("name", f"neznámé jméno '{name}' (dostupné: {', '.join(self.ctx)})", n)
                return self.ctx[name]
            case ast.Attribute(value=base, attr=key):
                return self.key(self.ev(base, d), key, base, n)
            case ast.Subscript(value=base, slice=idx):
                obj, i = self.ev(base, d), self.ev(idx, d)
                if isinstance(obj, dict):
                    return self.key(obj, i, base, n)
                if isinstance(obj, (list, str)) and type(i) is int:
                    if -len(obj) <= i < len(obj):
                        return obj[i]
                    raise self.err("index", f"index {i} mimo rozsah '{ast.unparse(base)}' (délka {len(obj)})", n)
                raise self.err("type", f"nelze indexovat {tname(obj)} pomocí {tname(i)}", n)
            case ast.List(elts=elts):
                return [self.ev(e, d) for e in elts]
            case ast.BoolOp(op=op, values=vals):
                for v in vals:
                    r = self.bool(self.ev(v, d), v, "and" if isinstance(op, ast.And) else "or")
                    if r is isinstance(op, ast.Or):
                        return r
                return r
            case ast.UnaryOp(op=ast.Not(), operand=x):
                return not self.bool(self.ev(x, d), x, "not")
            case ast.UnaryOp(op=ast.USub() | ast.UAdd() as op, operand=x):
                v = self.ev(x, d)
                if not isnum(v):
                    raise self.err("type", f"unární mínus/plus chce number, dostal {tname(v)}", n)
                return -v if isinstance(op, ast.USub) else v
            case ast.BinOp(left=l, op=op, right=r) if type(op) in _ARITH:
                return self.arith(self.ev(l, d), op, self.ev(r, d), r)
            case ast.Compare(left=l, ops=ops, comparators=rs):
                a = self.ev(l, d)
                for op, rn in zip(ops, rs):
                    b = self.ev(rn, d)
                    if not self.compare(a, op, b, rn, rn):
                        return False
                    a = b
                return True
            case ast.Call(func=ast.Name(id=fname), args=args, keywords=[]) if fname in FUNCS:
                vals = [self.ev(a, d) for a in args if not isinstance(a, ast.Starred)]
                if len(vals) != len(args):
                    raise self.err("forbidden", "*args nejsou povolené", n)
                try:
                    return FUNCS[fname](*vals)
                except TypeError as e:
                    raise self.err("type", str(e), n) from None
                except ValueError as e:
                    raise self.err("value", str(e), n) from None
            case ast.Call(func=ast.Name(id=fname)):
                raise self.err("forbidden", f"funkce '{fname}' není povolená (povolené: {', '.join(FUNCS)})", n)
            case ast.Call():
                raise self.err("forbidden", "volání metod není povolené", n)
        raise self.err("forbidden", f"konstrukce '{type(n).__name__}' není ve výrazech povolená", n)

    def key(self, obj, key, base, n):
        if not isinstance(obj, dict):
            raise self.err("type", f"'{ast.unparse(base)}' je {tname(obj)}, ne object — nemá klíč '{key}'", n, self.keylen(n))
        if key not in obj:
            raise self.err("key", f"'{ast.unparse(base)}' nemá klíč '{key}' (dostupné: {', '.join(map(str, obj)) or '—'})",
                           n, self.keylen(n))
        return obj[key]

    @staticmethod
    def keylen(n):
        return len(n.attr) if isinstance(n, ast.Attribute) else None

    def bool(self, v, node, op):
        if type(v) is not bool:
            raise self.err("type", f"'{op}' chce bool, dostal {tname(v)} — porovnej výslovně (např. len(x) > 0)", node)
        return v

    def arith(self, a, op, b, n):
        sym = _ARITH[type(op)]
        ok = (isnum(a) and isnum(b)) or (sym == "+" and tname(a) == tname(b) in ("string", "list"))
        if not ok:
            raise self.err("type", f"nelze {tname(a)} {sym} {tname(b)}", n)
        try:
            match sym:
                case "+": return a + b
                case "-": return a - b
                case "*": return a * b
                case "/": return a / b
                case "//": return a // b
                case "%": return a % b
        except ZeroDivisionError:
            raise self.err("zero", "dělení nulou", n) from None

    def compare(self, a, op, b, rn, n):
        ta, tb = tname(a), tname(b)
        match op:
            case ast.Eq() | ast.NotEq():
                if ta != tb and "null" not in (ta, tb):
                    raise self.err("type", f"porovnání {ta} s {tb} — převeď typ výslovně (int(), str())", n)
                return (a == b) is isinstance(op, ast.Eq)
            case ast.Is() | ast.IsNot():
                if not (isinstance(rn, ast.Constant) and rn.value is None):
                    raise self.err("forbidden", "'is' jen ve tvaru 'x is None'", n)
                return (a is None) is isinstance(op, ast.Is)
            case ast.In() | ast.NotIn():
                if tb == "list":
                    r = any(tname(x) == ta and x == a for x in b)
                elif tb in ("string", "object") and ta == "string":
                    r = a in b
                else:
                    raise self.err("type", f"'in' nad {tb} s levou stranou {ta}", n)
                return r is isinstance(op, ast.In)
        if not (ta == tb == "string" or (ta == tb == "number")):
            raise self.err("type", f"nelze {ta} {_CMP[type(op)]} {tb}", n)
        match _CMP[type(op)]:
            case "<": return a < b
            case "<=": return a <= b
            case ">": return a > b
            case ">=": return a >= b


if __name__ == "__main__":
    ctx = {"steps": {"copy": {"hashtags": ["#a", "#b"]}, "k": {"s": 0.4}}, "inputs": {"jazyk": "cs"}}
    assert evaluate('steps.k.s < 0.7 and inputs.jazyk == "cs"', ctx) is True
    assert evaluate("join(steps.copy.hashtags, ' ')", ctx) == "#a #b"
    for bad, kind in [("steps.x.y", "key"), ("1 == '1'", "type"), ("'x'.upper()", "forbidden"),
                      ("__import__('os')", "forbidden"), ("1/0", "zero"), ("1 <", "syntax"),
                      ("-" * 300 + "1", "limit"), ("(" * 300 + "1" + ")" * 300, "syntax"), ("steps.copy.hashtags and True", "type")]:
        try:
            evaluate(bad, ctx)
            raise AssertionError(f"prošlo: {bad}")
        except ExprError as e:
            assert e.kind == kind, (bad, e.kind, str(e))
    print("ok")
