"""report.html (run-record.md): jeden soubor bez externích zdrojů, kroky, prompty
a odpovědi v <details>, chyba; nikdy base64 ani tajné hodnoty."""
from pathlib import Path

from conftest import events, run

from maw.loader import read_yaml

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
