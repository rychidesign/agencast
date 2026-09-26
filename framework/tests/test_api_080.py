"""API podle nálezů z GUI, část 2 (agencast 0.8.0, api.md „Dávka, náhled a doplňky“): dávka operací,
náhled bez zápisu, celý krok, stav čerstvého běhu, lehký otisk, chyby souboru, popis nových souborů,
použití aliasů modelů a povolená pole config.yaml."""
import json
import time

import httpx
import pytest
from test_api import registry_server  # noqa: F401 — fixture
from test_edit import VETVE, ids
from test_gui_api import held_lock
from test_webhook import TOKEN

from agencast import ConfigErrors, api, server
from agencast.fake import Fake
from agencast.loader import load_yaml

PREJMENUJ = """\
version: 1
name: prejmenuj
description: Přejmenování čteného kroku
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: napis
    ask: { agent: pisatel, prompt: "Téma {{ inputs.tema }}" }
  # komentář: steps.napis.text se čte níž
  - id: uprav
    when: steps.napis.text != ""
    ask: { agent: pisatel, prompt: "Uprav: {{ steps.napis.text }} (steps.napis.text mimo šablonu zůstane)" }
    default: { text: "" }
  - id: vystup
    output:
      text: "{{ steps.uprav.text }} {{steps.napis.text}}"
"""


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    for name, text in (("vetve", VETVE), ("prejmenuj", PREJMENUJ)):
        assert api.write_file(root, f"scenarios/{name}.yaml", None, text)["errors"] == []
    return root


def text_of(root, name):
    return (root / "workflows" / "scenarios" / f"{name}.yaml").read_text()


def tag_of(root, name):
    return api.read_file(root, f"scenarios/{name}.yaml")["etag"]


def test_rename_read_step_in_one_batch(proj):
    tag = tag_of(proj, "prejmenuj")
    with pytest.raises(ConfigErrors):  # po jedné operaci to nejde (nalezy-api 10)
        api.update_step(proj, "prejmenuj", tag, ["steps", 0], {"id": "navrh"})
    with pytest.raises(ConfigErrors) as e:  # bez rename_refs zůstanou čtenáři rozbití — chyba výsledku, ne operace
        api.batch(proj, "prejmenuj", tag, [{"op": "rename_step", "address": ["steps", 0], "new_id": "navrh",
                                            "rename_refs": False}])
    assert not isinstance(e.value, api.OpError)
    r = api.batch(proj, "prejmenuj", tag, [{"op": "rename_step", "address": ["steps", 0], "new_id": "navrh"}])
    assert r["errors"] == []
    text = text_of(proj, "prejmenuj")
    assert text == PREJMENUJ.replace("id: napis", "id: navrh").replace(
        'when: steps.napis.text != ""', 'when: steps.navrh.text != ""').replace(
        '{ agent: pisatel, prompt: "Uprav: {{ steps.napis.text }} (steps.napis.text mimo šablonu zůstane)" }',
        '{agent: pisatel, prompt: "Uprav: {{ steps.navrh.text }} (steps.napis.text mimo šablonu zůstane)"}').replace(
        "{{steps.napis.text}}", "{{steps.navrh.text}}")  # komentář a text mimo šablonu beze změny ({ a } → {a}: api.md)
    assert r["etag"] == tag_of(proj, "prejmenuj")


def test_batch_atomic_sequential_addresses_and_op_index(proj):
    tag = tag_of(proj, "prejmenuj")
    before = text_of(proj, "prejmenuj")
    # smazání čteného kroku + úprava čtenáře; adresa druhé operace platí pro stav po první
    r = api.batch(proj, "prejmenuj", tag, [
        {"op": "delete_step", "address": ["steps", 1]},
        {"op": "update_step", "address": ["steps", 1], "fields": {"output": {"text": "{{ steps.napis.text }}"}}}])
    assert [s["id"] for s in load_yaml(text_of(proj, "prejmenuj"), "")["steps"]] == ["napis", "vystup"]
    # chyba n-té operace → nic se nezapíše, OpError s indexem
    cur = text_of(proj, "prejmenuj")
    bad_ops = [
        ([{"op": "add_step", "step": {"id": "x", "fail": "x"}}, {"op": "delete_step", "address": ["steps", 9]}], 1,
         "index 9"),
        ([{"op": "zmen"}], 0, "neznám"),
        ([{"op": "move_step", "address": ["steps", 0]}], 0, "chybí pole to"),
        ([{"op": "delete_step", "address": ["steps", 0], "navic": 1}], 0, "neznámé pole navic"),
        (["ne-objekt"], 0, "neznám"), ([{"op": ["seznam"]}], 0, "neznám")]
    for ops, n, msg in bad_ops:
        with pytest.raises(api.OpError) as e:
            api.batch(proj, "prejmenuj", r["etag"], ops)
        assert e.value.op == n and msg in e.value.errors[0] and e.value.errors[0].startswith(f"ops[{n}]")
    with pytest.raises(ConfigErrors, match="ops: má být seznam"):
        api.batch(proj, "prejmenuj", r["etag"], {"op": "delete_step"})
    with pytest.raises(api.Conflict):
        api.batch(proj, "prejmenuj", tag, [])
    assert text_of(proj, "prejmenuj") == cur != before


def test_incomplete_step_and_new_branch_in_one_batch(proj):
    tag = tag_of(proj, "prejmenuj")
    novy = [{"op": "add_step", "after": ["steps", 0], "step": {"id": "novy", "ask": {}}}]
    with pytest.raises(ConfigErrors):  # prázdný ask sám neprojde (validace se nemění)
        api.batch(proj, "prejmenuj", tag, novy)
    r = api.batch(proj, "prejmenuj", tag, novy + [
        {"op": "update_step", "address": ["steps", 1], "fields": {"ask": {"agent": "pisatel", "prompt": "Nový"}}}])
    assert r["errors"] == [] and load_yaml(text_of(proj, "prejmenuj"), "")["steps"][1]["id"] == "novy"

    par = ["steps", 0, "switch", "cases", "káva", 0]
    tag = tag_of(proj, "vetve")
    with pytest.raises(ConfigErrors):  # prázdná větev sama neprojde
        api.batch(proj, "vetve", tag, [{"op": "add_branch", "address": par, "name": "d"}])
    r = api.batch(proj, "vetve", tag, [
        {"op": "add_branch", "address": par, "name": "d"},
        {"op": "add_step", "after": [*par, "parallel", "d"], "step": {"id": "d0", "fail": "D"}},
        {"op": "add_branch", "address": ["steps", 0], "name": "čaj", "steps": [{"id": "c0", "fail": "Čaj"}]}])
    tree = api.describe_scenario(proj, "vetve")
    assert tree and ("d0", [*par, "parallel", "d", 0]) in ids(tree["steps"])
    assert list(tree["steps"][0]["cases"]) == ["káva", "čaj"]
    for op, msg in (({"address": par, "name": "a"}, "nesmí být"), ({"address": ["steps", 1], "name": "x"}, "jen do")):
        with pytest.raises(api.OpError, match=msg):
            api.batch(proj, "vetve", r["etag"], [{"op": "add_branch", **op}])


def test_replace_step_with_null(proj):
    r = api.write_file(proj, "scenarios/obrazek.yaml", None, (
        "version: 1\nname: obrazek\ndescription: Obrázek\noutputs:\n  text: { type: string }\nsteps:\n"
        "  - id: foto\n    image: { model: gemini-image, prompt: Káva }\n"
        "  - id: vystup\n    output: { text: hotovo }\n"))
    step = {"id": "foto", "when": "false", "image": {"model": "gemini-image", "prompt": "Čaj"}, "default": {"file": None}}
    with pytest.raises(ConfigErrors):  # merge patch null neumí zapsat — smaže klíč a default je pak neúplný
        api.update_step(proj, "obrazek", r["etag"], ["steps", 0], {"default": {"file": None}, "when": "false"})
    r = api.replace_step(proj, "obrazek", r["etag"], ["steps", 0], step)
    assert r["errors"] == [] and load_yaml(text_of(proj, "obrazek"), "")["steps"][0] == step
    # 19: alias z image.model je „v užití“
    d = api.describe_project(proj)
    assert d["links"]["scenario_model"] == [["obrazek", "gemini-image"]]
    assert d["models_used"] == {"chytry": ["agents/pisatel.md"], "rychly": [], "gemini-image": ["scenarios/obrazek.yaml"]}


def test_render_without_write(proj):
    p = proj / "workflows" / "scenarios" / "prejmenuj.yaml"
    before = p.read_bytes()
    tag = tag_of(proj, "prejmenuj")
    out = api.render(proj, "prejmenuj", None, [
        {"op": "add_step", "after": ["steps", 0], "step": {"id": "novy", "ask": {"agent": "pisatel"}}},
        {"op": "set_header", "fields": {"description": "Nový popis"}}])
    assert p.read_bytes() == before
    assert "# komentář: steps.napis.text se čte níž\n" in out["text"] and "description: Nový popis\n" in out["text"]
    assert [(s["id"], s["address"]) for s in out["tree"]][:2] == [("napis", ["steps", 0]), ("novy", ["steps", 1])]
    assert any("novy" in e for e in out["errors"])  # chyba rozpracovaného stavu, ne 422
    assert api.render(proj, "prejmenuj", tag, [])["text"] == before.decode()
    with pytest.raises(api.Conflict):
        api.render(proj, "prejmenuj", "stary", [])
    with pytest.raises(api.OpError):
        api.render(proj, "prejmenuj", None, [{"op": "delete_step", "address": ["steps", 7]}])
    with pytest.raises(api.NotFound):
        api.render(proj, "neni", None, [])


def test_file_errors_new_files_and_config(proj):
    # 17: files/ vrací chyby validate souboru jako GET /projects/<p>
    text = PREJMENUJ.replace("{{steps.napis.text}}", "{{ steps.nic.text }}")
    # write_file novou chybu nepustí → ruční úprava mimo API
    (proj / "workflows" / "scenarios" / "prejmenuj.yaml").write_text(text)
    f = api.read_file(proj, "scenarios/prejmenuj.yaml")
    d = api.describe_project(proj)
    want = next(s["errors"] for s in d["scenarios"] if s["name"] == "prejmenuj")
    assert f["errors"] == want and any("nic" in e for e in want)
    assert api.read_file(proj, "agents/pisatel.md")["errors"] == []
    assert api.file_etag(proj, "scenarios/prejmenuj.yaml") == f["etag"]
    with pytest.raises(api.NotFound):
        api.file_etag(proj, "scenarios/neni.yaml")
    # 18: popis a model nového agenta a scénáře
    api.new_agent(proj, "novy", "Popis: s dvojtečkou a \"uvozovkami\"", "rychly")
    fm = api.read_file(proj, "agents/novy.md")["frontmatter"]
    assert fm["description"] == "Popis: s dvojtečkou a \"uvozovkami\"" and fm["model"] == "rychly"
    with pytest.raises(ConfigErrors, match="není alias"):
        api.new_agent(proj, "jiny", model="neni")
    api.new_scenario(proj, "novy", "Co scénář dělá")
    assert api.read_file(proj, "scenarios/novy.yaml")["data"]["description"] == "Co scénář dělá"
    with pytest.raises(ConfigErrors, match="description"):
        api.new_scenario(proj, "treti", 5)  # type: ignore[arg-type]
    # 20: runs_dir a openrouter.jev_model jdou, base_url ne
    c = api.read_file(proj, "config.yaml")
    r = api.set_config(proj, c["etag"], {"runs_dir": "./behy", "openrouter": {"jev_model": "jev-1.14"}})
    data = api.read_file(proj, "config.yaml")["data"]
    assert data["runs_dir"] == "./behy" and data["openrouter"]["jev_model"] == "jev-1.14"
    with pytest.raises(ConfigErrors, match="base_url"):
        api.set_config(proj, r["etag"], {"openrouter": {"base_url": "https://openrouter.ai/api/v2"}})


def test_fresh_run_state(proj, monkeypatch):
    """15: hned po 202 queued, převzatá složka bez zámku queued, se zámkem running; dry_run jen bez run.lock."""
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", "s")
    hook = server.Webhook(proj / "workflows", fake=Fake(None))  # bez start(): nikdo frontu nezpracuje
    s, body = hook.accept(f"Bearer {TOKEN}", json.dumps({"scenario": "prejmenuj"}).encode(), gui=True)
    assert s == 202
    run_id = body["run_id"]
    assert api.run_detail(proj, run_id) == {"run_id": run_id, "status": "queued", "state": "queued",
                                            "scenario": "prejmenuj", "queue_position": 1}
    d = proj / "runs" / run_id
    d.mkdir()  # pracovní vlákno vytvořilo složku, zámek ještě nemá
    for detail in (api.run_detail(proj, run_id), api.runs_list(proj)[0]):
        assert detail and detail["state"] == "queued" and detail["status"] == "queued" and detail["queue_position"] == 1
    (d / "run.lock").touch()
    (d / "plan.md").write_text("# plán\n")
    assert api.run_detail(proj, run_id)["state"] == "queued"  # type: ignore[index]
    with held_lock(d):
        assert api.run_detail(proj, run_id)["state"] == "running"  # type: ignore[index]
    (proj / "runs" / "_queue" / f"{run_id}.json").unlink()  # server skončil a frontu někdo smazal
    assert api.runs_list(proj)[0]["state"] == "interrupted"  # plan.md + run.lock = ostrý běh, ne dry-run
    dry = api.dry_run(api.load("prejmenuj", project_root=proj, offline=True), {}).dir
    assert api.run_detail(proj, dry.name)["state"] == "dry_run"  # type: ignore[index]


def test_http_batch_render_head(registry_server):  # noqa: F811
    _, client, a, _ = registry_server
    assert api.write_file(a, "scenarios/prejmenuj.yaml", None, PREJMENUJ)["errors"] == []
    tag = client.get("/projects/alfa/scenarios/prejmenuj").json()["etag"]
    # lehký otisk: HEAD s hlavičkou ETag, GET ?etag_only=1
    h = client.head("/projects/alfa/files/scenarios/prejmenuj.yaml")
    assert h.status_code == 200 and h.headers["etag"] == f'"{tag}"' and h.content == b""
    assert client.get("/projects/alfa/files/scenarios/prejmenuj.yaml?etag_only=1").json() == {"etag": tag}
    assert client.head("/projects/alfa/files/scenarios/neni.yaml").status_code == 404
    assert client.head("/projects/alfa/files/.env").status_code == 404
    assert httpx.head(f"{client.base_url}/projects/alfa/files/config.yaml").status_code == 401
    # render: nic se nezapíše, chyby jako objekty
    r = client.post("/projects/alfa/scenarios/prejmenuj/render", json={"ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": "navrh", "rename_refs": False}]})
    assert r.status_code == 200 and set(r.json()) == {"text", "tree", "errors"}
    assert r.json()["tree"][0]["id"] == "navrh" and r.json()["errors"][0]["file"] == "scenarios/prejmenuj.yaml"
    assert client.head("/projects/alfa/files/scenarios/prejmenuj.yaml").headers["etag"] == f'"{tag}"'
    raw = client.post("/projects/alfa/scenarios/prejmenuj/render", json={"text": PREJMENUJ})
    assert raw.status_code == 200 and set(raw.json()) == {"tree", "errors"}
    assert raw.json()["tree"][0]["id"] == "napis" and raw.json()["errors"] == []
    checked = client.post("/projects/alfa/validate", json={"path": "scenarios/prejmenuj.yaml", "text": PREJMENUJ})
    assert checked.status_code == 200 and checked.json()["tree"][0]["id"] == "napis"
    assert checked.json()["errors"] == []
    assert (a / "workflows" / "scenarios" / "prejmenuj.yaml").read_text() == PREJMENUJ
    # batch: 422 s indexem operace, 409, 200
    r = client.post("/projects/alfa/scenarios/prejmenuj/batch", json={"etag": tag, "ops": [
        {"op": "set_header", "fields": {"description": "x"}}, {"op": "delete_step", "address": ["steps", 5]}]})
    assert r.status_code == 422 and r.json()["op"] == 1 and r.json()["errors"][0]["message"].startswith("ops[1]")
    r = client.post("/projects/alfa/scenarios/prejmenuj/batch", json={"etag": tag, "ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": []}]})
    assert r.status_code == 422 and r.json()["errors"][0] | {"message": ""} == {
        "message": "", "step": "napis", "field": "new_id"}
    r = client.post("/projects/alfa/scenarios/prejmenuj/batch", json={"etag": tag, "ops": [
        {"op": "add_step", "after": ["steps", 9], "step": {"id": "novy", "fail": "chyba"}}]})
    assert r.status_code == 422 and r.json()["errors"][0]["step"] == "novy"
    assert client.post("/projects/alfa/scenarios/prejmenuj/batch", json={"etag": "x", "ops": []}).status_code == 409
    r = client.post("/projects/alfa/scenarios/prejmenuj/batch", json={"etag": tag, "ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": "navrh"}]})
    assert r.status_code == 200 and r.json()["errors"] == []
    # PUT …/steps/<adresa> = celý krok
    r = client.put("/projects/alfa/scenarios/prejmenuj/steps/0", json={"etag": r.json()["etag"], "step": {
        "id": "navrh", "ask": {"agent": "pisatel", "prompt": "Jiný"}}})
    assert r.status_code == 200 and "prompt: Jiný" in (a / "workflows" / "scenarios" / "prejmenuj.yaml").read_text()
    # POST scenarios/agents s popisem a modelem
    r = client.post("/projects/alfa/agents", json={"name": "grafik", "description": "Kreslí", "model": "gemini-image"})
    assert r.status_code == 200
    assert client.post("/projects/alfa/agents", json={"name": "x", "model": "neni"}).status_code == 422
    body = client.get("/projects/alfa").json()
    assert body["models_used"]["gemini-image"] == ["agents/grafik.md"] and body["links"]["scenario_model"] == []
    # files/ s chybami validate souboru (objekty jako v GET /projects/<p>)
    f = a / "workflows" / "scenarios" / "prejmenuj.yaml"
    f.write_text(f.read_text().replace("prompt: Jiný", 'prompt: "{{ steps.nic.text }}"'))
    errs = client.get("/projects/alfa/files/scenarios/prejmenuj.yaml").json()["errors"]
    assert errs and errs == next(s["errors"] for s in client.get("/projects/alfa").json()["scenarios"]
                                 if s["name"] == "prejmenuj")


def test_http_fresh_run_is_never_dry_run(registry_server):  # noqa: F811
    """15 přes HTTP: od 202 do konce běhu jen queued/running/succeeded."""
    _, client, _, _ = registry_server
    run_id = client.post("/projects/alfa/runs", json={"scenario": "ukazka"}).json()["run_id"]
    seen = set()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        states = {client.get(f"/projects/alfa/runs/{run_id}").json()["state"],
                  next(x["state"] for x in client.get("/projects/alfa/runs").json()["runs"] if x["run_id"] == run_id)}
        seen |= states
        if states == {"succeeded"}:
            break
        time.sleep(0.01)
    assert "succeeded" in seen and seen <= {"queued", "running", "succeeded"}
