"""Render docs/visuals/*.html -> docs/images/*.png at 2x with Playwright (Chromium).

    python docs/visuals/build_data.py && python docs/visuals/render.py     # everything
    python docs/visuals/render.py results headline                         # just those pages

Each page draws into a #frame element (800 css px wide -> 1600 px PNG; the cover is 1000x420 -> 2000x840)
and that element is screenshotted. If this interpreter has no playwright, the script re-runs itself with
docs/visuals/.venv (create it once):

    python -m uv venv --python 3.12 docs/visuals/.venv
    python -m uv pip install --python docs/visuals/.venv/Scripts/python.exe playwright
    docs/visuals/.venv/Scripts/python.exe -m playwright install chromium
Fonts (Barlow Condensed, Public Sans, IBM Plex Mono) load from Google Fonts, so rendering needs a network.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ["RECALLDESK_VISUALS_OUT"]) if os.environ.get("RECALLDESK_VISUALS_OUT") else HERE.parent / "images"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    venv_py = HERE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
        sys.exit(subprocess.call([str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]]))
    sys.exit("playwright is not installed; see the setup lines at the top of docs/visuals/render.py")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    names = sys.argv[1:] or sorted(p.stem for p in HERE.glob("*.html") if not p.stem.startswith("_"))
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:
            # fall back to any already-downloaded headless shell (avoids a re-download on version skew)
            shells = sorted(Path.home().glob("AppData/Local/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell*"))
            if not shells:
                raise
            browser = pw.chromium.launch(executable_path=str(shells[-1]))
        ctx = browser.new_context(viewport={"width": 1200, "height": 1000}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("  PAGE ERROR:", e))
        page.on("console", lambda m: m.type in ("error", "warning") and print("  console:", m.text))
        for name in names:
            page.goto((HERE / f"{name}.html").as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)
            frame = page.locator("#frame")
            box = frame.bounding_box()
            out = OUT / f"{name}.png"
            frame.screenshot(path=str(out), animations="disabled")
            wm = page.locator(".wm-badge").count()
            print(f"{out.name}: {int(box['width'] * 2)}x{int(box['height'] * 2)} px" + ("  [WATERMARKED]" if wm else ""))
        browser.close()


if __name__ == "__main__":
    main()
