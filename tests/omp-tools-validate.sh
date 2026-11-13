#!/usr/bin/env bash
# Standalone entrypoint used by mise run test:omp and doctor.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$root/tests/omp-tools-validate.py"
