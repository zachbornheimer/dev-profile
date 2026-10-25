# Inventory queries

Run from the app root. Exclude `node_modules`, `dist`, `vendor`, `build`.

```sh
# every declared custom property, with file:line
grep -rnoE -- "--[a-z0-9-]+\s*:" --include=*.css --include=*.scss --include=*.tsx --include=*.jsx --include=*.vue --include=*.svelte . \
  | grep -v node_modules | sort -u

# reference counts per property
grep -rhoE -- "var\(--[a-z0-9-]+" --include=*.css --include=*.scss --include=*.tsx --include=*.jsx . \
  | grep -v node_modules | sed 's/var(//' | sort | uniq -c | sort -rn

# framework fingerprints
grep -rln "@theme" --include=*.css . | head            # Tailwind v4
ls tailwind.config.* 2>/dev/null                         # Tailwind v3
grep -rln -- "--bs-" --include=*.css . | head            # Bootstrap
grep -rln "styled\.\|css\`" --include=*.tsx --include=*.jsx . | head   # CSS-in-JS

# layers
grep -rn "@layer" --include=*.css --include=*.html . | grep -v node_modules
# unlayered third-party sheets: list every <link rel=stylesheet> and @import,
# then check each for a top-level @layer statement
```

Record the browser load order from the rendered HTML, not from source, when
a build tool or CMS assembles the page.
