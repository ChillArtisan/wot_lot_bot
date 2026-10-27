"""HTML slide to PNG through headless Chromium, with no network.

Adapted from paygame_bot (`autopilot/paygame/screenshot.py`): the page is our
own template with everything (fonts, tank images) inlined as `data:` URIs, so
Chromium gets a CSP that forbids any request, a resolver that maps every host
to NOTFOUND and a dead proxy. Its background traffic never leaves the box.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import struct
import tempfile
from collections.abc import Sequence
from pathlib import Path

WIDTH = 1280
HEIGHT = 720
TIMEOUT_SECONDS = 40

CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
       "font-src data:; frame-src 'none'; form-action 'none'")

# Bare headless shell first (Docker image); then full browsers, which need
# --headless. The Windows paths are for running the bot locally.
_CANDIDATES = (
    "/usr/lib/chromium/chromium-headless-shell",
    "/usr/bin/chromium-headless-shell",
    "chromium-headless-shell",
    "chromium",
    "chromium-browser",
    "google-chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


class RenderError(RuntimeError):
    """Slide not rendered. The text is for the owner, with no paths or args."""


def find_browser(configured: str = "") -> list[str] | None:
    """Chromium command, or None if there is none."""
    for candidate in ((configured,) if configured.strip() else _CANDIDATES):
        path = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if path and os.path.isfile(path) and (os.name == "nt" or os.access(path, os.X_OK)):
            command = [path]
            if "headless-shell" not in os.path.basename(path):
                command.append("--headless")
            return command
    return None


def png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\x89PNG") or len(data) < 24:
        return (0, 0)
    return struct.unpack(">II", data[16:24])


def _child_env(home: str) -> dict[str, str]:
    # The bot's environment holds the Telegram and Lolz tokens; the browser
    # needs none of it.
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TZ", "TMPDIR", "TEMP", "TMP",
            "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "USERPROFILE")
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env["HOME"] = home
    return env


# One Chromium at a time: hundreds of MB on a server shared with other bots.
_render_lock = asyncio.Lock()


async def render(markup: str, *, browser: Sequence[str], width: int = WIDTH,
                 height: int = HEIGHT, timeout: float = TIMEOUT_SECONDS) -> bytes:
    """PNG of the page at exactly width x height."""
    async with _render_lock:
        workdir = tempfile.mkdtemp(prefix="wot-slide-")
        try:
            page = Path(workdir) / "page.html"
            page.write_text(markup, encoding="utf-8")
            out = Path(workdir) / "shot.png"
            args = [
                *browser,
                "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--hide-scrollbars", "--mute-audio",
                "--force-device-scale-factor=1", f"--window-size={width},{height}",
                "--host-resolver-rules=MAP * ~NOTFOUND", "--proxy-server=http://127.0.0.1:9",
                "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                "--disable-component-update", "--disable-sync", "--disable-default-apps",
                "--disable-extensions", "--disable-breakpad",
                f"--user-data-dir={Path(workdir) / 'profile'}",
                f"--screenshot={out}",
                page.as_uri(),
            ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL, env=_child_env(workdir), cwd=workdir,
                )
            except OSError:
                raise RenderError("Chromium не запустился.") from None
            try:
                await asyncio.wait_for(process.wait(), timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise RenderError(f"Chromium не уложился в {int(timeout)} с.") from None
            try:
                data = out.read_bytes()
            except OSError:
                raise RenderError("Chromium не записал картинку.") from None
            if not data.startswith(b"\x89PNG"):
                raise RenderError("Chromium записал не картинку.")
            return data
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
