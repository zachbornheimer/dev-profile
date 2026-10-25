# Host inventory

Answer these from the target repo before copying CSS. Do not assume a
named app. The answers pick the file and the layer edit. They are not extra
procedure.

1. **Who emits the first `@layer` order list?** One authored file. If a
   published package exports a copy and the app also has a local copy, patch
   the package source (never `build/` only) and make the app import the
   package. Two lists drift.

2. **Does anything wrap customer/brand CSS in a named layer at ingest?** If
   yes, delete the unlayered fallback `:root` in `brand.example.css` and do
   not wrap the file again. Nested `whitelabel.whitelabel` is a silent miss.

3. **Must unlayered vendor CSS beat the app?** Yes → `contract.gen.legacy.css`
   and source order. No → `contract.gen.css` plus a `contract` slot in the
   host list (`…, contract, kit, whitelabel, app`).

4. **Does a published kit pin have to move with this?** If contract CSS loads
   before the kit's layer-order lists `contract`, defaults append after `app`.
   Bump the pin in the same change that first loads `contract.gen.css`.

5. **Tailwind v4 `@theme`?** Identity-named keys (`--color-ink` and friends)
   go in `@theme reference`. See `framework-adapters.md`.

## Illustrations (not a checklist for those repos)

A tokens package that publishes `layer-order.css`: insert `contract` in the
authored source; the build is a copy. Consumers that duplicate the list
locally should drop the duplicate import.

A form runtime that wraps `cssVariables` in `@layer whitelabel`: install the
layered gen file, strip a pasted `@layer` / `:root` before wrap, delete the
brand.example fallback. Do not load contract CSS until question 4 is yes.
