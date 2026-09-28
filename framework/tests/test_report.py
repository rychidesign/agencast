"""report.html (run-record.md): jeden soubor bez externích zdrojů, kroky, prompty
a odpovědi v <details>, chyba; nikdy base64 ani tajné hodnoty. Ceny v summary.md
a report.html: celé, řádek Celkem (čas a cena běhu)."""
import json
from pathlib import Path

from conftest import events, run, scenario
from test_engine import PARALLEL

from agencast.loader import read_yaml
from agencast.record import cz, cz_usd

GOLDEN = read_yaml(Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "ig-post.yaml")
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


# --- ceny: celé, řádek Celkem (0.2.4, čas 0.2.5) -----------------------------------------------------

def test_cz_usd():
    assert [cz_usd(x) for x in (0, 0.0015, 4.482e-06, 0.0693, 1, 0.1 + 0.2)] == \
        ["0", "0,0015", "0,000004482", "0,0693", "1,0000", "0,3000"]


def total(r):
    fin = events(r, "run_finished")[0]
    cb = json.loads((r.rec.dir / "callback.json").read_text())
    assert fin["usage"]["cost_usd"] == cb["cost_usd"]
    return fin["usage"]["cost_usd"]


def total_time(r):
    """Čas v řádku Celkem = duration_s z run_finished (čas celého běhu)."""
    return f"{cz(events(r, 'run_finished')[0]['duration_s'], 1)} s"


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
    t = total_time(r)
    assert f"| | Celkem | | | {t} | {cz_usd(cost)} | z toho obrázky 0,0400 |\n\n## Varování" in md
    html = (r.rec.dir / "report.html").read_text()
    assert f"<td>Celkem</td><td></td><td></td><td>{t}</td><td>{cz_usd(cost)}</td><td>z toho obrázky 0,0400</td>" in html
    assert "0,000004482 USD" in html  # hlavička volání v detailu kroku


def test_total_row_on_failed_run(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"}, {"kontrola": {"answers": {"on_brand": 0.2}}})
    assert r.status == "failed"
    cost = total(r)
    assert cost == 0.0002
    t = total_time(r)
    assert f"| | Celkem | | | {t} | 0,0002 |  |" in (r.rec.dir / "summary.md").read_text()
    assert f"<td>Celkem</td><td></td><td></td><td>{t}</td><td>0,0002</td><td></td>" in (r.rec.dir / "report.html").read_text()


def test_total_time_is_run_time_not_sum_with_parallel(wf):
    """Větve parallel běží současně a vnořené kroky jsou v čase p → Celkem není součet sloupce Čas."""
    r, _ = run(scenario(wf, PARALLEL), script={"r1": {"sleep": 0.3, "text": "A"}, "s1": {"sleep": 0.3, "text": "B"}})
    assert r.status == "succeeded", r.error
    run_s = events(r, "run_finished")[0]["duration_s"]
    step_sum = sum(e["duration_s"] for e in events(r, "step_finished"))
    assert step_sum > 2 * run_s  # r1, s1 i p trvají ~0,3 s, běh taky ~0,3 s
    t = total_time(r)
    assert t != f"{cz(step_sum, 1)} s"
    assert f"| | Celkem | | | {t} | 0,0002 |  |" in (r.rec.dir / "summary.md").read_text()
    assert f"<td>Celkem</td><td></td><td></td><td>{t}</td><td>0,0002</td>" in (r.rec.dir / "report.html").read_text()
