"""Expressions and templates `{{ }}` (scenario.md §5, DESIGN D1c).

Custom evaluator over `ast` (spike (c)): node whitelist, no getattr or
eval. Dot access and `[]` only read keys/items. Strict types: bool is not a number,
comparing different types is an error (except `== null`), `and/or/not` require bool.

The same type rules (`*_rule`) are used at runtime (on values) and by `validate`
(on types known in advance, `infer`).

Static type: None = unknown; text = kind (`"string"`, `"number"`, …);
dict = object with known keys; `[t]` = list of items of type t.
"""
import ast
import json
import math
import operator
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MAX_LEN = 2000        # expression characters, checked before parsing
MAX_DEPTH = 100       # AST depth, checked before evaluation
MAX_SIZE = 100_000    # text characters / list items in the result
LITERALS = {"true": True, "false": False, "null": None}
ROOTS = ("inputs", "steps")
FUNCS = ("len", "min", "max", "round", "str", "int", "float", "join")
_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
_OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv, "%": operator.mod,
        "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}
_CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
        ast.In: "in", ast.NotIn: "not in"}
_INT_RE = re.compile(r"[+-]?[0-9]+")
_FLOAT_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
TEMPLATE_RE = re.compile(r"\{\{(.*?)\}\}", re.S)


FILE_KEYS = {"width": "number", "height": "number", "format": "string"}  # 0.18.0: `file` metadata read with a dot


@dataclass(frozen=True)
class FileRef:
    """Value of type `file`: path relative to the run directory (scenario.md File type).
    Metadata (0.18.0) do not take part in `==`; None = unknown (e.g. an SVG from an image step)."""
    path: str
    width: int | None = field(default=None, compare=False)
    height: int | None = field(default=None, compare=False)
    format: str | None = field(default=None, compare=False)  # png | jpeg | webp | gif | avif | svg+xml (image step)


class ExprError(Exception):
    """Expression/template error; `text` + `col` = line with a caret."""

    def __init__(self, msg: str, col: int | None = None, text: str | None = None):
        super().__init__(msg)
        self.msg, self.col, self.text = msg, col, text

    def __str__(self):
        if self.col is None or self.text is None:
            return self.msg
        return f"{self.msg}\n  {self.text}\n  {' ' * self.col}^"


# --- types and text conversion --------------------------------------------------

def kind(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, FileRef):
        return "file"
    return {str: "string", list: "list", dict: "object"}[type(v)]


def tkind(t) -> str | None:
    """Static type kind."""
    if isinstance(t, dict):
        return "object"
    if isinstance(t, list):
        return "list"
    return t


def to_json(v):
    return json.dumps(v, ensure_ascii=False, default=lambda o: o.path)


def to_text(v) -> str:
    """Same text as `str()` in an expression or a template within text (§5)."""
    if isinstance(v, str):
        return v
    if isinstance(v, FileRef):
        return v.path
    if v is None or isinstance(v, (bool, list, dict)):
        return to_json(v)
    return repr(v) if isinstance(v, float) else str(v)


def _check_result(v):
    if isinstance(v, float) and not math.isfinite(v):
        raise ExprError("result is not a finite number (nan or infinity)")
    if isinstance(v, (str, list)) and len(v) > MAX_SIZE:
        raise ExprError(f"result has {len(v)} characters/items, maximum {MAX_SIZE}")
    return v


# --- type rules (shared by runtime and validate; None = unknown type) --------------

def arith_rule(sym: str, a, b):
    if sym != "+":
        for k in (a, b):
            if k and k != "number":
                raise ExprError(f"'{sym}' requires numbers, got {k}")
        return "number"
    if a and b:
        if a == b and a in ("number", "string", "list"):
            return a
        hint = " — convert explicitly, e.g. str(x)" if {a, b} == {"string", "number"} else ""
        raise ExprError(f"cannot add {a} + {b}{hint}")
    k = a or b
    if k and k not in ("number", "string", "list"):
        raise ExprError(f"'+' cannot be used on {k}")
    return None


def compare_rule(op: str, a, b):
    if op in ("in", "not in"):
        if b and b not in ("list", "string", "object"):
            raise ExprError(f"'in' requires a list, string or object on the right, got {b}")
        if a and b in ("string", "object") and a != "string":
            raise ExprError(f"'in' on {b} requires a string on the left, got {a}")
        return
    if a and b and a != b and "null" not in (a, b):
        raise ExprError(f"comparing {a} with {b} — convert the type explicitly (float(), str())")
    if op not in ("==", "!="):
        for k in (a, b):
            if k and k not in ("number", "string"):
                raise ExprError(f"'{op}' only supports numbers or strings, got {k}")


def bool_rule(op: str, k):
    if k and k != "boolean":
        raise ExprError(f"'{op}' requires true/false, got {k} — compare explicitly (e.g. len(x) > 0)")


def func_rule(name: str, kinds: list):
    n = len(kinds)

    def need(*counts):
        if n not in counts:
            raise ExprError(f"{name}() requires {' or '.join(map(str, counts))} argument(s), got {n}")

    def allow(k, allowed):
        if k and k not in allowed:
            raise ExprError(f"{name}() does not accept {k} (only {', '.join(allowed)})")

    match name:
        case "len":
            need(1)
            allow(kinds[0], ("string", "list", "object"))
        case "min" | "max":
            if n == 0:
                raise ExprError(f"{name}() requires at least one argument")
            for k in kinds:
                allow(k, ("number", "list") if n == 1 else ("number",))
        case "round":
            need(1, 2)
            for k in kinds:
                allow(k, ("number",))
        case "str":
            need(1)
            return "string"
        case "int" | "float":
            need(1)
            allow(kinds[0], ("number", "string"))
        case "join":
            need(2)
            allow(kinds[0], ("list",))
            allow(kinds[1], ("string",))
            return "string"
    return "number"


def _round(x, nd):
    if nd is not None and not float(nd).is_integer():
        raise ExprError("round(): number of decimal places must be an integer")
    d = Decimal(repr(x))
    try:
        if nd is None:
            return int(d.quantize(Decimal(1), ROUND_HALF_UP))
        r = d.quantize(Decimal(1).scaleb(-int(nd)), ROUND_HALF_UP)
    except InvalidOperation:  # number has more digits than the rounding precision
        return x
    return int(r) if isinstance(x, int) else float(r)


def call_func(name: str, args: list):
    func_rule(name, [kind(a) for a in args])
    a = args[0]
    match name:
        case "len":
            return len(a)
        case "min" | "max":
            vals = a if isinstance(a, list) else args
            if not vals:
                raise ExprError(f"{name}() on an empty list")
            for i, x in enumerate(vals):
                if kind(x) != "number":
                    raise ExprError(f"{name}(): item [{i}] is {kind(x)}, not number")
            return (min if name == "min" else max)(vals)
        case "round":
            return _round(a, args[1] if len(args) == 2 else None)
        case "str":
            return _check_result(to_text(a))
        case "int":
            if isinstance(a, str):
                if not _INT_RE.fullmatch(a):
                    raise ExprError(f"int({to_json(a)}): string is not an integer")
                return int(a)
            _check_result(a)
            return int(a)
        case "float":
            if isinstance(a, str) and not _FLOAT_RE.fullmatch(a):
                raise ExprError(f"float({to_json(a)}): string is not a number")
            return _check_result(float(a))
        case "join":
            for i, x in enumerate(a):
                if not isinstance(x, str):
                    raise ExprError(f"join(): item [{i}] is {kind(x)}, not string")
            return _check_result(args[1].join(a))


# --- expression parsing -----------------------------------------------------------

def _src(expr: str) -> str:
    """Expression on one line without surrounding whitespace (YAML `>-`, `{{ x }}`)."""
    return expr.replace("\n", " ").strip()


def _col(text: str, byte_offset: int) -> int:
    """ast gives offsets in UTF-8 bytes; the caret needs characters."""
    return len(text.encode()[:byte_offset].decode(errors="ignore"))


def parse(expr: str) -> ast.expr:
    """Syntax, limits and forbidden constructs. Error = ExprError with a caret."""
    if len(expr) > MAX_LEN:
        raise ExprError(f"expression has {len(expr)} characters, maximum {MAX_LEN}")
    src = _src(expr)
    try:
        tree = ast.parse(src, mode="eval").body
    except SyntaxError as e:
        eof = not e.offset or e.offset > len(src)
        msg = "unexpected end of expression" if eof else f"syntax error ({e.msg})"
        raise ExprError(msg, len(src) if eof else e.offset - 1, src) from None
    except (RecursionError, MemoryError):
        raise ExprError("expression is nested too deeply", None, src) from None
    stack = [(tree, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise ExprError(f"nesting deeper than {MAX_DEPTH}", _col(src, getattr(node, "col_offset", 0)), src)
        stack.extend((c, depth + 1) for c in ast.iter_child_nodes(node))
    _whitelist(tree, src)
    return tree


def _whitelist(n, src):
    def bad(msg, node=n):
        raise ExprError(msg, _col(src, getattr(node, "col_offset", 0)), src)

    match n:
        case ast.Constant(value=v):
            if v is None or isinstance(v, bool):
                bad(f"unknown name '{v}' — literals are written as true, false, null")
            if type(v) not in (int, float, str):
                bad("this syntax is not allowed in expressions")
            if isinstance(v, float) and not math.isfinite(v):
                bad("number is out of range")
            return
        case ast.Name(id=name):
            if name == "item":
                bad("'item' is reserved for future foreach, unavailable in v1")
            if name not in ROOTS and name not in LITERALS:
                bad(f"unknown name '{name}' (known names: inputs, steps, true, false, null)")
            return
        case ast.Attribute(attr=attr):
            if attr.startswith("__"):
                bad("attributes and dunder (__x__) are not allowed")
        case ast.Subscript(slice=ast.Slice()):
            bad("slices (x[1:3]) are not allowed")
        case ast.Subscript() | ast.List() | ast.BoolOp():
            pass
        case ast.UnaryOp(op=op):
            if not isinstance(op, (ast.Not, ast.USub, ast.UAdd)):
                bad("this operator is not allowed")
        case ast.BinOp(op=op):
            if isinstance(op, ast.Pow):
                bad("exponentiation ** is not allowed")
            if isinstance(op, ast.FloorDiv):
                bad("integer division // is not allowed — use int(a / b)")
            if type(op) not in _ARITH:
                bad("this operator is not allowed")
        case ast.Compare(ops=ops):
            for op in ops:
                if isinstance(op, (ast.Is, ast.IsNot)):
                    bad("'is' is not allowed — write == null")
        case ast.Call(func=ast.Name(id=name), args=args, keywords=kws):
            if name not in FUNCS:
                bad(f"function '{name}' is not allowed (allowed: {', '.join(FUNCS)})")
            if kws or any(isinstance(a, ast.Starred) for a in args):
                bad("keyword arguments and *args are not allowed")
            for a in args:
                _whitelist(a, src)
            return
        case ast.Call(func=ast.Attribute()):
            bad("method calls are not allowed")
        case ast.Call(func=f):
            _whitelist(f, src)
            bad("only whitelisted functions can be called by name")
        case ast.IfExp():
            bad("conditional 'x if c else y' is not allowed")
        case ast.Lambda():
            bad("lambda is not allowed")
        case ast.ListComp() | ast.SetComp() | ast.DictComp() | ast.GeneratorExp():
            bad("comprehension ([x for x in …]) is not allowed")
        case ast.NamedExpr():
            bad("assignment := is not allowed")
        case ast.JoinedStr():
            bad("f-strings are not allowed")
        case ast.Dict():
            bad("object literal {…} is not allowed")
        case ast.Tuple():
            bad("tuples are not allowed")
        case _:
            bad(f"construct '{type(n).__name__}' is not allowed in expressions")
    for c in ast.iter_child_nodes(n):
        if not isinstance(c, (ast.expr_context, ast.boolop, ast.operator, ast.unaryop, ast.cmpop)):
            _whitelist(c, src)


def parse_path(expr: str) -> ast.expr:
    """Contents of `{{ }}`: only a path to a value (scenario.md §5 Templates)."""
    tree = parse(expr)
    src = _src(expr)
    n = tree
    while True:
        match n:
            case ast.Name(id=name) if name in ROOTS:
                return tree
            case ast.Attribute(value=v):
                n = v
            case ast.Subscript(value=v, slice=ast.Constant(value=str() | int())) | \
                    ast.Subscript(value=v, slice=ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=int()))):
                n = v
            case _:
                raise ExprError("a template may only contain a path to a value, e.g. {{ steps.copy.caption }}"
                                " — calculations belong in a set step", _col(src, n.col_offset), src)


def path_step(tree) -> str | None:
    """ID of the step referenced by the path `steps.<id>…`."""
    chain = []
    while isinstance(tree, (ast.Attribute, ast.Subscript)):
        chain.append(tree)
        tree = tree.value
    if isinstance(tree, ast.Name) and tree.id == "steps" and chain:
        first = chain[-1]
        if isinstance(first, ast.Attribute):
            return first.attr
        if isinstance(first.slice, ast.Constant):
            return first.slice.value
    return None


# --- evaluation ------------------------------------------------------------

class _Walk:
    def __init__(self, src):
        self.src = src

    def at(self, node, fn, *args, end_len: int | None = None):
        """Call a rule; add the node position to any error."""
        try:
            return fn(*args)
        except ExprError as e:
            if e.col is None:
                e.col = self.col(node, end_len)
                e.text = self.src
            raise

    def col(self, node, end_len=None):
        if end_len is not None:
            return _col(self.src, node.end_col_offset) - end_len
        return _col(self.src, node.col_offset)

    def err(self, msg, node, end_len=None):
        return ExprError(msg, self.col(node, end_len), self.src)


class _Eval(_Walk):
    def __init__(self, src, ctx):
        super().__init__(src)
        self.ctx = ctx

    def ev(self, n):
        match n:
            case ast.Constant(value=v):
                return v
            case ast.Name(id=name):
                if name in LITERALS:
                    return LITERALS[name]
                return self.ctx[name]
            case ast.Attribute(value=base, attr=key):
                return self.key(self.ev(base), key, base, n, len(key))
            case ast.Subscript(value=base, slice=idx):
                obj, i = self.ev(base), self.ev(idx)
                if isinstance(obj, (dict, FileRef)):
                    return self.key(obj, i, base, n, None)
                if isinstance(obj, list):
                    if kind(i) != "number" or not float(i).is_integer():
                        raise self.err(f"list index must be an integer, got {kind(i)}", idx)
                    i = int(i)
                    if -len(obj) <= i < len(obj):
                        return obj[i]
                    raise self.err(f"index {i} out of range for '{ast.unparse(base)}' (length {len(obj)})", idx)
                raise self.err(f"'{ast.unparse(base)}' is {kind(obj)} — only list or object can be indexed", n)
            case ast.List(elts=elts):
                return self.at(n, _check_result, [self.ev(e) for e in elts])
            case ast.BoolOp(op=op, values=vals):
                is_or = isinstance(op, ast.Or)
                for v in vals:
                    r = self.ev(v)
                    self.at(v, bool_rule, "or" if is_or else "and", kind(r))
                    if r is is_or:
                        return r
                return r
            case ast.UnaryOp(op=ast.Not(), operand=x):
                r = self.ev(x)
                self.at(x, bool_rule, "not", kind(r))
                return not r
            case ast.UnaryOp(op=op, operand=x):
                v = self.ev(x)
                if kind(v) != "number":
                    raise self.err(f"unary sign requires number, got {kind(v)}", x)
                return -v if isinstance(op, ast.USub) else v
            case ast.BinOp(left=l, op=op, right=r):
                a, b = self.ev(l), self.ev(r)
                sym = _ARITH[type(op)]
                self.at(r, arith_rule, sym, kind(a), kind(b))
                if sym in ("/", "%") and b == 0:
                    raise self.err("division by zero", r)
                return self.at(n, _check_result, _OPS[sym](a, b))
            case ast.Compare(left=l, ops=ops, comparators=rs):
                a = self.ev(l)
                for op, rn in zip(ops, rs):
                    b = self.ev(rn)
                    if not self.compare(_CMP[type(op)], a, b, rn):
                        return False
                    a = b
                return True
            case ast.Call(func=ast.Name(id=name), args=args):
                vals = [self.ev(a) for a in args]
                return self.at(n, call_func, name, vals)
        raise self.err(f"construct '{type(n).__name__}' is not allowed", n)  # parse() rejects this

    def key(self, obj, key, base, n, end_len):
        where = ast.unparse(base)
        if isinstance(obj, FileRef):  # 0.18.0: file metadata
            if not isinstance(key, str) or key not in FILE_KEYS:
                raise self.err(f"'{where}' is file — has no key '{key}' (available: {', '.join(FILE_KEYS)})", n, end_len)
            v = getattr(obj, key)
            if v is None:
                raise self.err(f"'{where}': {key} of {obj.path} is unknown (unsupported image format)", n, end_len)
            return v
        if not isinstance(obj, dict):
            raise self.err(f"'{where}' is {kind(obj)}, not object — has no key '{key}'", n, end_len)
        if not isinstance(key, str):
            raise self.err(f"object key must be a string, got {kind(key)}", n, end_len)
        if key not in obj:
            raise self.err(f"'{where}' has no key '{key}' (available: {', '.join(map(str, obj)) or '—'})", n, end_len)
        return obj[key]

    def compare(self, op, a, b, rn):
        self.at(rn, compare_rule, op, kind(a), kind(b))
        match op:
            case "in" | "not in":
                if isinstance(b, list):
                    for i, x in enumerate(b):
                        if kind(x) != kind(a):
                            raise self.err(f"'in': item [{i}] is {kind(x)}, searched value is {kind(a)}", rn)
                return (a in b) is (op == "in")
            case "==":
                return a == b and kind(a) == kind(b)
            case "!=":
                return not (a == b and kind(a) == kind(b))
        return _OPS[op](a, b)


def evaluate(expr: str, ctx: dict, tree=None):
    """Evaluate an expression over `{"inputs": …, "steps": …}`. Error = ExprError."""
    tree = tree or parse(expr)
    return _Eval(_src(expr), ctx).ev(tree)


# --- static checking (validate) --------------------------------------------

STEPS = object()  # type of the name `steps`: resolve_step handles keys


class _Infer(_Walk):
    def __init__(self, src, inputs_type, resolve_step):
        super().__init__(src)
        self.inputs_type, self.resolve_step = inputs_type, resolve_step

    def ty(self, n):
        match n:
            case ast.Constant(value=v):
                return kind(v)
            case ast.Name(id=name):
                if name in LITERALS:
                    return kind(LITERALS[name])
                return self.inputs_type if name == "inputs" else STEPS
            case ast.Attribute(value=base, attr=key):
                return self.key(self.ty(base), key, base, n, len(key))
            case ast.Subscript(value=base, slice=idx):
                t, it = self.ty(base), self.ty(idx)
                if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
                    return self.key(t, idx.value, base, n, None)
                if t is STEPS:
                    return None
                if isinstance(t, list):
                    self.need_index(it, idx)
                    return t[0]
                if tkind(t) == "list":
                    self.need_index(it, idx)
                    return None
                if t in (None, "object") or isinstance(t, dict):
                    return None
                raise self.err(f"'{ast.unparse(base)}' is {tkind(t)} — only list or object can be indexed", n)
            case ast.List(elts=elts):
                ts = {repr(self.ty(e)) for e in elts}
                return [self.ty(elts[0])] if len(ts) == 1 else [None]
            case ast.BoolOp(op=op, values=vals):
                for v in vals:
                    self.at(v, bool_rule, "or" if isinstance(op, ast.Or) else "and", tkind(self.ty(v)))
                return "boolean"
            case ast.UnaryOp(op=ast.Not(), operand=x):
                self.at(x, bool_rule, "not", tkind(self.ty(x)))
                return "boolean"
            case ast.UnaryOp(operand=x):
                k = tkind(self.ty(x))
                if k and k != "number":
                    raise self.err(f"unary sign requires number, got {k}", x)
                return "number"
            case ast.BinOp(left=l, op=op, right=r):
                a, b = self.ty(l), self.ty(r)
                return self.at(r, arith_rule, _ARITH[type(op)], tkind(a), tkind(b))
            case ast.Compare(left=l, ops=ops, comparators=rs):
                a = self.ty(l)
                for op, rn in zip(ops, rs):
                    b = self.ty(rn)
                    self.at(rn, compare_rule, _CMP[type(op)], tkind(a), tkind(b))
                    if isinstance(b, list) and tkind(b[0]) and tkind(a) and tkind(b[0]) != tkind(a):
                        raise self.err(f"'in': list items are {tkind(b[0])}, searched value is {tkind(a)}", rn)
                    a = b
                return "boolean"
            case ast.Call(func=ast.Name(id=name), args=args):
                ts = [self.ty(a) for a in args]
                r = self.at(n, func_rule, name, [tkind(t) for t in ts])
                if name in ("join", "min", "max") and ts and isinstance(ts[0], list) and tkind(ts[0][0]):
                    want = "string" if name == "join" else "number"
                    if tkind(ts[0][0]) != want:
                        raise self.err(f"{name}() requires a list of {want}, got a list of {tkind(ts[0][0])}", args[0])
                return r
        return None

    def need_index(self, it, idx):
        if tkind(it) and tkind(it) != "number":
            raise self.err(f"list index must be a number, got {tkind(it)}", idx)

    def key(self, t, key, base, n, end_len):
        if t is STEPS:
            try:
                return self.resolve_step(key)
            except ExprError as e:
                raise self.err(e.msg, n, end_len) from None
        if isinstance(t, dict):
            if key not in t:
                raise self.err(f"'{ast.unparse(base)}' has no key '{key}' (available: {', '.join(t) or '—'})", n, end_len)
            return t[key]
        k = tkind(t)
        if k == "file":  # 0.18.0: file metadata
            if key not in FILE_KEYS:
                raise self.err(f"'{ast.unparse(base)}' is file — has no key '{key}' (available: {', '.join(FILE_KEYS)})",
                               n, end_len)
            return FILE_KEYS[key]
        if k and k != "object":
            raise self.err(f"'{ast.unparse(base)}' is {k}, not object — has no key '{key}'", n, end_len)
        return None


def infer(expr: str, inputs_type: dict, resolve_step, tree=None):
    """Static expression type; errors in types known in advance = ExprError."""
    tree = tree or parse(expr)
    return _Infer(_src(expr), inputs_type, resolve_step).ty(tree)


# --- templates ------------------------------------------------------------------

def template_parts(s: str) -> list[tuple[int, int, str]]:
    """(start, end, expression) of each `{{ }}`; unclosed `{{` is an error."""
    parts = [(m.start(), m.end(), m.group(1)) for m in TEMPLATE_RE.finditer(s)]
    rest = TEMPLATE_RE.sub("", s)
    if "{{" in rest:
        i = s.find("{{", parts[-1][1] if parts else 0)
        raise ExprError("unclosed template '{{' (literal {{ cannot be written in v1)", 0, s[i:i + 40])
    return parts


def _fragment_error(e: ExprError, s: str, start: int, end: int) -> ExprError:
    """Expression error caret → position in `{{ … }}` (surrounding prompt text may span lines)."""
    inner = s[start + 2:end - 2]
    col = None if e.col is None else e.col + 2 + len(inner) - len(inner.lstrip())
    return ExprError(e.msg, col, s[start:end].replace("\n", " "))


def render(s: str, ctx: dict, null_ok=lambda tree: False):
    """Evaluate a template. Entire value = one template → value with its type;
    otherwise text. `null` is an error unless `null_ok(path tree)` says otherwise."""
    parts = template_parts(s)
    if not parts:
        return s
    out, pos = [], 0
    for start, end, expr in parts:
        try:
            tree = parse_path(expr)
            v = evaluate(expr, ctx, tree)
            if v is None and not null_ok(tree):
                raise ExprError(f"'{expr.strip()}' is null — a template cannot insert null (exception: explicit default)", 0)
        except ExprError as e:
            raise _fragment_error(e, s, start, end) from None
        if len(parts) == 1 and start == 0 and end == len(s):
            return v
        out += [s[pos:start], to_text(v)]
        pos = end
    return "".join(out + [s[pos:]])


def template_type(s: str, inputs_type: dict, resolve_step):
    """Static template type (validate). Text containing a template = string."""
    parts = template_parts(s)
    if not parts:
        return "string"
    for start, end, expr in parts:
        try:
            tree = parse_path(expr)
            t = infer(expr, inputs_type, resolve_step, tree)
            if t == "null":
                raise ExprError(f"'{expr.strip()}' is always null — a template cannot insert null", 0)
        except ExprError as e:
            raise _fragment_error(e, s, start, end) from None
        if len(parts) == 1 and start == 0 and end == len(s):
            return t
    return "string"
