#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-${CLAUDE_HOOK_INPUT:-}}"

if [[ -z "$INPUT" ]]; then
  exit 0
fi

if echo "$INPUT" | grep -Eiq '(^|[[:space:]])pip([[:space:]]|$)|python[[:space:]]+-m[[:space:]]+pip'; then
  cat <<'EOF'
[bb-cli hook] Prefer uv-based workflows over direct pip usage.
Examples:
  uv run pytest tests/ -v
  uv run bb <command>
  uv pip install -e .
EOF
  exit 0
fi

if echo "$INPUT" | grep -Eiq '(^|[[:space:]])pytest([[:space:]]|$)' && ! echo "$INPUT" | grep -Eiq 'uv[[:space:]]+run[[:space:]]+pytest'; then
  cat <<'EOF'
[bb-cli hook] Prefer running tests through uv.
Example:
  uv run pytest tests/ -v
EOF
  exit 0
fi

exit 0
