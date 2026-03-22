#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 0 && -n "${1:-}" ]]; then
  INPUT="$1"
elif [[ -n "${CLAUDE_HOOK_INPUT:-}" ]]; then
  INPUT="$CLAUDE_HOOK_INPUT"
else
  INPUT="$(cat)"
fi

if [[ -z "$INPUT" ]]; then
  exit 0
fi

MESSAGE=""
ADDITIONAL=""

if echo "$INPUT" | grep -Eiq '"command"[[:space:]]*:[[:space:]]*"[^"]*python[[:space:]]+-m[[:space:]]+pip'; then
  MESSAGE="Prefer uv-based workflows over python -m pip."
  ADDITIONAL="This repository uses uv-based install and execution flows. Prefer commands like 'uv pip install -e .' or 'uv run ...' instead of python -m pip."
elif echo "$INPUT" | grep -Eiq '"command"[[:space:]]*:[[:space:]]*"[^"]*(^|[^[:alnum:]_])pip([[:space:]]|$)'; then
  MESSAGE="Prefer uv-based workflows over direct pip usage."
  ADDITIONAL="This repository uses uv-based install and execution flows. Prefer commands like 'uv pip install -e .' or 'uv run ...' instead of direct pip usage."
elif echo "$INPUT" | grep -Eiq '"command"[[:space:]]*:[[:space:]]*"[^"]*(^|[^[:alnum:]_])pytest([[:space:]]|$)' && ! echo "$INPUT" | grep -Eiq 'uv[[:space:]]+run[[:space:]]+pytest'; then
  MESSAGE="Prefer running tests through uv."
  ADDITIONAL="Repository convention is to run tests through uv, for example 'uv run pytest tests/ -v'."
fi

if [[ -z "$MESSAGE" ]]; then
  exit 0
fi

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "$MESSAGE",
    "additionalContext": "$ADDITIONAL"
  }
}
EOF

exit 0
