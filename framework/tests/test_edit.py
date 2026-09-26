"""Editační operace (edit.py, api.md „Editace“): round-trip YAML, adresa kroku, otisk, validace před zápisem."""
import difflib
import re
from pathlib import Path

import pytest
from conftest import WORKFLOWS

from agencast import ConfigErrors, api
from agencast.edit import FRONTMATTER, _new, merge, yaml_edit
from agencast.loader import load_yaml

SCENARIOS = sorted(p.name for p in (WORKFLOWS / "scenarios").glob("*.yaml"))
AGENTS = sorted(p.name for p in (WORKFLOWS / "agents").glob("*.md"))


def changed_lines(a: str, b: str) -> list[str]:
    """Řádky originálu, které změna přepsala nebo smazala (vložené řádky se nepočítají)."""
    sm = difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False)
    return [ln for op, i1, i2, _, _ in sm.get_opcodes() if op in ("replace", "delete") for ln in a.splitlines()[i1:i2]]


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_roundtrip(name):
    text = (WORKFLOWS / "scenarios" / name).read_text(encoding="utf-8")
    assert yaml_edit(text, lambda d: None, name) == text  # no-op = bajtově stejný soubor

    new_step = {"id": "rt_novy", "fail": "Víc řádků\n{{ inputs.x }}"}

    def change(d):
        merge(d, {"description": "Nový popis: {{ neni šablona }}"})
        d["steps"].insert(1, _new(new_step))
    new = yaml_edit(text, change, name)
    want = load_yaml(text, name)
    want["description"] = "Nový popis: {{ neni šablona }}"
    want["steps"].insert(1, new_step)
    assert load_yaml(new, name) == want  # loader (PyYAML 1.2 core) čte očekávaný obsah
    assert 'description: "Nový popis: {{ neni šablona }}"' in new
    # přepsaný je jen popis (u víceřádkového jeho řádky); komentáře, uvozovky a zbytek zůstaly doslova
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("description:"))
    j = next(n for n in range(i + 1, len(lines)) if not lines[n].startswith(" "))
    assert set(changed_lines(text, new)) <= set(lines[i:j])


@pytest.mark.parametrize("name", AGENTS)
def test_agent_roundtrip(name):
    src = (WORKFLOWS / "agents" / name).read_text(encoding="utf-8")
    m = FRONTMATTER.match(src)
    assert m
    assert m[1] + yaml_edit(m[2], lambda d: merge(d, {}), name) + m[3] + m[4] == src  # no-op
    fm = yaml_edit(m[2], lambda d: merge(d, {"description": "Jiný popis", "limits": {"budget_usd": 0.5}}), name)
    new = m[1] + fm + m[3] + m[4]
    want = load_yaml(m[2], name)
    want["description"] = "Jiný popis"
    want.setdefault("limits", {})["budget_usd"] = 0.5
    m2 = FRONTMATTER.match(new)
    assert m2 and load_yaml(m2[2], name) == want and m2[4] == m[4]  # tělo beze změny
    assert [ln for ln in m[2].splitlines() if ln.lstrip().startswith("#")] == \
           [ln for ln in fm.splitlines() if ln.lstrip().startswith("#")]  # komentáře zůstaly


def test_noop_operation_on_golden_project(wf):
    root = wf.parent
    p = wf / "scenarios" / "ig-post.yaml"
    before = p.read_bytes()
    d = api.describe_scenario(root, "ig-post")
    assert d and d["steps"][0]["address"] == ["steps", 0]
    r = api.set_header(root, "ig-post", d["etag"], {})
    assert p.read_bytes() == before and r["etag"] == d["etag"]


VETVE = """\
version: 1
name: vetve
description: Větve na libovolnou hloubku
inputs:
  tema: { type: string, default: káva }   # zarovnání a mezery zůstanou
outputs:
  text: { type: string }
steps:
  # rozhodnutí podle tématu
  - id: rozhodni
    switch:
      value: inputs.tema
      cases:
        káva:
          - id: par
            parallel:
              a:
                - id: a1
                  ask: { agent: pisatel, prompt: "A {{ inputs.tema }}" }
              b:
                - id: b1
                  ask: { agent: pisatel, prompt: "B {{ inputs.tema }}" }
                - id: b2
                  ask: { agent: pisatel, prompt: "B2 {{ inputs.tema }}" }
              c:
                - id: c1
                  ask: { agent: pisatel, prompt: "C {{ inputs.tema }}" }
      default:
        - id: d1
          ask: { agent: pisatel, prompt: "D {{ inputs.tema }}" }

  - id: vystup
    output:
      text: "{{ inputs.tema }}"
"""


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    r = api.write_file(root, "scenarios/vetve.yaml", None, VETVE)
    assert r["errors"] == []
    return root


def ids(tree):
    out = []
    for s in tree:
        out.append((s["id"], s["address"]))
        for sub in [*s.get("branches", {}).values(), *s.get("cases", {}).values(), s.get("default") or []]:
            out += ids(sub)
    return out


def test_address_in_get_and_nested_ops(proj):
    d = api.describe_scenario(proj, "vetve")
    assert d
    assert ids(d["steps"]) == [
        ("rozhodni", ["steps", 0]), ("par", ["steps", 0, "switch", "cases", "káva", 0]),
        ("a1", ["steps", 0, "switch", "cases", "káva", 0, "parallel", "a", 0]),
        ("b1", ["steps", 0, "switch", "cases", "káva", 0, "parallel", "b", 0]),
        ("b2", ["steps", 0, "switch", "cases", "káva", 0, "parallel", "b", 1]),
        ("c1", ["steps", 0, "switch", "cases", "káva", 0, "parallel", "c", 0]),
        ("d1", ["steps", 0, "switch", "default", 0]), ("vystup", ["steps", 1])]
    a = ["steps", 0, "switch", "cases", "káva", 0, "parallel", "a"]
    # add na začátek větve (adresa seznamu) a za krok (adresa kroku); adresy z URL jsou texty
    r = api.add_step(proj, "vetve", d["etag"], a, {"id": "a0", "ask": {"agent": "pisatel", "prompt": "Nula {{ inputs.tema }}"}})
    r = api.add_step(proj, "vetve", r["etag"], [*a[:-1], "a", "1"],
                     {"id": "a2", "ask": {"agent": "pisatel", "prompt": "Dva\n{{ steps.a1.text }}"}})
    text = (proj / "workflows" / "scenarios" / "vetve.yaml").read_text()
    assert 'prompt: "Nula {{ inputs.tema }}"' in text and "prompt: |-\n" in text
    assert "  tema: { type: string, default: káva }   # zarovnání a mezery zůstanou\n" in text
    assert "  # rozhodnutí podle tématu\n" in text
    tree = api.describe_scenario(proj, "vetve")
    assert tree and [i for i, _ in ids(tree["steps"])] == ["rozhodni", "par", "a0", "a1", "a2", "b1", "b2", "c1", "d1", "vystup"]
    # update: merge patch, null maže pole
    r = api.update_step(proj, "vetve", r["etag"], ["steps", 0, "switch", "default", 0],
                        {"ask": {"prompt": "Jiný {{ inputs.tema }}"}, "timeout": "1m"})
    r = api.update_step(proj, "vetve", r["etag"], ["steps", 0, "switch", "default", 0], {"timeout": None})
    data = load_yaml((proj / "workflows" / "scenarios" / "vetve.yaml").read_text(), "")
    assert data["steps"][0]["switch"]["default"][0] == {"id": "d1", "ask": {"agent": "pisatel", "prompt": "Jiný {{ inputs.tema }}"}}
    # move: z hloubky větve b na začátek default; pak delete
    r = api.move_step(proj, "vetve", r["etag"], [*a[:-1], "b", 0], ["steps", 0, "switch", "default"])
    tree = api.describe_scenario(proj, "vetve")
    assert tree and [i for i, _ in ids(tree["steps"])] == ["rozhodni", "par", "a0", "a1", "a2", "b2", "c1", "b1", "d1", "vystup"]
    assert ("b1", ["steps", 0, "switch", "default", 0]) in ids(tree["steps"])
    r = api.delete_step(proj, "vetve", r["etag"], ["steps", 0, "switch", "default", 0])
    r = api.delete_step(proj, "vetve", r["etag"], [*a[:-1], "c", 0])  # poslední krok větve → větev zmizí
    tree = api.describe_scenario(proj, "vetve")
    assert tree and tree["etag"] == r["etag"]
    assert [i for i, _ in ids(tree["steps"])] == ["rozhodni", "par", "a0", "a1", "a2", "b2", "d1", "vystup"]
    assert list(tree["steps"][0]["cases"]["káva"][0]["branches"]) == ["a", "b"]
    with pytest.raises(api.NotFound):
        api.delete_step(proj, "vetve", r["etag"], ["steps", 0, "parallel", "x", 0])
    with pytest.raises(ConfigErrors, match="vlastní větve"):
        api.move_step(proj, "vetve", r["etag"], ["steps", 0], ["steps", 0, "switch", "default"])


def test_etag_conflict_and_validation_write_nothing(proj):
    p = proj / "workflows" / "scenarios" / "vetve.yaml"
    before = p.read_bytes()
    cur = api.describe_scenario(proj, "vetve")["etag"]  # type: ignore[index]
    with pytest.raises(api.Conflict) as e:
        api.set_header(proj, "vetve", "stary", {"description": "x"})
    assert e.value.etag == cur and p.read_bytes() == before
    # output musí zůstat poslední → chyba config, nic se nezapíše
    with pytest.raises(ConfigErrors) as e2:
        api.add_step(proj, "vetve", cur, ["steps", 1], {"id": "po", "fail": "konec"})
    assert any("output" in x for x in e2.value.errors) and p.read_bytes() == before
    with pytest.raises(ConfigErrors):  # odkaz na neexistující krok
        api.update_step(proj, "vetve", cur, ["steps", 1], {"output": {"text": "{{ steps.nic.text }}"}})
    with pytest.raises(ConfigErrors, match="steps"):
        api.set_header(proj, "vetve", cur, {"steps": []})
    assert p.read_bytes() == before


def test_existing_errors_do_not_block(proj):
    wf = proj / "workflows"
    (wf / "scenarios" / "rozbity.yaml").write_text("version: 1\nname: rozbity\ndescription: x\nsteps: []\n")
    r = api.set_header(proj, "ukazka", api.describe_scenario(proj, "ukazka")["etag"], {"description": "Nový"})  # type: ignore[index]
    assert any("rozbity" in e for e in r["errors"])  # zůstává hlášená, ale změnu neblokuje


def test_delete_refused_when_used(proj):
    wf = proj / "workflows"
    d = api.describe_project(proj)
    tag = {a["name"]: a["etag"] for a in d["agents"]}["pisatel"]
    with pytest.raises(ConfigErrors, match="pisatel.*ukazka"):
        api.delete_agent(proj, "pisatel", tag)
    assert (wf / "agents" / "pisatel.md").is_file()
    # skill: nový, použitý agentem → nejde smazat
    r = api.set_skill(proj, "hlas", None, "---\nname: hlas\ndescription: Tón textů\n---\nTykáme.\n")
    ra = api.set_agent(proj, "pisatel", tag, {"skills": ["hlas"]})
    with pytest.raises(ConfigErrors, match="hlas.*pisatel"):
        api.delete_skill(proj, "hlas", r["etag"])
    api.set_agent(proj, "pisatel", ra["etag"], {"skills": None})
    assert api.delete_skill(proj, "hlas", r["etag"])["etag"] is None and not (wf / "skills" / "hlas").exists()
    # scénář volaný přes call nejde smazat
    callee = api.read_file(proj, "scenarios/ukazka.yaml")
    api.set_header(proj, "ukazka", callee["etag"], {"callable": True})
    callee = api.read_file(proj, "scenarios/ukazka.yaml")
    vetve = api.read_file(proj, "scenarios/vetve.yaml")
    api.add_step(proj, "vetve", vetve["etag"], ["steps"], {"id": "volej", "call": {"scenario": "ukazka"}})
    with pytest.raises(ConfigErrors, match="ukazka.*vetve"):
        api.delete_scenario(proj, "ukazka", callee["etag"])
    assert api.delete_scenario(proj, "vetve", api.read_file(proj, "scenarios/vetve.yaml")["etag"])["etag"] is None


def test_set_agent_keeps_comments_and_creates(proj):
    wf = proj / "workflows"
    f = api.read_file(proj, "agents/pisatel.md")
    assert f["frontmatter"]["model"] == "chytry" and f["body"].startswith("Píšeš")
    api.set_agent(proj, "pisatel", f["etag"], {"description": "Jiný"}, "Nové tělo.\n")
    text = (wf / "agents" / "pisatel.md").read_text()
    assert "description: Jiný\n" in text and text.endswith("---\nNové tělo.\n")
    with pytest.raises(ConfigErrors, match="frontmatter i body"):
        api.set_agent(proj, "novy", None, {"description": "x"})
    r = api.set_agent(proj, "novy", None, {"description": "Nový agent", "model": "rychly", "limits": {"budget_usd": 0.01}},
                      "Instrukce.\n")
    assert r["etag"] and api.read_file(proj, "agents/novy.md")["frontmatter"]["name"] == "novy"
    api.new_agent(proj, "komentovany")
    k = api.read_file(proj, "agents/komentovany.md")
    api.set_agent(proj, "komentovany", k["etag"], {"model": "rychly"})
    assert "model: rychly    # alias z config.yaml" in (wf / "agents" / "komentovany.md").read_text()


def test_set_config_no_secrets(proj):
    c = api.read_file(proj, "config.yaml")
    r = api.set_config(proj, c["etag"], {"models": {"levny": {"id": "google/gemini-3.5-flash-lite"}},
                                         "limits": {"run_budget_usd": 2}})
    text = (proj / "workflows" / "config.yaml").read_text()
    assert "  levny:" in text and "run_budget_usd: 2\n" in text and "# Pojistky jednoho běhu." in text
    for bad in ({"version": 2}, {"openrouter": {"base_url": "http://127.0.0.1/x"}}):
        with pytest.raises(ConfigErrors, match="nejde"):
            api.set_config(proj, r["etag"], bad)
    with pytest.raises(ConfigErrors) as e:  # hodnota místo jména proměnné
        api.set_config(proj, r["etag"], {"openrouter": {"api_key_env": "sk-or-v1-tajny"}})
    assert "tajny" not in " ".join(e.value.errors)


@pytest.mark.parametrize("rel", ["../.env", ".env", "agents/../../.env", "agents/x.txt", "scenarios/a/b.yaml",
                                 "runs/x.yaml", "/etc/passwd", "skills/x/other.md", "commands.yaml"])
def test_files_only_inside_workflows(proj, rel):
    with pytest.raises(api.NotFound):
        api.read_file(proj, rel)
    with pytest.raises(api.NotFound):
        api.write_file(proj, rel, None, "x")


def test_write_file_raw(proj):
    f = api.read_file(proj, "scenarios/ukazka.yaml")
    assert f["data"]["name"] == "ukazka" and f["errors"] == []
    with pytest.raises(ConfigErrors):  # rozbitý YAML se nezapíše
        api.write_file(proj, "scenarios/ukazka.yaml", f["etag"], "version: 1\nname: [\n")
    new = f["text"].replace("description: ", "# komentář\ndescription: ")
    r = api.write_file(proj, "scenarios/ukazka.yaml", f["etag"], new)
    assert (proj / "workflows" / "scenarios" / "ukazka.yaml").read_text() == new and r["etag"] != f["etag"]
    assert not list((proj / "workflows").rglob("*.tmp"))
    assert re.fullmatch(r"[0-9a-f]{64}", r["etag"])


def test_describe_has_etags(proj):
    d = api.describe_project(proj)
    for x in d["scenarios"] + d["agents"]:
        kind = "scenarios" if x in d["scenarios"] else "agents"
        suffix = ".yaml" if kind == "scenarios" else ".md"
        assert x["etag"] == api.read_file(proj, f"{kind}/{x['name']}{suffix}")["etag"]
    assert Path(d["root"]) == proj.resolve()
