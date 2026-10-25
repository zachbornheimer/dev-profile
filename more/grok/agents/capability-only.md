---
name: capability-only
description: Default Grok session with the native file, shell, search and todo tools removed; the capability MCP server provides read, write, edit, grep, glob, bash and todo instead.
disallowedTools:
  - run_terminal_cmd
  - read_file
  - write
  - search_replace
  - grep
  - list_dir
  - web_search
  - todo_write
---
