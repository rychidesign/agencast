"""report.html (run-record.md): one file with no external resources, steps, prompts
and responses in <details>, error; never base64 or secret values. Costs in summary.md
and report.html: full precision, Total row (run time and cost)."""
import json
from pathlib import Path

from conftest import events, run, scenario
from test_engine import PARALLEL

from agencast import engine
from agencast.loader import read_yaml
from agencast.record import format_number, format_usd, format_value

GOLDEN = read_yaml(Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "ig-post.yaml")
SECRET = "secret-callback-value-789"


def test_report_success_masks_secret_and_has_no_base64(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    monkeypatch.setattr(engine, "now_iso", lambda: "2026-09-29T14:05:37.000Z")
    script = {**GOLDEN, "copy": {"json": {"caption": f"Coffee {SECRET}", "hashtags": ["#coffee"], "image_idea": "a cup"}}}
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"topic": "coffee"}, script)
    assert r.status == "succeeded", r.error
    html = (r.rec.dir / "report.html").read_text()
    assert html.startswith("<!doctype html>") and "<style>" in html
    assert "2026-09-29 14:05 UTC" in html
    assert "2026-09-29 14:05 UTC" in (r.rec.dir / "summary.md").read_text()
    assert "base64," not in html and SECRET not in html and "<secret: CALLBACK_SECRET>" in html
    for bad in ("<script", "<link", "src=", "@import", "url("):
        assert bad not in html, bad
    for step in ("copy", "tone_check", "photo_prompt", "photo", "out"):
        assert f"<td>{step}</td>" in html, step
    assert "<details><summary>Prompt</summary>" in html and "Write an IG post about: coffee" in html
    assert "skipped" in html and "when: steps.tone_check.on_brand &lt; 0.7 → false" in html
    up = events(r, "file_uploaded")[-1]
    assert up["output"] == "report" and r.report_url == up["url"] and Path(up["url"][7:]).read_text() == html


def test_report_failure_shows_error(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"topic": "coffee"}, {"tone_check": {"answers": {"on_brand": 0.2}}})
    assert r.status == "failed"
    html = (r.rec.dir / "report.html").read_text()
    assert "— <span class=\"err\">failed</span>" in html and "<h2 class=\"err\">Error</h2>" in html
    assert "step <code>stop</code>" in html and "The text does not match the brand (on_brand = 0.2)" in html


def test_report_long_prompt_is_cut(wf):
    long = "x" * 9000
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"topic": long}, GOLDEN)
    html = (r.rec.dir / "report.html").read_text()
    assert "truncated" in html and long not in html
    assert long in (r.rec.dir / "steps/01-copy/prompt.md").read_text()  # full text stays in the record


# --- costs: full precision, Total row (0.2.4, time 0.2.5) -----------------------------------------------------

def test_format_usd():
    assert [format_usd(x) for x in (0, 0.0015, 4.482e-06, 0.0693, 1, 0.1 + 0.2)] == \
        ["0", "0.0015", "0.000004482", "0.0693", "1.0000", "0.3000"]
    assert format_number(12.45, 1) == "12.4"
    assert format_value(0.75) == "0.75"


def total(r):
    fin = events(r, "run_finished")[0]
    cb = json.loads((r.rec.dir / "callback.json").read_text())
    assert fin["usage"]["cost_usd"] == cb["cost_usd"]
    return fin["usage"]["cost_usd"]


def total_time(r):
    """Time in the Total row = duration_s from run_finished (whole run time)."""
    return f"{format_number(events(r, 'run_finished')[0]['duration_s'], 1)} s"


def test_call_cost_exact_and_total_row(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"topic": "coffee"}, {**GOLDEN, "copy": {**GOLDEN["copy"][0], "cost": 4.482e-06}})
    assert r.status == "succeeded", r.error
    call = events(r, "model_call")[0]
    assert call["step"] == "copy" and call["usage"]["cost_usd"] == 4.482e-06  # unchanged from the provider
    assert json.loads((r.rec.dir / call["response_file"]).read_text())["usage"]["cost"] == 4.482e-06
    assert [e["cost_usd"] for e in events(r, "step_finished") if e["step"] == "copy"] == [4.482e-06]
    cost = total(r)
    assert cost == round(4.482e-06 + 3 * 0.0001 + 0.04, 10)
    md = (r.rec.dir / "summary.md").read_text()
    assert f"· {format_usd(cost)} USD (of which images 0.0400 USD)" in md
    assert "| 1 | copy | ask | ✓ |" in md and "| 0.000004482 | smart" in md
    assert "| 8 | out | output | ✓ | 0.0 s | 0 |  |" in md  # step without a model call
    t = total_time(r)
    assert f"| | Total | | | {t} | {format_usd(cost)} | of which images 0.0400 |\n\n## Warnings" in md
    html = (r.rec.dir / "report.html").read_text()
    assert f"<td>Total</td><td></td><td></td><td>{t}</td><td>{format_usd(cost)}</td><td>of which images 0.0400</td>" in html
    assert "0.000004482 USD" in html  # call header in step details


def test_total_row_on_failed_run(wf):
    r, _ = run(wf / "scenarios" / "ig-post.yaml", {"topic": "coffee"}, {"tone_check": {"answers": {"on_brand": 0.2}}})
    assert r.status == "failed"
    cost = total(r)
    assert cost == 0.0002
    t = total_time(r)
    assert f"| | Total | | | {t} | 0.0002 |  |" in (r.rec.dir / "summary.md").read_text()
    assert f"<td>Total</td><td></td><td></td><td>{t}</td><td>0.0002</td><td></td>" in (r.rec.dir / "report.html").read_text()


def test_total_time_is_run_time_not_sum_with_parallel(wf):
    """Parallel branches run concurrently and nested steps are included in p time → Total is not the Time column sum."""
    r, _ = run(scenario(wf, PARALLEL), script={"r1": {"sleep": 0.3, "text": "A"}, "s1": {"sleep": 0.3, "text": "B"}})
    assert r.status == "succeeded", r.error
    run_s = events(r, "run_finished")[0]["duration_s"]
    step_sum = sum(e["duration_s"] for e in events(r, "step_finished"))
    assert step_sum > 2 * run_s  # r1, s1 and p each take ~0.3 s, and so does the run
    t = total_time(r)
    assert t != f"{format_number(step_sum, 1)} s"
    assert f"| | Total | | | {t} | 0.0002 |  |" in (r.rec.dir / "summary.md").read_text()
    assert f"<td>Total</td><td></td><td></td><td>{t}</td><td>0.0002</td>" in (r.rec.dir / "report.html").read_text()
