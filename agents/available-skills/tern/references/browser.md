# Tern browser blocks

Read this only when the user asked to open or drive a page in Tern. `tern browser --help` is the authority if it disagrees with this page. Checked against tern 0.9.12.

```bash
tern browser '<json>' [--timeout SECONDS]
```

The answer is one JSON object: `{"ok": ...}` or `{"error": {"kind", "message"}}` with exit 1. Exit 124 means `--timeout` ran out.

A driven page stays live at its page size even when it is not on screen. Opening, clicking, or evaluating runs on the live site. Submit only what they asked for.

## Open and list

`{"op":"open","owner":BLOCK,"url":URL}` opens a browser picture-in-picture over `BLOCK` and answers its block.

- `"show": false` parks it: never on screen, still live at its page size.
- `"how": "beside"` or `"below"` docks it in a split by `BLOCK`.
- `"how": "over"` puts it in `BLOCK`'s place until it closes, focused.

`{"op":"blocks"}` lists every browser block of the window, including the user's: `{block, url, title, owner, shown, driven}`.

`state`, `goto`, `nav`, `events`, `close`, `eval`, `capture`, and `input` take any of those blocks. `release` hands one back: its settings reset, the block stays.

Do not `close` a browser block you did not open.

## Read the page

`snapshot` reads the DOM without enabling Tern's dialog policy.

```json
{"op":"snapshot","block":BLOCK,"root":"REF_OR_CSS","depth":3,"nodes":400,"mode":"outline","format":"tree"}
```

`mode` also accepts `"text"`. `format` also accepts `"text"`. The answer has URL and title, a tree or text, an omitted-node count, and iframe addresses. Password values are masked. Element refs stay stable until navigation.

`root`, `depth`, `nodes`, `mode`, and `format` are optional. `nodes` defaults to 400 in the help text.

Headless returns `failed` for native page calls. Other unsupported platforms return `unsupported`. A snapshot still installs the platform browser driver.

## Act

`act` uses a ref from the latest snapshot. A stale ref answers `not_found`.

```json
{"op":"act","block":BLOCK,"action":"click","ref":"REF"}
```

Actions: `click`, `fill` (`text`), `press` (`keys`: a chord or an array, such as `"Meta+a"`), `select` (`text` is the option value), `check`, `uncheck`, `hover`, `scroll` (`dy` defaults to 600). The answer is `{done: true, url, title}`.

`{"op":"pick","block":BLOCK}` waits for the user to click an element. Escape cancels. The answer is `{picked: {ref, selector, tag, role, name, text, value, box}, url, title}` or `{cancelled: true, url, title}`. `act` takes the picked ref. Do not `pick` unless they are at the keyboard and agreed to click.
