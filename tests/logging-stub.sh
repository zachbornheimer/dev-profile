#!/usr/bin/env bash
# Logs "name|dir|args" to STUB_LOG, then exits with STUB_EXIT. Linked under each tool name.
name="${0##*/}"
echo "${name}|${PWD}|$*" >>"$STUB_LOG"
exit "$STUB_EXIT"
