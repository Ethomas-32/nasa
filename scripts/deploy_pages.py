"""Publish the website + results to the `gh-pages` branch for GitHub Pages.
    .\\.venv\\Scripts\\python.exe scripts\\deploy_pages.py
The site is staged in a temporary folder (web/ + export/ without NetCDF, a root redirect, .nojekyll)
and force-pushed as a single commit to `gh-pages` on `origin`. `main` and the working tree are not
touched. Re-run after rebuilding results (scripts/build_export.py) to update the live site.
One-time setup on GitHub: Settings > Pages > Source "Deploy from a branch" > gh-pages, / (root).
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "gh-pages"

REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Resource Trends</title>
<meta http-equiv="refresh" content="0; url=web/">
<link rel="canonical" href="web/"></head>
<body><p><a href="web/">Open Resource Trends</a></p></body></html>
"""


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def main():
    remote = git("remote", "get-url", "origin", cwd=ROOT)
    head = git("rev-parse", "--short", "HEAD", cwd=ROOT)
    if not (ROOT / "export" / "index.json").exists():
        raise SystemExit("export/ is missing: run scripts/build_export.py first")
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / "site"
        shutil.copytree(ROOT / "web", site / "web")
        shutil.copytree(ROOT / "export", site / "export", ignore=shutil.ignore_patterns("*.nc"))
        (site / "index.html").write_text(REDIRECT, encoding="utf-8")
        (site / ".nojekyll").write_text("", encoding="utf-8")
        n = sum(1 for p in site.rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in site.rglob("*") if p.is_file()) / 1e6
        git("init", "-q", "-b", BRANCH, cwd=site)
        name = git("config", "user.name", cwd=ROOT)
        email = git("config", "user.email", cwd=ROOT)
        git("config", "user.name", name, cwd=site)
        git("config", "user.email", email, cwd=site)
        git("config", "core.autocrlf", "false", cwd=site)
        git("add", "-A", cwd=site)
        git("commit", "-q", "-m", f"Deploy site from main@{head}", cwd=site)
        print(f"pushing {n} files ({size:.0f} MB) to {remote} {BRANCH} ...", flush=True)
        subprocess.run(["git", "push", "--force", remote, f"{BRANCH}:{BRANCH}"], cwd=site, check=True)
    owner_repo = remote.rstrip("/").removesuffix(".git").split("github.com/")[-1]
    owner, repo = owner_repo.split("/")
    print(f"done. Site (after GitHub builds it, ~1-2 min): https://{owner.lower()}.github.io/{repo}/web/")


if __name__ == "__main__":
    main()
