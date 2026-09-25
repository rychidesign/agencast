"""Metadata kandidátů z PyPI a GitHubu (bez klíčů) → results/meta.json."""
import json, urllib.request
from pathlib import Path

PKGS = {
    "simpleeval": "danthedeckie/simpleeval",
    "asteval": "lmfit/asteval",
    "cel-python": "cloud-custodian/cel-python",
    "common-expression-language": "hardbyte/python-common-expression-language",
    "RestrictedPython": "zopefoundation/RestrictedPython",
    "evalidate": "yaroslaff/evalidate",
}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "spike-expressions"})
    return json.load(urllib.request.urlopen(req, timeout=20))

out = {}
for pkg, repo in PKGS.items():
    p = get(f"https://pypi.org/pypi/{pkg}/json")
    i, v = p["info"], p["info"]["version"]
    files = p["releases"][v]
    g = get(f"https://api.github.com/repos/{repo}")
    out[pkg] = {
        "version": v,
        "released": files[0]["upload_time"][:10] if files else None,
        "wheel_kb": min((f["size"] for f in files if f["packagetype"] == "bdist_wheel"), default=None) and
                    round(min(f["size"] for f in files if f["packagetype"] == "bdist_wheel") / 1024),
        "requires_dist": [r for r in (i.get("requires_dist") or []) if "extra ==" not in r],
        "requires_python": i.get("requires_python"),
        "repo": repo,
        "stars": g.get("stargazers_count"),
        "license": (g.get("license") or {}).get("spdx_id"),
        "pushed_at": (g.get("pushed_at") or "")[:10],
        "open_issues": g.get("open_issues_count"),
        "archived": g.get("archived"),
    }
Path("results").mkdir(exist_ok=True)
Path("results/meta.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
for k, m in out.items():
    print(k, m)
