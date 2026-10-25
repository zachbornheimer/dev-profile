#!/usr/bin/env bash
# Contract fixtures for the doctor verb against a repo's own task runners and the
# uv-only rewrite. Usage: runners.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' output=''
. "$(dirname "$0")/world.sh" "$@"

fixture_repo_task_runners() {
	local clean dirty
	clean="$(new_repo runners-clean)"
	printf '[tasks.cmake-build]\nrun = "cmake --build build"\n[tasks.smoke]\nrun = "uv run scripts/smoke.py"\n[tasks."conformance:python"]\nrun = "mise run conformance:_run python"\n[tasks.pytest]\nrun = "uv run pytest -q"\n' >"${clean}/mise.toml"
	run_task "$clean" doctor || fail "runners clean: doctor should pass"

	dirty="$(new_repo runners-dirty)"
	printf '[tasks.build]\nrun = "make build"\n[tasks.smoke]\nrun = "PYTHONPATH=src python3 -m pip install -e ."\n[tasks.report]\nrun = "python3 scripts/report.py"\n' >"${dirty}/mise.toml"
	mkdir -p "${dirty}/mise-tasks"
	printf '#!/usr/bin/env bash\npip install requests\n' >"${dirty}/mise-tasks/deps"
	chmod +x "${dirty}/mise-tasks/deps"
	if run_task "$dirty" doctor; then fail "runners dirty: doctor should fail"; fi
	expect_output "no-make: task 'build' invokes make" "runners dirty"
	expect_output "uv-only: task 'smoke' runs python" "runners dirty"
	expect_output "uv-only: task 'deps' runs python" "runners dirty"
	expect_output "uv-only: task 'report' runs python" "runners dirty"
}

fixture_uv_instead_of_python_in_tasks() {
	local file="${work}/python-fix.toml" want="${work}/python-fix.want"
	cat >"$file" <<'EOF'
[tasks.a]
run = "python3 scripts/a.py --flag"
[tasks.b]
run = "PYTHONPATH=src python scripts/b.py"
[tasks.c]
run = ["uv run tools/c.py", "uv run --script d.py && python3 e.py"]
[tasks.keep]
run = ["python3 -c 'print(1)'", "uv run pytest -q", "python3 -m http.server", "mise run conformance:_run python"]
[tools]
python = "3.12"
python="3.12"
"python" = "3.12"
python3 = "3.12"
[tasks.multi]
run = """
python script.py
"""
EOF
	cat >"$want" <<'EOF'
[tasks.a]
run = "uv run scripts/a.py --flag"
[tasks.b]
run = "PYTHONPATH=src uv run scripts/b.py"
[tasks.c]
run = ["uv run tools/c.py", "uv run --script d.py && uv run e.py"]
[tasks.keep]
run = ["uv run python3 -c 'print(1)'", "uv run pytest -q", "uv run python3 -m http.server", "mise run conformance:_run python"]
[tools]
python = "3.12"
python="3.12"
"python" = "3.12"
python3 = "3.12"
[tasks.multi]
run = """
uv run script.py
"""
EOF
	dev-profile-uv-instead-of-python-in-tasks "$file"
	diff -u "$want" "$file" >"$output" || fail "uv-instead-of-python-in-tasks: unexpected rewrite"
}

fixture_repo_task_runners
fixture_uv_instead_of_python_in_tasks
echo "contract runner fixtures ok"
