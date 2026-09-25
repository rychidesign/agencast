# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Ověří ukázky a úryvky specifikace proti JSON Schema.

Soubory čte stejně, jak je bude číst framework (DESIGN §5.2, spec REVIEW B6):
YAML 1.2 core — booleany jen true/false, `4:5` a `yes` jsou text,
duplicitní klíč je chyba s číslem řádku.

Spuštění z kořene repozitáře:  uv run docs/spec/tools/check.py
Součást specifikace, ne frameworku.
"""
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/spec"


class Yaml12Loader(yaml.SafeLoader):
    """SafeLoader bez resolverů YAML 1.1 (yes/no/on/off, 4:5 → 245, datum)."""

    def construct_mapping(self, node, deep=False):
        seen = {}
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicitní klíč {key!r} (poprvé na řádku {seen[key]})",
                    key_node.start_mark)
            seen[key] = key_node.start_mark.line + 1
        return super().construct_mapping(node, deep)


Yaml12Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in rs if tag in ("tag:yaml.org,2002:null",)]
    for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for tag, rx, first in [
    ("tag:yaml.org,2002:bool", r"^(?:true|True|TRUE|false|False|FALSE)$", "tTfF"),
    ("tag:yaml.org,2002:int", r"^(?:[-+]?[0-9]+|0x[0-9a-fA-F]+)$", "-+0123456789"),
    ("tag:yaml.org,2002:float",
     r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$",
     "-+0123456789."),
]:
    Yaml12Loader.add_implicit_resolver(tag, re.compile(rx), list(first))


def _int12(loader, node):
    v = loader.construct_scalar(node)
    return int(v, 16) if v.startswith("0x") else int(v, 10)


Yaml12Loader.add_constructor("tag:yaml.org,2002:int", _int12)


def load(text):
    return yaml.load(text, Loader=Yaml12Loader)


def split_frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        raise ValueError("chybí frontmatter mezi řádky ---")
    return load(m.group(1)), m.group(2)


def self_test():
    assert load("a: 4:5") == {"a": "4:5"}
    assert load("on: x\nyes: y\nb: true") == {"on": "x", "yes": "y", "b": True}
    assert load("a: 010\nb: 0x1f\nc: 2026-09-25\nd: .5") == {"a": 10, "b": 31, "c": "2026-09-25", "d": 0.5}
    try:
        load("a: 1\nb: 2\na: 3")
    except yaml.YAMLError as e:
        assert "duplicitní klíč 'a'" in str(e) and "line 3" in str(e)
    else:
        raise AssertionError("duplicitní klíč prošel")


def main():
    self_test()
    schemas = {n: Draft202012Validator(json.loads((SPEC / f"schema/{n}.schema.json").read_text()))
               for n in ("agent", "scenario", "config", "mcp", "skill")}
    for v in schemas.values():
        v.check_schema(v.schema)
    items = []  # (popis, schéma, data)
    errors = []

    def add(label, kind, getter):
        try:
            items.append((label, kind, getter()))
        except (yaml.YAMLError, ValueError) as e:
            errors.append(f"{label}: {e}")

    def body_check(label, body):
        if not body.strip():
            errors.append(f"{label}: prázdné tělo")

    wf = ROOT / "workflows"
    for f in sorted((wf / "agents").glob("*.md")):
        def g(f=f):
            fm, body = split_frontmatter(f.read_text())
            body_check(f.name, body)
            if fm.get("name") != f.stem:
                errors.append(f"{f.name}: name ≠ jméno souboru")
            return fm
        add(str(f.relative_to(ROOT)), "agent", g)
    for f in sorted((wf / "skills").glob("*/SKILL.md")):
        def g(f=f):
            fm, body = split_frontmatter(f.read_text())
            body_check(str(f), body)
            if fm.get("name") != f.parent.name:
                errors.append(f"{f}: name ≠ jméno složky")
            return fm
        add(str(f.relative_to(ROOT)), "skill", g)
    for f in sorted((wf / "scenarios").glob("*.yaml")):
        def g(f=f):
            d = load(f.read_text())
            if d.get("name") != f.stem:
                errors.append(f"{f.name}: name ≠ jméno souboru")
            return d
        add(str(f.relative_to(ROOT)), "scenario", g)
    add("workflows/config.example.yaml", "config", lambda: load((wf / "config.example.yaml").read_text()))
    add("workflows/mcp.example.yaml", "mcp", lambda: load((wf / "mcp.example.yaml").read_text()))
    add("workflows/commands.example.yaml", None, lambda: load((wf / "commands.example.yaml").read_text()))

    # Úryvky ze specifikace.
    for md in sorted(SPEC.glob("*.md")):
        text = md.read_text()
        for i, block in enumerate(re.findall(r"```yaml\n(.*?)```", text, re.S), 1):
            label = f"{md.name} yaml#{i}"
            try:
                d = load(block)
            except yaml.YAMLError as e:
                errors.append(f"{label}: {e}")
                continue
            if md.name == "scenario.md":
                if isinstance(d, dict) and "version" in d:
                    items.append((label, "scenario", d))
                elif isinstance(d, list):
                    items.append((label, "scenario", {"version": 1, "name": "x", "description": "x", "steps": d}))
            elif isinstance(d, dict) and "openrouter" in d:
                items.append((label, "config", d))
            elif isinstance(d, dict) and "servers" in d:
                items.append((label, "mcp", d))
        for i, block in enumerate(re.findall(r"```markdown\n(.*?)```", text, re.S), 1):
            kind = {"agent.md": "agent", "skill.md": "skill"}.get(md.name)
            if kind:
                add(f"{md.name} markdown#{i}", kind, lambda b=block: split_frontmatter(b)[0])

    counts = {}
    for label, kind, data in items:
        if kind is None:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        for e in schemas[kind].iter_errors(data):
            path = "/".join(str(p) for p in e.absolute_path) or "(kořen)"
            errors.append(f"{label} [{kind}] {path}: {e.message}")

    for e in errors:
        print("CHYBA", e)
    print("ověřeno:", ", ".join(f"{k} {v}×" for k, v in sorted(counts.items())),
          "| chyb:", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
