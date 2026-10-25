# Why each rule exists

Sources behind the skill's rules, so future edits keep the mechanism intact.
Each rule names the evidence; check links still say what they said before changing
the rule.

## The maker must not grade the work

- Adversarial review is a maker-checker control: the agent (or person) that
  produced a change never certifies it. Banking has run this control for decades;
  Clark-Wilson formalized it; NIST AC-5 codifies separation of duties.
  <https://www.augmentcode.com/guides/adversarial-code-review>
- LLMs recognize their own output and prefer it (self-preference bias), the
  mechanism is familiarity, and the leniency is worst exactly on incorrect code.
  Prompting does not repair it: masking the judge's ability to recognize its own
  output reduces the bias, meaning recognition drives it more than instructions.
  Same-session review compounds it: the assumptions that shaped the work shape
  the review. <https://arxiv.org/html/2404.13076v1>
- Fresh context is the fix: the reviewer sees only the diff/material and the
  criteria, never the reasoning that produced it. That is why the attack manifest
  is the adversary's entire input — and why the outcome is quoted verbatim from
  the user's request rather than paraphrased by the parent: the maker must not
  write the success criterion its own work is judged against.
- Cross-family reviewers catch what the maker's family misses: same-family models
  share correlated blind spots and "confidently agree in the same places"
  (libfuse review campaign, which produced published CVEs). The same campaign is
  the evidence for the reproduction rule: 80+ agents, including dedicated
  adversarial reviewers, unanimously endorsed a non-existent vulnerability, and
  a single empirical test killed it — reviewer agreement by reading is not
  verification of behavior.
  <https://arxiv.org/html/2604.19049v1>

## Independence and corroboration

- Multiple independent verifier perspectives produce an aggregate signal stronger
  than any single pass: multi-agent verification with aspect verifiers and
  best-of-n selection (MAV, Aspect Verifiers, BoN-MAV).
  <https://arxiv.org/html/2502.20379v1>
- Corroboration promotion (two-plus adversaries → one level up, from the higher
  base) converts that aggregate into a decision rule. The cap at major and the
  fragile-assumption precedence were added after the skill's own first run: the
  uncapped rule promoted three corroborated majors into blockers and inflated a
  CONCERNS-shaped review into BLOCK — corroborated findings must carry their own
  blocker-severity evidence to block.
- Mandatory findings with a fragile-assumption out, severity promotion, and the
  BLOCK/CONCERNS/CLEAN verdict scheme adapted from the adversarial-reviewer
  skill pattern: <https://github.com/alirezarezvani/claude-skills/blob/main/engineering-team/skills/adversarial-reviewer/SKILL.md>
- Caution: SWR-Bench found multi-agent review can underperform a simple
  reviewer baseline — architecture alone does not guarantee better review;
  verifier prompts and scoped context determine what gets caught. That is why
  this skill pins the work-order contract and the manifest, not just the fan-out.
  <https://arxiv.org/html/2509.01494v1>

## Findings discipline, verdicts, rounds

- Findings as violation → impact → smallest fix → regression test turns critique
  from "reject" into "here is how to fix it".
  <https://asdlc.io/patterns/adversarial-code-review/>
- Verdict anchors keep BLOCK honest; CONCERNS covers any major (the original
  "two or more majors" left the most common shape — exactly one major — with no
  verdict; caught by the skill's own first adversarial review).
- Bounded rounds: practitioner consensus is that adversarial review "will always
  find something," so bound rounds explicitly and decide when to stop rather than
  chase nits indefinitely. Budget routing by blast radius (security-sensitive
  paths and low-oversight agent output first; skip trivial diffs) comes from the
  maker-checker guide above; the quick/full profiles mirror the sibling
  security-audit skill's quick/standard/deep scheme.

## Plans and decisions: pre-mortem and assumption attack

- Klein's pre-mortem: prospective hindsight — assume the project failed, then
  generate the failure story. Imagined failure surfaces risks that checklists
  miss. <https://www.theuncertaintyproject.org/tools/pre-mortem>
- Macro-level red teaming for designs and systems: scrutinize the architecture
  for failure modes, challenge assumptions about how people actually behave with
  the system, and check observability and control are built in from the start
  rather than retrofitted. <https://arxiv.org/html/2507.05538v1>

## The lavish report

- The report opens as a lavish artifact because the review loop does not end at
  the verdict: the user annotates the artifact in the browser and sends feedback
  back. Zysys Admin design system (not DaisyUI) is the standing house rule for
  every lavish HTML artifact: `~/.agents/AGENTS.md` and
  `~/.agents/lavish-design-system/AGENT.md`, including its precedence carve-outs
  (a look named in the turn, or a mocked app's own system, wins).
