"""Auth state helper: save a manual login once, reuse it later.

Usage:
    # 1. Save: opens a headed browser, you log in by hand, press Enter.
    python -m traj_gen.auth_helper save https://github.com/login --name github

    # 2. Reuse in code:
    from traj_gen.auth_helper import load_storage_state
    context = browser.new_context(storage_state=load_storage_state("github"))
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

AUTH_DIR = Path(__file__).resolve().parent.parent / "auth"


def auth_path(name: str) -> Path:
    return AUTH_DIR / f"{name}.json"


def load_storage_state(name: str) -> str | None:
    """Return path to a saved auth state file, or None if missing."""
    p = auth_path(name)
    return str(p) if p.exists() else None


def save_auth(url: str, name: str, executable_path: str | None = None) -> Path:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    out = auth_path(name)

    with sync_playwright() as pw:
        launch_kwargs = {"headless": False}
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)

        print(f"\n[auth_helper] Browser opened at: {url}")
        print("[auth_helper] Log in manually, then come back here and press Enter.")
        input("[auth_helper] Press Enter when login is complete... ")

        context.storage_state(path=str(out))
        browser.close()

    print(f"[auth_helper] Saved auth state to: {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Save/inspect browser auth state.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser("save", help="Open a headed browser and save login state.")
    p_save.add_argument("url", help="URL to open (e.g. site login page).")
    p_save.add_argument("--name", required=True, help="Identifier, e.g. 'github'.")
    p_save.add_argument(
        "--chrome",
        default=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"),
        help="Path to Chrome executable (default: /usr/bin/google-chrome).",
    )

    p_list = sub.add_parser("list", help="List saved auth states.")

    args = parser.parse_args()

    if args.cmd == "save":
        save_auth(args.url, args.name, executable_path=args.chrome or None)
    elif args.cmd == "list":
        if not AUTH_DIR.exists():
            print("(no auth states saved)")
            return
        for p in sorted(AUTH_DIR.glob("*.json")):
            print(p.stem)


if __name__ == "__main__":
    main()
