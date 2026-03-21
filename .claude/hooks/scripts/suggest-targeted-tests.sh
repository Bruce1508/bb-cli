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

suggestions=()

if echo "$INPUT" | grep -Eiq 'bb/db\.py|bb/tools/queries\.py|bb/models/content\.py'; then
  suggestions+=("uv run pytest tests/ -v")
fi

if echo "$INPUT" | grep -Eiq 'bb/adapters/blackboard_ultra\.py|selectors/blackboard_ultra\.toml|bb/sync\.py'; then
  suggestions+=("Check scraping-related tests or add a narrow regression test around the changed adapter or selector lane.")
fi

if echo "$INPUT" | grep -Eiq 'bb/cli\.py'; then
  suggestions+=("Sanity-check the affected command flow with uv run bb <command>.")
fi

if echo "$INPUT" | grep -Eiq 'pyproject\.toml'; then
  suggestions+=("Verify package and CLI sanity with uv build and a quick uv run bb <command> check.")
fi

if [[ ${#suggestions[@]} -eq 0 ]]; then
  exit 0
fi

json_array=""
for s in "${suggestions[@]}"; do
  escaped=$(printf '%s' "$s" | sed 's/\\/\\\\/g; s/"/\\"/g')
  if [[ -n "$json_array" ]]; then
    json_array+="\\n- ${escaped}"
  else
    json_array+="- ${escaped}"
  fi
done

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Suggested targeted verification:\n${json_array}"
  },
  "suppressOutput": true
}
EOF

exit 0
