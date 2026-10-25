# Computed-style snapshot

The proof for every editing phase. Same pages, same selectors, same viewport;
the JSON must be byte-identical across phases.

Pick 3–5 representative pages and a selector list covering: body, a heading,
a paragraph, a primary button, a field, a card, a full-width band, header,
footer, a link. Capture with Playwright (already present in most of Zach's
repos; otherwise `pnpm dlx playwright`):

```js
// scripts/style-snapshot.mjs — run: node scripts/style-snapshot.mjs <out.json>
import { chromium } from "playwright";
const PAGES = ["/", "/pricing"];
const SELECTORS = [
  "body",
  "h1",
  "p",
  "button.primary",
  "input",
  ".card",
  "section.band",
  "header",
  "footer",
  "a",
];
const PROPS = [
  "color",
  "background-color",
  "background-image",
  "border-color",
  "font-family",
  "font-size",
  "border-radius",
  "padding",
  "gap",
  "min-height",
  "transition-duration",
];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const out = {};
for (const path of PAGES) {
  await page.goto(`http://localhost:5173${path}`);
  out[path] = await page.evaluate(
    ({ SELECTORS, PROPS }) =>
      Object.fromEntries(
        SELECTORS.map((s) => {
          const el = document.querySelector(s);
          if (!el) return [s, null];
          const cs = getComputedStyle(el);
          return [
            s,
            Object.fromEntries(PROPS.map((p) => [p, cs.getPropertyValue(p)])),
          ];
        }),
      ),
    { SELECTORS, PROPS },
  );
}
await browser.close();
await import("node:fs").then((fs) =>
  fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 2))
);
```

Diff with `diff pre.json post.json`. A non-empty diff after the shim means the
map is wrong. Fix the map and re-run; never patch component CSS to make the
diff go away.
