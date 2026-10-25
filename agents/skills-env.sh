#!/bin/bash
# Skills CLI Environment Configuration
# Source this file or add these exports to your shell configuration (~/.zshrc, ~/.bashrc)
#
# Usage:
#   source ~/.agents/skills-env.sh

# Force Skills CLI to use ~/.agents/available-skills exclusively
export SKILLS_DIR="$HOME/.agents/available-skills"
export SKILLS_GLOBAL_PATH="$HOME/.agents/available-skills"

# Prevent aubx from using default skill locations
export SKILLS_DISABLE_DEFAULT_PATHS=true

echo "✓ Skills CLI configured to use: $SKILLS_DIR"
