# Improvement: provision the supported Semgrep PR reviewer

## Intent

Install one real reviewer through the maintained adopted profile for ZYS-11242,
without introducing another harness or persisted credential.

## Contract and ownership

- `profile/mise.toml` already includes `languages/python/tools.toml`; that fragment
  remains the single owner of the `pypi:semgrep` pin (one declaration).
- Semgrep 1.187.0 uses a private Python 3.13 runtime through mise's `python`
  tool option. It does not replace the user's default Python.
- `mise.toml` adds one `test:review-pr` task for the installed
  `~/.omp/agent/tools/review_pr/review_pr.test.ts`, following the existing
  installed-tool task convention. The parent owns the tool implementation.
- README documents installation and the task. No new extraction, mutation path,
  credential, OCR dependency, or replacement for the Foxguard push gate is added.

## Evidence

Installed from this branch's profile with:

```sh
MISE_GLOBAL_CONFIG_FILE="$PWD/profile/mise.toml" mise install pypi:semgrep
mise exec pypi:semgrep -- semgrep --version
mise reshim
```

mise installed Semgrep 1.187.0 and its private CPython 3.13.18 runtime. The exact
version command printed `1.187.0` with exit 0; the shell resolves `semgrep` to
`~/.local/share/mise/shims/semgrep`. This proves local installation and CLI
startup, not a fresh Relay adoption or a completed GitHub review. Those public
workflow proofs belong to the parent integration pass.

`mise run ci` passed its lint stage, then doctor reported a held-renderer
`cd latency fixture` failure. The complete command exceeded its 300-second
deadline; the full repository gate is NOT PROVEN. The parent independently ran
the installed reviewer suite and reported 54 passing tests.
