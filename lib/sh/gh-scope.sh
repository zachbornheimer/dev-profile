# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: `slug` (origin's owner/name) and `ghr <gh args>`, gh scoped to it. In a fork
# clone gh alone resolves to the parent repo, but origin is where this clone publishes.
# Edit lib/sh/gh-scope.sh: `mise run generate` copies it into lib/.

origin_url="$(git config --get remote.origin.url || :)"
origin_url="${origin_url%/}"
slug="$(sed -En 's#^(https?://([^/@]+@)?|ssh://([^/@]+@)?|[^/@]+@)[^/:]+[:/]([^/]+/[^/]+)$#\4#p' <<<"${origin_url%.git}")"
ghr() { gh "$@" ${slug:+--repo "${slug}"}; }
