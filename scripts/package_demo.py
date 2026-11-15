"""Bundle the website + results into a zip that runs on another device with only Python 3 installed.
    .\\.venv\\Scripts\\python.exe scripts\\package_demo.py            -> dist/resource-trends-demo.zip
NetCDF files are left out (the website reads only PNG and JSON).
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "resource-trends-demo.zip"
TOP = "resource-trends-demo"
PORT = 8765

BAT = rf"""@echo off
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
echo Starting the Resource Trends server in a separate window (close that window to stop the demo).
start "Resource Trends server - close to stop" %PY% -m http.server {PORT} --bind 127.0.0.1
timeout /t 2 /nobreak >nul
start "" http://localhost:{PORT}/web/
"""

COMMAND = f"""#!/bin/sh
cd "$(dirname "$0")"
echo "Starting Resource Trends demo on http://localhost:{PORT}/web/  (close this window to stop)"
(sleep 1; open "http://localhost:{PORT}/web/" 2>/dev/null || xdg-open "http://localhost:{PORT}/web/") &
python3 -m http.server {PORT} --bind 127.0.0.1
"""

README = f"""Resource Trends demo
====================
Needs: Python 3 (no extra packages) and an internet connection (map libraries, basemap and globe
texture load from the web; all analysis results are in this folder).

Windows: double-click START-DEMO.bat
macOS:   double-click start-demo.command (first time: right-click > Open, because it is unsigned)
Linux:   sh start-demo.command
Manual:  open a terminal in this folder, run  python -m http.server {PORT}  and browse to
         http://localhost:{PORT}/web/

Pages: http://localhost:{PORT}/web/ (globe) and http://localhost:{PORT}/web/dashboard.html?region=conus
Demo links: add ?teaser=trend:precipitation or ?teaser=portfolio:r_solar_hydro to the globe URL.
Stop: close the terminal window.
"""


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for folder in ("web", "export"):
            for p in sorted((ROOT / folder).rglob("*")):
                if p.is_file() and p.suffix != ".nc":
                    z.write(p, f"{TOP}/{p.relative_to(ROOT).as_posix()}")
                    n += 1
        z.writestr(f"{TOP}/START-DEMO.bat", BAT.replace("\n", "\r\n"))
        info = zipfile.ZipInfo(f"{TOP}/start-demo.command")
        info.external_attr = 0o100755 << 16          # executable on macOS/Linux
        z.writestr(info, COMMAND)
        z.writestr(f"{TOP}/README.txt", README.replace("\n", "\r\n"))
    print(f"{OUT} ({OUT.stat().st_size / 1e6:.0f} MB, {n} data/web files)")


if __name__ == "__main__":
    main()
