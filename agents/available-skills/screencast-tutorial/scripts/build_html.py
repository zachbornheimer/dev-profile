#!/usr/bin/env python3
"""Render a tutorial Markdown file as one self-contained HTML page (Zysys Admin design system).

Usage: build_html.py TUTORIAL.md OUT.html --tokens TOKENS [--meta "line under the title"] [--badge "macOS · Nix"]

TOKENS is a design-system .zip (its */tokens.css is used) or a tokens .css file.
The first `# ` heading becomes the page title; each `## ` section becomes a card;
a `## Contents` section is dropped (the sticky sidebar replaces it), but a code
block inside it (e.g. a repo tree) moves to the intro card. Links whose text is
"▶ m:ss" are relabelled "Watch at m:ss". Images become JPEG data URIs.
Requires pandoc and Pillow.
"""

import argparse
import base64
import html
import io
import pathlib
import re
import subprocess
import sys
import zipfile

from PIL import Image

CSS = """
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:var(--space-20)}
body{margin:0;background:var(--color-bg-page);font-family:var(--font-sans);font-size:15px;color:var(--color-text);-webkit-font-smoothing:antialiased;line-height:var(--leading-relaxed)}
.shell{max-width:var(--layout-max-width);margin:0 auto;padding:var(--space-28) var(--layout-gutter);display:flex;flex-direction:column;gap:var(--space-20)}
.hdr{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--space-16);flex-wrap:wrap}
.hdr h1{margin:0;font-size:var(--text-page-title);font-weight:var(--weight-medium);letter-spacing:var(--tracking-title);line-height:var(--leading-tight)}
.hdr .meta{font-size:var(--text-body);color:var(--color-text-muted);margin-top:var(--space-6)}
.pill{display:inline-flex;align-items:center;gap:var(--space-8);font-size:var(--text-meta);font-weight:var(--weight-semibold);padding:5px var(--space-10) 5px var(--space-8);border-radius:var(--radius-pill);background:var(--color-accent-bg);color:var(--color-accent-hover);white-space:nowrap}
.pill i{width:8px;height:8px;border-radius:50%;background:var(--color-accent)}
.layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:var(--space-20);align-items:start}
nav.toc{position:sticky;top:var(--space-20);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-card);padding:var(--space-16) 0;max-height:calc(100vh - 40px);overflow:auto}
nav.toc .lbl{font-size:var(--text-badge);font-weight:var(--weight-semibold);letter-spacing:var(--tracking-badge);text-transform:uppercase;color:var(--color-text-muted);padding:0 var(--space-16) var(--space-8)}
nav.toc ol{list-style:none;margin:0;padding:0}
nav.toc a{display:block;padding:var(--space-6) var(--space-16);font-size:var(--text-body);color:var(--color-text-secondary);text-decoration:none;border-left:2px solid transparent;line-height:var(--leading-tight)}
nav.toc a:hover{background:var(--color-surface-subtle);color:var(--color-text)}
nav.toc a.on{color:var(--color-text);font-weight:var(--weight-semibold);border-left-color:var(--color-accent);background:var(--color-accent-bg)}
main{display:flex;flex-direction:column;gap:var(--space-16);min-width:0}
.card{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-card);padding:var(--space-24) var(--space-28)}
.prose>*:first-child{margin-top:0}.prose>*:last-child{margin-bottom:0}
.prose h2{font-size:var(--text-heading-lg);font-weight:var(--weight-semibold);margin:0 0 var(--space-12);padding-bottom:var(--space-12);border-bottom:1px solid var(--color-divider)}
.prose h3{font-size:var(--text-section-title);font-weight:var(--weight-semibold);margin:var(--space-28) 0 var(--space-8)}
.prose p,.prose li{color:var(--color-text-secondary)}
.prose p{margin:0 0 var(--space-12)}
.prose ul,.prose ol{margin:0 0 var(--space-12);padding-left:var(--space-24)}
.prose li{margin:var(--space-4) 0}
.prose strong{color:var(--color-text);font-weight:var(--weight-semibold)}
.prose a{color:var(--color-accent);text-decoration:none}.prose a:hover{color:var(--color-accent-hover);text-decoration:underline}
.prose code{font-family:var(--font-mono);font-size:var(--text-mono);background:var(--color-surface-subtle);border:1px solid var(--color-border);border-radius:var(--radius-badge);padding:1px 5px;color:var(--color-text)}
.prose pre{position:relative;background:var(--color-surface-subtle);border:1px solid var(--color-border);border-radius:var(--radius-control);padding:var(--space-14) var(--space-16);overflow-x:auto;margin:0 0 var(--space-16);line-height:var(--leading-body)}
.prose pre code{background:none;border:0;padding:0;font-size:var(--text-mono)}
.copy{position:absolute;top:var(--space-8);right:var(--space-8);font-family:var(--font-sans);font-size:var(--text-meta);font-weight:var(--weight-medium);padding:3px var(--space-10);border-radius:var(--radius-control);border:1px solid var(--color-border-control);background:var(--color-surface);color:var(--color-text);cursor:pointer;opacity:0;transition:opacity .12s}
.prose pre:hover .copy,.copy:focus{opacity:1}
.copy.done{border-color:var(--color-success);color:var(--color-success-text);background:var(--color-success-bg)}
.prose figure,.prose p>img{margin:var(--space-8) 0 var(--space-20)}
.prose img{display:block;max-width:100%;height:auto;border:1px solid var(--color-border);border-radius:var(--radius-control);cursor:zoom-in}
.prose figcaption{font-size:var(--text-meta);color:var(--color-text-muted);margin-top:var(--space-6)}
.prose blockquote{margin:0 0 var(--space-16);padding:var(--space-12) var(--space-16);background:var(--color-warning-bg);border:1px solid var(--color-warning-border);border-radius:var(--radius-control)}
.prose blockquote p{color:var(--color-warning-text);margin:0}
.prose table{width:100%;border-collapse:collapse;margin:0 0 var(--space-16);font-size:var(--text-body)}
.prose th{text-align:left;font-size:var(--text-badge);font-weight:var(--weight-semibold);letter-spacing:var(--tracking-badge);text-transform:uppercase;color:var(--color-text-muted);padding:var(--space-8) var(--space-12);border-bottom:1px solid var(--color-border)}
.prose td{padding:9px var(--space-12);border-bottom:1px solid var(--color-row-divider);vertical-align:top}
.prose td code{white-space:nowrap}
.prose em{color:var(--color-text-muted)}
.lightbox{position:fixed;inset:0;background:rgba(29,35,39,.88);display:none;align-items:center;justify-content:center;padding:var(--space-24);z-index:10;cursor:zoom-out}
.lightbox.on{display:flex}.lightbox img{max-width:100%;max-height:100%;border-radius:var(--radius-control)}
@media (max-width:900px){.layout{grid-template-columns:1fr}nav.toc{position:static;max-height:none}.card{padding:var(--space-20)}}
"""

# Ids from GitHub-style anchors can start with a digit ("1-install-nix"), which is not a
# valid CSS #selector, so every lookup goes through getElementById.
JS = """
document.querySelectorAll('.prose pre').forEach(pre=>{const b=document.createElement('button');b.className='copy';b.type='button';b.textContent='Copy';
b.onclick=()=>navigator.clipboard.writeText(pre.querySelector('code').innerText).then(()=>{b.textContent='Copied';b.classList.add('done');setTimeout(()=>{b.textContent='Copy';b.classList.remove('done')},1400)});pre.appendChild(b)});
const lb=document.querySelector('.lightbox'),lbi=lb.querySelector('img');
document.querySelectorAll('.prose img').forEach(i=>i.onclick=()=>{lbi.src=i.src;lbi.alt=i.alt;lb.classList.add('on')});
lb.onclick=()=>lb.classList.remove('on');document.addEventListener('keydown',e=>{if(e.key==='Escape')lb.classList.remove('on')});
const links=[...document.querySelectorAll('nav.toc a')],secs=links.map(a=>document.getElementById(a.getAttribute('href').slice(1)));
const mark=a=>links.forEach(b=>b.classList.toggle('on',b===a));
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)mark(links[secs.indexOf(e.target)])}),{rootMargin:'-10% 0px -80% 0px'});
secs.forEach(s=>s&&io.observe(s));links.forEach(a=>a.addEventListener('click',()=>mark(a)));
"""


def load_tokens(path: pathlib.Path) -> str:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(
                (
                    n
                    for n in z.namelist()
                    if n.endswith("/tokens.css") or n == "tokens.css"
                ),
                None,
            )
            if not name:
                sys.exit(f"no tokens.css in {path}")
            return z.read(name).decode()
    return path.read_text()


def inline_images(fragment: str, root: pathlib.Path) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        src = root / html.unescape(m.group(1))
        if not src.exists():
            sys.exit(f"missing image: {src}")
        im = Image.open(src).convert("RGB")
        im.thumbnail((1440, 1440))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80, optimize=True)
        count += 1
        return f'src="data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}" loading="lazy"'

    return re.sub(r'src="(?!data:|https?:)([^"]+)"', repl, fragment), count


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("markdown", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument(
        "--tokens",
        type=pathlib.Path,
        default=pathlib.Path.home() / "Dropbox/Zysys/zysys-admin-design-system.zip",
    )
    ap.add_argument("--meta", default="")
    ap.add_argument("--badge", default="")
    a = ap.parse_args()

    fragment = subprocess.run(
        ["pandoc", "-f", "gfm", "-t", "html5", "--no-highlight", str(a.markdown)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    fragment, images = inline_images(fragment, a.markdown.parent)
    fragment = re.sub(r">▶\s+(\d+(?::\d\d)+)</a>", r">Watch at \1</a>", fragment)

    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", fragment, re.DOTALL)
    title = title_m.group(1) if title_m else a.markdown.stem
    body = fragment[title_m.end() :] if title_m else fragment
    intro, *sections = re.split(r"(?=<h2 )", body)
    intro = re.sub(r"<hr\s*/?>", "", intro)

    toc, cards = [], []
    for s in sections:
        s = re.sub(r"<hr\s*/?>\s*$", "", s.strip())
        m = re.match(r'<h2 id="([^"]+)">(.*?)</h2>', s, re.DOTALL)
        if not m:
            continue
        sid, heading = m.groups()
        if sid == "contents":
            intro += "".join(re.findall(r"<p>[^<]*</p>\s*<pre.*?</pre>", s, re.DOTALL))
            continue
        toc.append(
            f'<li><a href="#{sid}">{html.escape(re.sub("<[^>]+>", "", heading))}</a></li>'
        )
        cards.append(
            f'<section class="card prose" id="{sid}"><h2>{heading}</h2>{s[m.end() :]}</section>'
        )

    badge = f'<div class="pill"><i></i>{html.escape(a.badge)}</div>' if a.badge else ""
    plain_title = re.sub("<[^>]+>", "", title)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{plain_title}</title>
<style>{load_tokens(a.tokens)}{CSS}</style></head>
<body><div class="shell">
<div class="hdr"><div><h1>{title}</h1><div class="meta">{html.escape(a.meta)}</div></div>{badge}</div>
<div class="layout">
<nav class="toc" aria-label="Contents"><div class="lbl">Contents</div><ol><li><a href="#top">Overview</a></li>{"".join(toc)}</ol></nav>
<main><section class="card prose" id="top">{intro}</section>{"".join(cards)}</main>
</div></div>
<div class="lightbox" role="dialog" aria-label="Screenshot"><img alt=""></div>
<script>{JS}</script></body></html>"""
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(page)
    print(
        f"{a.out}  {a.out.stat().st_size / 1e6:.1f} MB · {len(cards)} sections · {images} images"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
