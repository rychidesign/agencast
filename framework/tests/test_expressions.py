"""Výrazy a šablony (scenario.md §5). Základ = 58 případů ze spiku (c)
(`spikes/expressions/cases.py`), upravených podle schválené spec:
`item` ve v1 neexistuje (případy s ním čtou `inputs.item`), `//` a `is`
v jazyce nejsou, literály jsou true/false/null, `round` půlku od nuly.
"""
import pytest

from agencast.expressions import (MAX_LEN, ExprError, FileRef, evaluate, infer, parse, parse_path, path_step,
                             render, template_type)

CTX = {
    "inputs": {"jazyk": "cs", "tema": "léto", "limit": 3, "poznamka": None,
               "item": {"nazev": "tričko", "cena": 590, "tagy": ["a", "b"]}},
    "steps": {
        "kontrola": {"on_brand": 0.4, "duvod": "moc formální", "skore": [0.4, 0.9, 0.7]},
        "copy": {"caption": "Léto je tady", "hashtags": ["#leto", "#thtd", "#drop"]},  # koliduje s dict.copy
    },
}

VALID = [  # (id, výraz, výsledek)
    ("V01", 'steps.kontrola.on_brand < 0.7 and inputs.jazyk == "cs"', True),
    ("V02", "not (steps.kontrola.on_brand >= 0.7)", True),
    ("V03", "steps.kontrola.on_brand < 0.7 or inputs.limit > 10", True),
    ("V04", "inputs.limit * 2 + 1", 7),
    ("V05", "inputs.item.cena / 4", 147.5),
    ("V06", "int(inputs.item.cena / 100) % 3", 2),            # spike: `//` — ve spec není
    ("V07", "steps.copy.hashtags[0]", "#leto"),
    ("V08", "steps.copy.hashtags[-1]", "#drop"),
    ("V09", 'steps["kontrola"]["on_brand"]', 0.4),
    ("V10", "len(steps.copy.hashtags)", 3),
    ("V11", "min(steps.kontrola.skore)", 0.4),
    ("V12", "max(1, inputs.limit)", 3),
    ("V13", "round(steps.kontrola.on_brand * 100)", 40),
    ("V14", 'str(inputs.item.cena) + " Kč"', "590 Kč"),
    ("V15", 'int("42") + float("0.5")', 42.5),
    ("V16", 'join(steps.copy.hashtags, " ")', "#leto #thtd #drop"),
    ("V17", 'steps.copy.caption == "Léto je tady"', True),
    ("V18", "inputs.poznamka == null", True),                 # spike: `== None`
    ("V19", "inputs.poznamka != null", False),                # spike: `is None` — ve spec není
    ("V20", '"#thtd" in steps.copy.hashtags', True),
    ("V21", 'inputs.jazyk in ["cs", "sk"]', True),
    ("V22", 'steps.copy.caption != "" and len(steps.copy.caption) <= 280', True),
    ("V23", "-inputs.item.cena + 600", 10),
    ("V24", "round(2.5)", 3),                                 # spike: bankéřské 2; spec: od nuly
]

ERRORS = [  # (id, výraz, co musí být v hlášce)
    ("E01", "steps.neexistuje.x", "'steps' nemá klíč 'neexistuje' (dostupné: kontrola, copy)"),
    ("E02", "steps.kontrola.chybi > 1", "nemá klíč 'chybi'"),
    ("E03", "steps.copy.hashtags[10]", "index 10 mimo rozsah"),
    ("E04", 'steps.kontrola.on_brand < "0.7"', "porovnání number s string"),
    ("E05", 'inputs.limit == "3"', "porovnání number s string"),
    ("E06", "true + 1", "nelze boolean + number"),
    ("E07", "inputs.item.cena / 0", "dělení nulou"),
    ("E08", "steps.kontrola.on_brand <", "neočekávaný konec výrazu"),
    ("E09", 'inputs.jazyk = "cs"', "chyba syntaxe"),
    ("E10", 'int("abc")', '"abc"'),
    ("E11", "len(inputs.item.cena)", "nepřijímá number"),
    ("E12", "neznama_promenna", "neznámé jméno 'neznama_promenna'"),
    ("E13", "inputs.poznamka + 1", "nelze null + number"),
    ("E14", 'steps.copy.hashtags and inputs.jazyk == "cs"', "'and' chce true/false, dostal list"),
]

HARMFUL = [  # (id, výraz) — vždy chyba, nikdy výsledek
    ("H01", "__import__('os').getcwd()"), ("H02", "().__class__.__bases__[0].__subclasses__()"),
    ("H03", "open('/etc/passwd').read()"), ("H04", "getattr(inputs, 'jazyk')"), ("H05", "(lambda: 1)()"),
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


# --- pravidla spec nad rámec spiku ------------------------------------------------

@pytest.mark.parametrize("expr,want", [
    ("7 / 2", 3.5), ("4 / 2", 2.0), ("7 % 3", 1), ("round(-2.5)", -3), ("round(0.125, 2)", 0.13),
    ("round(2.4)", 2), ("int(2.7)", 2), ('int("3")', 3), ('float("0.7")', 0.7), ("str(null)", "null"),
    ("str(true)", "true"), ("str(0.62)", "0.62"), ("str(0.1 + 0.2)", "0.30000000000000004"), ("str(4 / 2)", "2.0"),
    ('"a" + "b"', "ab"), ("[1] + [2]", [1, 2]), ('"léto" in inputs.tema', True), ('"jazyk" in inputs', True),
    ("steps.copy.hashtags[-3]", "#leto"), ("min(3, 1, 2)", 1), ("max([1, 5])", 5), ("true and false or true", True),
    ("steps.copy.hashtags == null", False), ("1 < 2 < 3", True), ('steps.copy.hashtags[1.0]', "#thtd"),
])
def test_spec_rules(expr, want):
    got = evaluate(expr, CTX)
    assert got == want and type(got) is type(want)


@pytest.mark.parametrize("expr,msg", [
    ("True", "neznámé jméno 'True'"), ("None", "neznámé jméno 'None'"), ("item.x", "vyhrazené pro budoucí foreach"),
    ("steps.copy.hashtags[1:3]", "řezy"), ("2 ** 3", "mocnina"), ("x if y else z", "podmínka"),
    ("inputs.poznamka is None", "'is' není povolené"), ("10 // 3", "//"), ('{"a": 1}', "objektový literál"),
    ('f"{inputs.jazyk}"', "f-řetězce"), ("(1, 2)", "n-tice"), ("~1", "operátor"),
    ('3 in ["3"]', "'in': prvek [0] je string"), ('"a" * 3', "'*' chce čísla, dostal string"),
    ('"on_brand = " + 0.9', "str(x)"), ("not 1", "'not' chce true/false"), ('int("2.7")', "není celé číslo"),
    ('float("nan")', "není číslo"), ("1e308 * 10", "není konečné číslo"), ("join(steps.copy.hashtags)", "join() chce 2"),
    ('join([1, 2], ",")', "prvek [0] je number"), ("len(1, 2)", "len() chce 1"), ("min([])", "prázdného"),
    ("steps.copy.caption.x", "je string, ne object"), ('steps.copy["x"]', "nemá klíč 'x'"),
    ("steps.copy.hashtags[0.5]", "celé číslo"), ('steps.copy.caption[0]', "indexovat jde jen list nebo object"),
    ("inputs.__dict__", "dunder"), ("1e999", "mimo rozsah"), ("-(true)", "znaménko chce number"),
    ("round(1.5, 0.5)", "celé číslo"), ('"a" < 1', "porovnání string s number"), ("[1] < [2]", "umí jen čísla nebo texty"),
    ('str(inputs.item.tagy) + "x" * 1', "'*' chce čísla"),
])
def test_spec_errors(expr, msg):
    with pytest.raises(ExprError) as e:
        evaluate(expr, CTX)
    assert msg in str(e.value), str(e.value)


def test_limits_before_parser():
    with pytest.raises(ExprError, match="nejvýš 2000"):
        parse("1+" * 1000 + "1")                     # 2001 znaků: délka se kontroluje před parserem
    parse('"' + "x" * (MAX_LEN - 2) + '"')           # přesně 2000 znaků projde
    with pytest.raises(ExprError, match="vnoření hlubší než 100"):
        parse("-" * 150 + "1")


def test_result_size_limit():
    ctx = {"inputs": {"s": "x" * 60000}, "steps": {}}
    with pytest.raises(ExprError, match="nejvýš 100000"):
        evaluate("inputs.s + inputs.s", ctx)


def test_caret_points_to_error():
    with pytest.raises(ExprError) as e:
        evaluate("steps.kontrol.on_brand", CTX)
    lines = str(e.value).splitlines()
    assert lines[1] == "  steps.kontrol.on_brand" and lines[2] == "        ^"
    with pytest.raises(ExprError) as e:
        evaluate('steps.kontrola.on_brand < "0.7"', CTX)
    assert str(e.value).splitlines()[2].index("^") == 2 + len("steps.kontrola.on_brand < ")


def test_caret_counts_characters_not_bytes():
    ctx = {"inputs": {"téma": "x"}, "steps": {}}
    with pytest.raises(ExprError) as e:
        evaluate('inputs.téma == 1', ctx)
    assert str(e.value).splitlines()[2].index("^") == 2 + len("inputs.téma == ")


def test_dot_reads_keys_not_attributes():
    ctx = {"inputs": {}, "steps": {"items": {"keys": 1, "copy": 2, "get": 3}}}
    assert evaluate("steps.items.keys + steps.items.copy + steps.items.get", ctx) == 6


# --- šablony ------------------------------------------------------------------------

def test_template_whole_value_keeps_type():
    assert render("{{ steps.copy.hashtags }}", CTX) == ["#leto", "#thtd", "#drop"]
    assert render("{{ steps.kontrola.on_brand }}", CTX) == 0.4
    ref = FileRef("steps/07-foto/image.png")
    assert render("{{ steps.foto.file }}", {"inputs": {}, "steps": {"foto": {"file": ref}}}) is ref


def test_template_in_text():
    got = render("T: {{ inputs.tema }} {{ inputs.limit }} {{ steps.kontrola.on_brand }} {{ steps.copy.hashtags }}", CTX)
    assert got == 'T: léto 3 0.4 ["#leto","#thtd","#drop"]' or got == 'T: léto 3 0.4 ["#leto", "#thtd", "#drop"]'


def test_template_null_is_error_except_default():
    with pytest.raises(ExprError, match="null"):
        render("x {{ inputs.poznamka }}", CTX)
    ctx = {"inputs": {}, "steps": {"foto": {"file": None}}}
    assert render("{{ steps.foto.file }}", ctx, null_ok=lambda t: path_step(t) == "foto") is None
    assert render("a {{ steps.foto.file }}", ctx, null_ok=lambda t: path_step(t) == "foto") == "a null"


def test_template_only_paths():
    for bad in ("{{ inputs.limit + 1 }}", "{{ len(inputs.tema) }}", "{{ 1 }}", "{{ steps.copy.hashtags[inputs.limit] }}"):
        with pytest.raises(ExprError, match="jen cesta"):
            render(bad, CTX)
    parse_path("steps.copy.hashtags[-1]")
    parse_path('steps.kontrola["on_brand"]')


def test_template_never_reevaluated():
    ctx = {"inputs": {"x": "{{ inputs.y }}", "y": "tajné"}, "steps": {}}
    assert render("A {{ inputs.x }}", ctx) == "A {{ inputs.y }}"


def test_template_unclosed():
    with pytest.raises(ExprError, match="neuzavřená"):
        render("Ahoj {{ inputs.tema", CTX)


# --- statická kontrola (typy známé předem) ---------------------------------------------

def _res(types):
    def resolve(key):
        if key not in types:
            raise ExprError(f"krok '{key}' neexistuje")
        return types[key]
    return resolve


STEP_TYPES = {"kontrola": {"on_brand": "number", "details": {"on_brand": "object"}},
              "copy": {"caption": "string", "hashtags": ["string"]}}
INPUTS = {"jazyk": "string", "limit": "number"}


@pytest.mark.parametrize("expr,want", [
    ("steps.kontrola.on_brand < 0.7", "boolean"), ("len(steps.copy.hashtags)", "number"),
    ('join(steps.copy.hashtags, " ")', "string"), ("steps.copy.hashtags[0]", "string"),
    ("steps.kontrola.details.on_brand.confidence", None), ('steps.kontrola.details["on_brand"]', "object"),
])
def test_infer_ok(expr, want):
    assert infer(expr, INPUTS, _res(STEP_TYPES)) == want


@pytest.mark.parametrize("expr,msg", [
    ('steps.kontrola.on_brand < "0.7"', "porovnání number s string"), ('inputs.limit == "3"', "porovnání number s string"),
    ("steps.copy.hashtags and true", "'and' chce true/false, dostal list"), ("steps.copy.chybi", "nemá klíč 'chybi'"),
    ("steps.nic.x", "krok 'nic' neexistuje"), ('join([1], ",")', "join() chce seznam string"),
    ("inputs.limit + inputs.jazyk", "nelze number + string"), ('3 in steps.copy.hashtags', "prvky seznamu jsou string"),
    ("steps.copy.caption.x", "je string, ne object"), ("len(inputs.limit)", "nepřijímá number"),
])
def test_infer_errors(expr, msg):
    with pytest.raises(ExprError) as e:
        infer(expr, INPUTS, _res(STEP_TYPES))
    assert msg in str(e.value)


def test_template_type():
    assert template_type("{{ steps.copy.hashtags }}", INPUTS, _res(STEP_TYPES)) == ["string"]
    assert template_type("x {{ steps.copy.hashtags }}", INPUTS, _res(STEP_TYPES)) == "string"
    with pytest.raises(ExprError, match="vždy null"):
        template_type("{{ steps.s.x }}", INPUTS, _res({"s": {"x": "null"}}))
