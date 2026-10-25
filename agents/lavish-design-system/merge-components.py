#!/usr/bin/env python3
"""Union component preview CSS into one sheet. Cover's canvas rules lose to the page shell."""
import pathlib
import re

root = pathlib.Path("/Users/zbornheimer/.lavish-axi/design-system/components")
decls = {}
order = []

COVER_CANVAS = {"html,body", "body", "h1", "p", "svg"}

def add(sel, body, source):
    sel = " ".join(sel.split())
    body = " ".join(body.split())
    if source == "Cover" and sel in COVER_CANVAS:
        return
    if sel not in decls:
        order.append(sel)
        decls[sel] = body
        return
    if decls[sel] != body:
        raise SystemExit(f"conflict {sel} from {source}:\n  kept {decls[sel]}\n  new  {body}")

for path in sorted(root.glob("*/preview.html")):
    text = path.read_text()
    match = re.search(r"<style[^>]*>(.*?)</style>", text, re.S)
    if not match:
        continue
    for sel, body in re.findall(r"([^{}]+)\{([^{}]+)\}", match.group(1)):
        add(sel, body, path.parent.name)

out = pathlib.Path("/Users/zbornheimer/.lavish-axi/design-system/components.css")
lines = [
    "/* Generated from components/*/preview.html. Cover's canvas rules are omitted. */",
    "/* Regenerate with the merge script if the design-system zip is replaced. Do not edit by hand. */",
    "",
]
for sel in order:
    lines.append(f"{sel} {{{decls[sel]}}}")
out.write_text("\n".join(lines) + "\n")
print(f"wrote {out} selectors={len(order)} bytes={out.stat().st_size}")
