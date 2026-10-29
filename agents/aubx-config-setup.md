# aubx Skills Configuration Setup

aubx is **already configured** to write exclusively to `~/.agents/available-skills` via the `aubx-skills` wrapper.

## How It Works

The `~/.agents/bin/aubx-skills` wrapper (version 2026.10.22) ensures all skill operations write only to `~/.agents/available-skills`:

1. Runs the installer in an isolated throwaway `$HOME`
2. Copies results only to `$AVAILABLE_DIR` (`~/.agents/available-skills`)
3. Audits all filesystem changes before/after the install
4. **Exits with status 3** if any write occurs outside `available-skills`
5. Automatically removes harness-specific links the installer creates

## Configuration Files (Additional Safeguards)

Created as fallback configuration if the native `aubx` is ever called directly:

1. **`~/.skills-cli/config.json`** - Primary Skills CLI configuration
2. **`~/.skills/config.json`** - Alternative configuration location

Both files point all skill targets to `/Users/zbornheimer/.agents/available-skills` and disable default paths.

## Environment Variables (Optional)

Add to your shell configuration (`~/.zshrc`):

```bash
# Force Skills CLI to use ~/.agents/available-skills exclusively
export SKILLS_DIR="$HOME/.agents/available-skills"
export SKILLS_GLOBAL_PATH="$HOME/.agents/available-skills"
```

## Verification Commands

The wrapper is already in use. Run these commands to verify:

```bash
# Verify the wrapper is on PATH (should show ~/.agents/bin/aubx-skills or ~/.local/bin/aubx-skills)
which aubx-skills

# Show wrapper version
aubx-skills --version

# List installed skills (reads from ~/.agents/available-skills)
aubx-skills list

# Test installing a skill to verify it goes to the correct location
aubx skills add https://secluded.site --skill example-skill --yes --global

# Verify the skill was installed to the correct location
ls -la ~/.agents/available-skills/example-skill

# Check that skills are NOT being written to default locations
ls -la ~/.claude/skills/ 2>/dev/null || echo "✓ No skills in ~/.claude/skills/"
ls -la ~/.agents/skills/ 2>/dev/null || echo "✓ No skills in ~/.agents/skills/"
```

## Current Skills Inventory

Your `~/.agents/available-skills` directory already contains:

- 1,618 files across multiple skills
- Major skills: ai-history-ui, organize-files, cleaning-git-branches-and-worktrees, learnings, and others

## Next Steps

1. Source the environment variables (if you added them to ~/.zshrc):

   ```bash
   source ~/.zshrc
   ```

2. Verify the configuration:

   ```bash
   aubx skills config
   ```

3. Test installing a skill to confirm it writes to the correct location

## How the Wrapper Prevents Writes to Other Locations

The `aubx-skills` wrapper **mechanically enforces** that skills write only to `~/.agents/available-skills`:

1. **Isolation**: Installer runs under a scratch `$HOME` (deleted on exit)
2. **Auditing**: Compares filesystem state before/after the install
3. **Link removal**: Automatically removes any links to harness directories:
   - `~/.claude/skills/`
   - `~/.codex/skills/`
   - `~/.grok/skills/`
   - `~/.cursor/skills/`
   - `~/.config/opencode/skills/`
   - `~/.gemini/skills/`
4. **Tripwire**: If anything is written outside `available-skills`, exit status 3

All skills operations (add, update, remove) via `aubx-skills` target `~/.agents/available-skills` exclusively.

## Usage

Always use `aubx-skills` (not raw `aubx skills`):

```bash
# Install a skill
aubx-skills add vercel-labs/agent-skills --skill example-skill

# Update all global skills
aubx-skills update

# Remove a skill
aubx-skills remove example-skill
```
