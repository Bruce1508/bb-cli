#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-${CLAUDE_HOOK_INPUT:-}}"

if [[ -z "$INPUT" ]]; then
  exit 0
fi

suggestions=()

if echo "$INPUT" | grep -Eq 'bb/db.py|bb/tools/queries.py|bb/models/content.py'; then
  suggestions+=("uv run pytest tests/ -v")
fi

if echo "$INPUT" | grep -Eq 'bb/adapters/blackboard_ultra.py|selectors/blackboard_ultra.toml|bb/sync.py'; then
  suggestions+=("Check scraping-related tests or fixtures first; if absent, add a narrow regression test around the changed lane.")
fi

if echo "$INPUT" | grep -Eq 'bb/cli.py'; then
  suggestions+=("Run the most relevant CLI-focused tests and sanity-check the affected command flow with uv run bb <command>.")
fi

if echo "$INPUT" | grep -Eq 'pyproject.toml'; then
  suggestions+=("Verify package and CLI sanity: uv build && uv run bb version")
fi

if [[ ${#suggestions[@]} -eq 0 ]]; then
  exit 0
fi

echo "[bb-cli hook] Suggested targeted checks:"
for s in "${suggestions[@]}"; do
  echo "- $s"
done

exit 0
