"""report.html (run-record.md): jeden soubor bez externích zdrojů, kroky, prompty
a odpovědi v <details>, chyba; nikdy base64 ani tajné hodnoty. Ceny v summary.md
a report.html: celé, řádek Celkem."""
import json
from pathlib import Path

from conftest import events, run

from maw.loader import read_yaml
from maw.record import cz_usd

GOLDEN = read_yaml(Path(__file__).parent / "golden" / "ig-post.yaml")
SECRET = "tajna-hodnota-callbacku-789"


def test_report_success_masks_secret_and_has_no_base64(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    script = {**GOLDEN, "copy": {"json": {"caption": f"Káva {SECRET}", "hashtags": ["#kava"], "image_idea": "hrnek"}}}
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"}, script)
    assert r.status == "succeeded", r.error
    html = (r.rec.dir / "report.html").read_text()
    assert html.startswith("<!doctype html>") and "<style>" in html
    assert "base64," not in html and SECRET not in html and "<tajné: CALLBACK_SECRET>" in html
    for bad in ("<script", "<link", "src=", "@import", "url("):
        assert bad not in html, bad
    for step in ("copy", "kontrola", "foto_prompt", "foto", "out"):
        assert f"<td>{step}</td>" in html, step
    assert "<details><summary>Prompt</summary>" in html and "Napiš IG příspěvek na téma: káva" in html
    assert "přeskočeno" in html and "when: steps.kontrola.on_brand &lt; 0.7 → false" in html
    up = events(r, "file_uploaded")[-1]
    assert up["output"] == "report" and r.report_url == up["url"] and Path(up["url"][7:]).read_text() == html


def test_report_failure_shows_error(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"}, {"kontrola": {"answers": {"on_brand": 0.2}}})
    assert r.status == "failed"
    html = (r.rec.dir / "report.html").read_text()
    assert "— <span class=\"err\">chyba</span>" in html and "<h2 class=\"err\">Chyba</h2>" in html
    assert "krok <code>stop</code>" in html and "Text neodpovídá značce (on_brand = 0.2)" in html


def test_report_long_prompt_is_cut(wf):
    long = "x" * 9000
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": long}, GOLDEN)
    html = (r.rec.dir / "report.html").read_text()
    assert "zkráceno" in html and long not in html
    assert long in (r.rec.dir / "steps/01-copy/prompt.md").read_text()  # celý zůstává v záznamu


# --- ceny: celé, řádek Celkem (0.2.4) -----------------------------------------------------

def test_cz_usd():
    assert [cz_usd(x) for x in (0, 0.0015, 4.482e-06, 0.0693, 1, 0.1 + 0.2)] == \
        ["0", "0,0015", "0,000004482", "0,0693", "1,0000", "0,3000"]


def total(r):
    fin = events(r, "run_finished")[0]
    cb = json.loads((r.rec.dir / "callback.json").read_text())
    assert fin["usage"]["cost_usd"] == cb["cost_usd"]
    return fin["usage"]["cost_usd"]


def test_call_cost_exact_and_total_row(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"}, {**GOLDEN, "copy": {**GOLDEN["copy"][0], "cost": 4.482e-06}})
    assert r.status == "succeeded", r.error
    call = events(r, "model_call")[0]
    assert call["step"] == "copy" and call["usage"]["cost_usd"] == 4.482e-06  # beze změny od poskytovatele
    assert json.loads((r.rec.dir / call["response_file"]).read_text())["usage"]["cost"] == 4.482e-06
    assert [e["cost_usd"] for e in events(r, "step_finished") if e["step"] == "copy"] == [4.482e-06]
    cost = total(r)
    assert cost == round(4.482e-06 + 3 * 0.0001 + 0.04, 10)
    md = (r.rec.dir / "summary.md").read_text()
    assert f"· {cz_usd(cost)} USD (z toho obrázky 0,0400 USD)" in md
    assert "| 1 | copy | ask | ✓ |" in md and "| 0,000004482 | chytry" in md
    assert "| 8 | out | output | ✓ | 0,0 s | 0 |  |" in md  # krok bez volání modelu
    assert f"| | Celkem | | | | {cz_usd(cost)} | z toho obrázky 0,0400 |\n\n## Varování" in md
    html = (r.rec.dir / "report.html").read_text()
    assert f"<td>Celkem</td><td></td><td></td><td></td><td>{cz_usd(cost)}</td><td>z toho obrázky 0,0400</td>" in html
    assert "0,000004482 USD" in html  # hlavička volání v detailu kroku


def test_total_row_on_failed_run(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"}, {"kontrola": {"answers": {"on_brand": 0.2}}})
    assert r.status == "failed"
    cost = total(r)
    assert cost == 0.0002
    assert "| | Celkem | | | | 0,0002 |  |" in (r.rec.dir / "summary.md").read_text()
    assert "<td>Celkem</td><td></td><td></td><td></td><td>0,0002</td><td></td>" in (r.rec.dir / "report.html").read_text()
