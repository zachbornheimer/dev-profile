#!/usr/bin/env bash
# Contract fixture for dotnet target selection: which project or solution a verb
# builds, and the generated-tree exclusion. Usage: dotnet.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

fixture_dotnet_targets() {
	local nested sln deep generated
	nested="$(new_repo dotnet-nested)"
	mkdir -p "${nested}/packages/csharp/src" "${nested}/packages/csharp/obj"
	touch "${nested}/packages/csharp/src/Sdk.csproj" "${nested}/packages/csharp/obj/Gen.csproj"
	run_task "$nested" test || fail "dotnet nested: test failed"
	expect_call "dotnet|${nested}|test packages/csharp/src/Sdk.csproj" "dotnet nested"
	expect_no_call "obj/Gen.csproj" "dotnet nested"

	sln="$(new_repo dotnet-sln)"
	mkdir -p "${sln}/src"
	touch "${sln}/App.sln" "${sln}/src/App.csproj"
	run_task "$sln" build || fail "dotnet sln: build failed"
	expect_call "dotnet|${sln}|build App.sln" "dotnet sln"
	expect_no_call "build src/App.csproj" "dotnet sln"

	deep="$(new_repo dotnet-deep-sln)"
	mkdir -p "${deep}/services/api"
	touch "${deep}/services/api/Api.sln"
	run_task "$deep" build || fail "dotnet deep sln: build failed"
	expect_call "dotnet|${deep}|build services/api/Api.sln" "dotnet deep sln"

	generated="$(new_repo dotnet-generated-only)"
	mkdir -p "${generated}/obj"
	touch "${generated}/obj/Gen.csproj"
	run_task "$generated" build || fail "dotnet generated-only: build should pass"
	expect_output "skip  dotnet build (nothing to build)" "dotnet generated-only"
	expect_no_call "dotnet|" "dotnet generated-only"
}

fixture_dotnet_targets
echo "contract dotnet fixtures ok"
