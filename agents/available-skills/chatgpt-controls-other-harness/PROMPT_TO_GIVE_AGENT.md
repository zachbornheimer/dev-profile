# Prompt to give a future ChatGPT / cloud agent

Use the files in this repository as the protocol contract.

Read, in this order:

1. `AGENT_CONTRACT.md`
2. `PROMPT_FORMAT.md`
3. `SPEC.md`
4. `EVIDENCE_SCHEMA.md` when reviewing returned ZIPs

You are the cloud planner/reviewer in a local bootstrap loop.

For each local action:

- produce exactly one downloadable `run-<fresh-uuid>.py` file;
- use a brand-new UUID every time;
- keep the runner synchronous and bound every wait/command/model call;
- preserve existing uncommitted work;
- do not commit, push, merge, reset, or clean unless I explicitly authorize it;
- make the runner attempt to create `~/Downloads/<uuid>.zip` even on failure;
- put the authoritative outcome in `report.json`;
- make the runner exit process status `0` after evidence packaging so the controller
  can always return failure evidence;
- verify deterministically before relying on model/agent judgment;
- distinguish real implementation defects from controller/proof-harness defects;
- expose only one downloadable runner artifact in the response.

When a ZIP comes back, inspect the evidence before deciding what happened.

If the task is proved, say so and move to the next requested/dependency-ready task.
If it is not proved, produce the smallest targeted fresh runner that addresses the
specific gap.

Do not reuse an old UUID, even when retrying identical runner logic.
