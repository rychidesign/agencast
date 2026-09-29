"""Expressions and templates (scenario.md §5). Based on 58 cases from spike (c)
(spike report expressions/cases.py (removed from the tree; in repository history through commit fe90e05)), adapted to the approved spec:
`item` does not exist in v1 (its cases read `inputs.item`), `//` and `is`
are not in the language, literals are true/false/null, `round` rounds halves away from zero.
"""
import pytest

from agencast.expressions import (MAX_LEN, ExprError, FileRef, evaluate, infer, parse, parse_path, path_step,
                             render, template_type)

CTX = {
    "inputs": {"language": "en", "topic": "summer", "limit": 3, "note": None,
               "item": {"name": "T-shirt", "price": 590, "tags": ["a", "b"]}},
    "steps": {
        "check": {"on_brand": 0.4, "reason": "too formal", "scores": [0.4, 0.9, 0.7]},
        "copy": {"caption": "Summer is here", "hashtags": ["#summer", "#lumen", "#drop"]},  # collides with dict.copy
    },
}

VALID = [  # (id, expression, result)
    ("V01", 'steps.check.on_brand < 0.7 and inputs.language == "en"', True),
    ("V02", "not (steps.check.on_brand >= 0.7)", True),
    ("V03", "steps.check.on_brand < 0.7 or inputs.limit > 10", True),
    ("V04", "inputs.limit * 2 + 1", 7),
    ("V05", "inputs.item.price / 4", 147.5),
    ("V06", "int(inputs.item.price / 100) % 3", 2),            # spike: `//` — not in the spec
    ("V07", "steps.copy.hashtags[0]", "#summer"),
    ("V08", "steps.copy.hashtags[-1]", "#drop"),
    ("V09", 'steps["check"]["on_brand"]', 0.4),
    ("V10", "len(steps.copy.hashtags)", 3),
    ("V11", "min(steps.check.scores)", 0.4),
    ("V12", "max(1, inputs.limit)", 3),
    ("V13", "round(steps.check.on_brand * 100)", 40),
    ("V14", 'str(inputs.item.price) + " USD"', "590 USD"),
    ("V15", 'int("42") + float("0.5")', 42.5),
    ("V16", 'join(steps.copy.hashtags, " ")', "#summer #lumen #drop"),
    ("V17", 'steps.copy.caption == "Summer is here"', True),
    ("V18", "inputs.note == null", True),                 # spike: `== None`
    ("V19", "inputs.note != null", False),                # spike: `is None` — not in the spec
    ("V20", '"#lumen" in steps.copy.hashtags', True),
    ("V21", 'inputs.language in ["en", "fr"]', True),
    ("V22", 'steps.copy.caption != "" and len(steps.copy.caption) <= 280', True),
    ("V23", "-inputs.item.price + 600", 10),
    ("V24", "round(2.5)", 3),                                 # spike: banker's rounding gives 2; spec: away from zero
]

ERRORS = [  # (id, expression, required message substring)
    ("E01", "steps.nonexistent.x", "'steps' has no key 'nonexistent' (available: check, copy)"),
    ("E02", "steps.check.missing > 1", "has no key 'missing'"),
    ("E03", "steps.copy.hashtags[10]", "index 10 out of range"),
    ("E04", 'steps.check.on_brand < "0.7"', "comparing number with string"),
    ("E05", 'inputs.limit == "3"', "comparing number with string"),
    ("E06", "true + 1", "cannot add boolean + number"),
    ("E07", "inputs.item.price / 0", "division by zero"),
    ("E08", "steps.check.on_brand <", "unexpected end of expression"),
    ("E09", 'inputs.language = "en"', "syntax error"),
    ("E10", 'int("abc")', '"abc"'),
    ("E11", "len(inputs.item.price)", "does not accept number"),
    ("E12", "unknown_variable", "unknown name 'unknown_variable'"),
    ("E13", "inputs.note + 1", "cannot add null + number"),
    ("E14", 'steps.copy.hashtags and inputs.language == "en"', "'and' requires true/false, got list"),
]

HARMFUL = [  # (id, expression) — always an error, never a result
    ("H01", "__import__('os').getcwd()"), ("H02", "().__class__.__bases__[0].__subclasses__()"),
    ("H03", "open('/etc/passwd').read()"), ("H04", "getattr(inputs, 'language')"), ("H05", "(lambda: 1)()"),
    ("H06", "[x for x in steps.copy.hashtags]"), ("H07", "inputs.item.__class__.__init__.__globals__"),
    ("H08", '"{0.__class__}".format(1)'), ("H09", "steps.copy.caption.upper()"), ("H10", "inputs.keys()"),
    ("H11", "inputs.__class__"), ("H12", "type(inputs)"), ("H13", 'print("x")'), ("H14", "(x := 1)"),
    ("H15", "rand()"), ("H16", '"a" * 10**9'), ("H17", "10**10**10"), ("H18", "1+" * 50000 + "1"),
    ("H19", "-" * 100000 + "1"), ("H20", "(" * 1000 + "1" + ")" * 1000),
]


@pytest.mark.parametrize("cid,expr,want", VALID, ids=[c[0] for c in VALID])
def test_valid(cid, expr, want):
    got = evaluate(expr, CTX)
    assert got == want and type(got) is type(want), (got, want)


@pytest.mark.parametrize("cid,expr,msg", ERRORS, ids=[c[0] for c in ERRORS])
def test_errors(cid, expr, msg):
    with pytest.raises(ExprError) as e:
        evaluate(expr, CTX)
    assert msg in str(e.value)


@pytest.mark.parametrize("cid,expr", HARMFUL, ids=[c[0] for c in HARMFUL])
def test_harmful(cid, expr):
    with pytest.raises(ExprError):
        evaluate(expr, CTX)


# --- spec rules beyond the spike ------------------------------------------------

@pytest.mark.parametrize("expr,want", [
    ("7 / 2", 3.5), ("4 / 2", 2.0), ("7 % 3", 1), ("round(-2.5)", -3), ("round(0.125, 2)", 0.13),
    ("round(2.4)", 2), ("int(2.7)", 2), ('int("3")', 3), ('float("0.7")', 0.7), ("str(null)", "null"),
    ("str(true)", "true"), ("str(0.62)", "0.62"), ("str(0.1 + 0.2)", "0.30000000000000004"), ("str(4 / 2)", "2.0"),
    ('"a" + "b"', "ab"), ("[1] + [2]", [1, 2]), ('"summer" in inputs.topic', True), ('"language" in inputs', True),
    ("steps.copy.hashtags[-3]", "#summer"), ("min(3, 1, 2)", 1), ("max([1, 5])", 5), ("true and false or true", True),
    ("steps.copy.hashtags == null", False), ("1 < 2 < 3", True), ('steps.copy.hashtags[1.0]', "#lumen"),
])
def test_spec_rules(expr, want):
    got = evaluate(expr, CTX)
    assert got == want and type(got) is type(want)


@pytest.mark.parametrize("expr,msg", [
    ("True", "unknown name 'True'"), ("None", "unknown name 'None'"), ("item.x", "reserved for future foreach"),
    ("steps.copy.hashtags[1:3]", "slices"), ("2 ** 3", "exponentiation"), ("x if y else z", "conditional"),
    ("inputs.note is None", "'is' is not allowed"), ("10 // 3", "//"), ('{"a": 1}', "object literal"),
    ('f"{inputs.language}"', "f-strings"), ("(1, 2)", "tuples"), ("~1", "operator"),
    ('3 in ["3"]', "'in': item [0] is string"), ('"a" * 3', "'*' requires numbers, got string"),
    ('"on_brand = " + 0.9', "str(x)"), ("not 1", "'not' requires true/false"), ('int("2.7")', "is not an integer"),
    ('float("nan")', "is not a number"), ("1e308 * 10", "is not a finite number"), ("join(steps.copy.hashtags)", "join() requires 2"),
    ('join([1, 2], ",")', "item [0] is number"), ("len(1, 2)", "len() requires 1"), ("min([])", "empty"),
    ("steps.copy.caption.x", "is string, not object"), ('steps.copy["x"]', "has no key 'x'"),
    ("steps.copy.hashtags[0.5]", "an integer"), ('steps.copy.caption[0]', "only list or object can be indexed"),
    ("inputs.__dict__", "dunder"), ("1e999", "out of range"), ("-(true)", "unary sign requires number"),
    ("round(1.5, 0.5)", "an integer"), ('"a" < 1', "comparing string with number"), ("[1] < [2]", "only supports numbers or strings"),
    ('str(inputs.item.tags) + "x" * 1', "'*' requires numbers"),
])
def test_spec_errors(expr, msg):
    with pytest.raises(ExprError) as e:
        evaluate(expr, CTX)
    assert msg in str(e.value), str(e.value)


def test_limits_before_parser():
    with pytest.raises(ExprError, match="maximum 2000"):
        parse("1+" * 1000 + "1")                     # 2001 characters: length checked before parsing
    parse('"' + "x" * (MAX_LEN - 2) + '"')           # exactly 2000 characters passes
    with pytest.raises(ExprError, match="nesting deeper than 100"):
        parse("-" * 150 + "1")


def test_result_size_limit():
    ctx = {"inputs": {"s": "x" * 60000}, "steps": {}}
    with pytest.raises(ExprError, match="maximum 100000"):
        evaluate("inputs.s + inputs.s", ctx)


def test_caret_points_to_error():
    with pytest.raises(ExprError) as e:
        evaluate("steps.chec.on_brand", CTX)
    lines = str(e.value).splitlines()
    assert lines[1] == "  steps.chec.on_brand" and lines[2] == "        ^"
    with pytest.raises(ExprError) as e:
        evaluate('steps.check.on_brand < "0.7"', CTX)
    assert str(e.value).splitlines()[2].index("^") == 2 + len("steps.check.on_brand < ")


def test_caret_counts_characters_not_bytes():
    ctx = {"inputs": {"café": "x"}, "steps": {}}
    with pytest.raises(ExprError) as e:
        evaluate('inputs.café == 1', ctx)
    assert str(e.value).splitlines()[2].index("^") == 2 + len("inputs.café == ")


def test_dot_reads_keys_not_attributes():
    ctx = {"inputs": {}, "steps": {"items": {"keys": 1, "copy": 2, "get": 3}}}
    assert evaluate("steps.items.keys + steps.items.copy + steps.items.get", ctx) == 6


# --- templates ------------------------------------------------------------------------

def test_template_whole_value_keeps_type():
    assert render("{{ steps.copy.hashtags }}", CTX) == ["#summer", "#lumen", "#drop"]
    assert render("{{ steps.check.on_brand }}", CTX) == 0.4
    ref = FileRef("steps/07-photo/image.png")
    assert render("{{ steps.photo.file }}", {"inputs": {}, "steps": {"photo": {"file": ref}}}) is ref


def test_template_in_text():
    got = render("T: {{ inputs.topic }} {{ inputs.limit }} {{ steps.check.on_brand }} {{ steps.copy.hashtags }}", CTX)
    assert got == 'T: summer 3 0.4 ["#summer","#lumen","#drop"]' or got == 'T: summer 3 0.4 ["#summer", "#lumen", "#drop"]'


def test_template_null_is_error_except_default():
    with pytest.raises(ExprError, match="null"):
        render("x {{ inputs.note }}", CTX)
    ctx = {"inputs": {}, "steps": {"photo": {"file": None}}}
    assert render("{{ steps.photo.file }}", ctx, null_ok=lambda t: path_step(t) == "photo") is None
    assert render("a {{ steps.photo.file }}", ctx, null_ok=lambda t: path_step(t) == "photo") == "a null"


def test_template_only_paths():
    for bad in ("{{ inputs.limit + 1 }}", "{{ len(inputs.topic) }}", "{{ 1 }}", "{{ steps.copy.hashtags[inputs.limit] }}"):
        with pytest.raises(ExprError, match="only contain a path"):
            render(bad, CTX)
    parse_path("steps.copy.hashtags[-1]")
    parse_path('steps.check["on_brand"]')


def test_template_never_reevaluated():
    ctx = {"inputs": {"x": "{{ inputs.y }}", "y": "secret"}, "steps": {}}
    assert render("A {{ inputs.x }}", ctx) == "A {{ inputs.y }}"


def test_template_unclosed():
    with pytest.raises(ExprError, match="unclosed"):
        render("Hello {{ inputs.topic", CTX)


# --- static checking (types known in advance) ---------------------------------------------

def _res(types):
    def resolve(key):
        if key not in types:
            raise ExprError(f"step '{key}' does not exist")
        return types[key]
    return resolve


STEP_TYPES = {"check": {"on_brand": "number", "details": {"on_brand": "object"}},
              "copy": {"caption": "string", "hashtags": ["string"]}}
INPUTS = {"language": "string", "limit": "number"}


@pytest.mark.parametrize("expr,want", [
    ("steps.check.on_brand < 0.7", "boolean"), ("len(steps.copy.hashtags)", "number"),
    ('join(steps.copy.hashtags, " ")', "string"), ("steps.copy.hashtags[0]", "string"),
    ("steps.check.details.on_brand.confidence", None), ('steps.check.details["on_brand"]', "object"),
])
def test_infer_ok(expr, want):
    assert infer(expr, INPUTS, _res(STEP_TYPES)) == want


@pytest.mark.parametrize("expr,msg", [
    ('steps.check.on_brand < "0.7"', "comparing number with string"), ('inputs.limit == "3"', "comparing number with string"),
    ("steps.copy.hashtags and true", "'and' requires true/false, got list"), ("steps.copy.missing", "has no key 'missing'"),
    ("steps.missing.x", "step 'missing' does not exist"), ('join([1], ",")', "join() requires a list of string"),
    ("inputs.limit + inputs.language", "cannot add number + string"), ('3 in steps.copy.hashtags', "list items are string"),
    ("steps.copy.caption.x", "is string, not object"), ("len(inputs.limit)", "does not accept number"),
])
def test_infer_errors(expr, msg):
    with pytest.raises(ExprError) as e:
        infer(expr, INPUTS, _res(STEP_TYPES))
    assert msg in str(e.value)


def test_template_type():
    assert template_type("{{ steps.copy.hashtags }}", INPUTS, _res(STEP_TYPES)) == ["string"]
    assert template_type("x {{ steps.copy.hashtags }}", INPUTS, _res(STEP_TYPES)) == "string"
    with pytest.raises(ExprError, match="always null"):
        template_type("{{ steps.s.x }}", INPUTS, _res({"s": {"x": "null"}}))
