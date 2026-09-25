"""Adaptéry kandidátů: make(ctx) -> fn(expr) -> hodnota (chyba = výjimka).

Knihovny dostávají obyčejné pythonové funkce (ne typově přísné verze
z custom_eval), aby bylo vidět jejich vlastní chování.
"""
import ast

PYFUNCS = {"len": len, "min": min, "max": max, "round": round, "str": str, "int": int,
           "float": float, "join": lambda xs, sep="": sep.join(xs)}


class AttrDict(dict):
    """Tečkový přístup přes __getattr__ — getattr ale najde metody dictu dřív (steps.copy!)."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k) from None


def wrap(v):
    if isinstance(v, dict):
        return AttrDict({k: wrap(x) for k, x in v.items()})
    if isinstance(v, list):
        return [wrap(x) for x in v]
    return v


def custom(ctx):
    from custom_eval import evaluate
    return lambda expr: evaluate(expr, ctx)


def simpleeval_default(ctx):
    from simpleeval import SimpleEval
    s = SimpleEval(names=ctx, functions=dict(PYFUNCS))
    return s.eval


def simpleeval_hardened(ctx):
    """Tečka = jen klíč dictu; jiné atributy (a tím metody) zakázané."""
    from simpleeval import SimpleEval, FeatureNotAvailable

    class DictOnly(SimpleEval):
        def _eval_attribute(self, node):
            obj = self._eval(node.value)
            if isinstance(obj, dict):
                if node.attr in obj:
                    return obj[node.attr]
                raise KeyError(f"'{ast.unparse(node.value)}' nemá klíč '{node.attr}'")
            raise FeatureNotAvailable(f"atributy/metody nejsou povolené (.{node.attr})")

    s = DictOnly(names=ctx, functions=dict(PYFUNCS))
    for n in (ast.Assign, ast.AugAssign, ast.Import, ast.JoinedStr, ast.FormattedValue):
        s.nodes.pop(n, None)
    return s.eval


def asteval_minimal(ctx):
    from asteval import Interpreter
    ae = Interpreter(minimal=True, user_symbols={**wrap(ctx), **PYFUNCS})
    return lambda expr: ae.eval(expr, show_errors=False, raise_errors=True)


def evalidate_(ctx):
    from evalidate import Expr, EvalModel, base_eval_model

    def keys(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield k
                yield from keys(x)
        elif isinstance(v, list):
            for x in v:
                yield from keys(x)

    model = EvalModel(
        nodes=base_eval_model.nodes + ["Mult", "FloorDiv", "List", "Call", "Attribute"],
        allowed_functions=list(PYFUNCS), imported_functions=dict(PYFUNCS),
        # evalidate povoluje atributy jen podle jména → musíme vyjmenovat všechny klíče kontextu
        attributes=sorted(set(keys(ctx))),
    )
    w = wrap(ctx)
    return lambda expr: Expr(expr, model=model).eval(ctx_locals=w)


def restrictedpython(ctx):
    from RestrictedPython import compile_restricted_eval, safe_builtins
    from RestrictedPython.Guards import safer_getattr_raise
    w = wrap(ctx)

    def f(expr):
        res = compile_restricted_eval(expr)
        if res.errors:
            raise SyntaxError("; ".join(res.errors))
        g = {"__builtins__": {**safe_builtins, **PYFUNCS}, "_getattr_": safer_getattr_raise,
             "_getitem_": lambda o, k: o[k], "_getiter_": iter, **w}
        return eval(res.code, g)
    return f


def celpy_(ctx):
    import celpy
    from celpy import celtypes
    fns = {
        "min": lambda *a: min(a[0] if len(a) == 1 else a),
        "max": lambda *a: max(a[0] if len(a) == 1 else a),
        "round": lambda x: celtypes.IntType(round(x)),
        "join": lambda xs, sep: celtypes.StringType(sep.join(xs)),
    }
    env = celpy.Environment()
    act = {k: celpy.json_to_cel(v) for k, v in ctx.items()}

    def f(expr):
        r = env.program(env.compile(expr), functions=fns).evaluate(act)
        if isinstance(r, celpy.CELEvalError):
            raise r
        return r
    return f


def cel_rust(ctx):
    import cel
    fns = {
        "min": lambda *a: min(a[0] if len(a) == 1 else a),
        "max": lambda *a: max(a[0] if len(a) == 1 else a),
        "round": lambda x: round(x),
        "join": lambda xs, sep: sep.join(xs),
    }
    c = cel.Context(variables=ctx, functions=fns)
    return lambda expr: cel.evaluate(expr, c)


CANDIDATES = {
    "custom": custom,
    "simpleeval": simpleeval_default,
    "simpleeval+dictonly": simpleeval_hardened,
    "asteval": asteval_minimal,
    "evalidate": evalidate_,
    "RestrictedPython": restrictedpython,
    "cel-python": celpy_,
    "cel-rust": cel_rust,
}
CEL = {"cel-python", "cel-rust"}
