#!/usr/bin/env bash
# ZYS-10118 mini A/B: same prompt, same model, memory backend archive (default) vs off. --no-session: nothing is captured.
cd /home/user/Developer/Personal || exit 1
out=/tmp/z10118/ab
mkdir -p "$out"
Q=(
	"From our earlier work: what rule decides whether an omp worktree counts as owned by the current session? One sentence."
	"From our earlier work: what cosine similarity threshold does archive fact consolidation use to link facts? One sentence."
	"From our earlier work: why does omp exit 1 on a freshly cloned repository in a Relay sandbox? One sentence."
	"From our earlier work: how many requests per hour does the shared linear-personal MCP key allow? One sentence."
	"From our earlier work: how many wake turns did one omp turn get from stale wait path_changed arms? One sentence."
)
i=0
for q in "${Q[@]}"; do
	i=$((i + 1))
	for arm in on off; do
		cfg=()
		[ "$arm" = off ] && cfg=(--config /tmp/z10118/off.yml)
		s=$(date +%s%N)
		timeout 120 omp -p --no-session --no-tools "${cfg[@]}" "$q" >"$out/q$i.$arm.txt" 2>"$out/q$i.$arm.err"
		e=$(date +%s%N)
		echo "q$i $arm $(((e - s) / 1000000))ms" >>"$out/times.txt"
	done
done
echo done >"$out/DONE"
