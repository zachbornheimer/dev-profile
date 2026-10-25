#!/usr/bin/env python3
# Re-runs when any of the bundle sources change (chezmoi hashes the rendered
# script body — the include-hash comments below ARE the change detector):
#
# main.swift:  {{ include (joinPath .chezmoi.sourceDir "dot_local/share/nvim-kitty/main.swift") | sha256sum }}
# info.plist:  {{ include (joinPath .chezmoi.sourceDir "dot_local/share/nvim-kitty/Info.plist") | sha256sum }}
"""Compile + install ~/Applications/NvimKitty.app from the chezmoi-managed sources."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HOME     = Path.home()
SOURCES  = HOME / ".local/share/nvim-kitty"
BUNDLE   = HOME / "Applications/NvimKitty.app"
SWIFTC   = "/usr/bin/swiftc"
LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/"
    "LaunchServices.framework/Versions/A/Support/lsregister"
)


def build_bundle() -> None:
    """Create the .app bundle structure and compile the Swift binary."""
    swift_src = SOURCES / "main.swift"
    if not swift_src.exists():
        sys.exit(f"missing source: {swift_src}")

    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)

    macos_dir     = BUNDLE / "Contents/MacOS"
    resources_dir = BUNDLE / "Contents/Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            SWIFTC,
            "-O",
            "-swift-version", "5",
            "-target", "arm64-apple-macosx12.0",
            str(swift_src),
            "-framework", "AppKit",
            "-o", str(macos_dir / "NvimKitty"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"swiftc failed (exit {result.returncode})")


def overlay_plist() -> None:
    shutil.copy2(SOURCES / "Info.plist", BUNDLE / "Contents/Info.plist")


def register() -> None:
    subprocess.run([LSREGISTER, "-f", str(BUNDLE)], check=True)


# Extensions where NvimKitty should be the DEFAULT handler.
DEFAULT_EXTENSIONS = (
    "py", "pyi", "md", "markdown", "txt", "json", "yaml", "yml",
    "toml", "ini", "conf", "cfg", "env",
    "sh", "bash", "zsh", "fish",
    "go", "rs",
    "ts", "tsx", "js", "jsx", "mjs", "cjs",
    "rb", "pl", "pm", "lua", "vim",
    "sql",
    "xml", "csv", "tsv", "log",
    "applescript", "scpt",
    "tf", "tfvars",
    "Dockerfile", "gitignore", "gitconfig",
)
BUNDLE_ID = "com.zbornheimer.nvim-kitty"


def claim_defaults() -> None:
    duti = shutil.which("duti")
    if not duti:
        print("claim_defaults: duti not installed — skipping (`brew install duti`)")
        return
    failed = []
    for ext in DEFAULT_EXTENSIONS:
        result = subprocess.run(
            [duti, "-s", BUNDLE_ID, ext, "all"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0:
            failed.append(ext)
    print(
        f"claim_defaults: {len(DEFAULT_EXTENSIONS) - len(failed)}/{len(DEFAULT_EXTENSIONS)} "
        f"extensions set to NvimKitty"
        + (f" (failed: {', '.join(failed)})" if failed else "")
    )


def main() -> None:
    build_bundle()
    overlay_plist()
    register()
    claim_defaults()
    print(f"NvimKitty: installed at {BUNDLE} and registered with LaunchServices")


if __name__ == "__main__":
    main()
