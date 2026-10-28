# aubx-skills Global Configuration

## Status: ✓ Configured Correctly

`aubx-skills` is configured to write ONLY to `~/.agents/available-skills/` on this machine.

## Configuration Details

- **Binary Location**: `~/.local/bin/aubx-skills` → `~/.agents/bin/aubx-skills`
- **Skills Directory**: `~/.agents/available-skills/`
- **Lock File**: `~/.agents/available-skills/.skill-lock.json`
- **Configuration Method**: Default (no environment variable override needed)

## How It Works

`aubx-skills` is a wrapper around `aubx skills` (Vercel's skills CLI) that confines all writes to a single location:

1. **Isolated Installation**: Runs the upstream installer in a throwaway HOME directory
2. **Controlled Copy**: Extracts only the skill folders to `~/.agents/available-skills/`
3. **Symlink Creation**: Creates symlinks in various agent skill roots pointing to the central location
4. **Atomic Updates**: Uses file locking to prevent concurrent modification issues

## Upstream Skills Are Installed, Not Committed

- `.skill-lock.json` is committed. Every `github` entry in it is an upstream skill.
- `available-skills/.gitignore` is generated from that record by every `add`, `update`, `remove` and `sync`, so upstream skill folders are never committed. Skills written here (no `github` entry) stay tracked.
- `aubx-skills sync` installs each recorded upstream skill whose folder is missing, one installer run per source.
- After a pull (merge or rebase) or checkout in the dev-profile checkout, the global git hook `hook.agents-skills-sync` (`hooks/skills-sync-on-pull`) runs `sync` in the background; its log is `~/.local/state/dev-profile/skills-sync.log`. `mise run setup` runs `sync` on a fresh machine.
- A skill copied from upstream and then edited by hand (for example `lavish`) has no record entry and is committed, so `update` never overwrites the edits.
- `tests/skills-sync-fixture.sh` covers sync, the ignore list and the hook with a stub installer.

## Environment Variables

- `AGENTS_HOME`: Defaults to `$HOME/.agents` (no override needed)
- `AUBX_AGENT`: Defaults to `codex` (agent type for installation)
- `AUBX`: Path to real aubx binary (auto-detected from PATH)

## Verified Configuration

```bash
# Verification run on 2026-10-22
$ export HOME=/Users/zbornheimer
$ aubx-skills --help | grep AGENTS_HOME
env: AGENTS_HOME=/Users/zbornheimer/.agents

# Current state
Skills directory: 182 skills installed
Lock file: Present and valid
PATH: ~/.local/bin is configured in .zprofile
```

## Usage

### Add a skill globally

```bash
aubx-skills add vercel-labs/agent-skills --skill deploy-to-vercel -g -y
```

### Update all global skills

```bash
aubx-skills update -g
```

### Update specific skills

```bash
aubx-skills update -g skill-name
```

### List installed skills

```bash
aubx-skills list
```

### Remove a skill

```bash
aubx-skills remove skill-name -g -y
```

### Dry run (test without changes)

```bash
aubx-skills --dry-run add <package> --skill <skill-name> -g
```

## Directory Structure

```
~/.agents/
├── available-skills/           # PRIMARY WRITE LOCATION (all skills here)
│   ├── .skill-lock.json       # Installation registry
│   ├── skill-name-1/
│   ├── skill-name-2/
│   └── ...
└── bin/
    ├── aubx-skills*           # Main wrapper script
    ├── aubx*                  # aube dlx wrapper
    └── ...

~/.local/bin/
├── aubx-skills -> ~/.agents/bin/aubx-skills
├── aubx -> ~/.agents/bin/aubx
└── ...

~/.claude/skills/              # Symlinks to available-skills (created by aubx-skills)
~/.codex/skills/               # Symlinks to available-skills
~/.grok/skills/                # Symlinks to available-skills
~/.cursor/skills/              # Symlinks to available-skills
```

## Guarantees

1. **Single Write Location**: All skill files go to `~/.agents/available-skills/` only
2. **No Scattered Installs**: Other agent directories only contain symlinks
3. **Atomic Operations**: File locking prevents concurrent modification corruption
4. **Audit Trail**: Any write outside `available-skills` causes exit 3 (tripwire)

## Troubleshooting

### aubx-skills not found

```bash
# Check symlink
ls -la ~/.local/bin/aubx-skills

# Verify PATH
echo $PATH | grep -o "[^:]*\.local/bin[^:]*"

# Manual add to PATH if needed (add to ~/.zprofile)
export PATH="$HOME/.local/bin:$PATH"
```

### Skills not appearing in agent

1. Check if skill is in available-skills: `ls ~/.agents/available-skills/`
2. Check if symlink exists: `ls -la ~/.claude/skills/skill-name`
3. Verify agent configuration loads from correct skills directory

### Lock file issues

```bash
# If stale lock exists (>120 seconds old)
rm -rf ~/.agents/available-skills/.skill-lock.lock

# Verify lock file is valid JSON
jq . ~/.agents/available-skills/.skill-lock.json
```

## Notes

- Installation runs under a confined HOME to prevent writes outside `available-skills/`
- Package manager state (aube cache) is shared: `~/.cache/aube`, `~/.local/share/aube`
- Lock timeout: 120 seconds (after which lock is considered abandoned)
- Lock wait: Up to 60 seconds (600 attempts × 0.05s)

## Last Verified

- Date: 2026-10-22
- Version: aubx-skills 2026.10.22
- Skills Count: 182
- Status: Working correctly
