# bb-cli — Blackboard for your terminal

[![CI](https://github.com/Bruce1508/bb-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce1508/bb-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/blackboard-cli.svg)](https://pypi.org/project/blackboard-cli/)
[![Python](https://img.shields.io/pypi/pyversions/blackboard-cli.svg)](https://pypi.org/project/blackboard-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Stop opening Blackboard.** `bb` syncs your deadlines, grades, and announcements locally — then lets you ask an AI about them in plain English.

```
$ bb chat "what do I have due this week?"
🤖 You have 3 deadlines this week:
   • BTP200 Lab 4 — tomorrow at 11:59 PM
   • INT222 Assignment 2 — Friday at 11:59 PM
   • OPS445 Quiz 3 — Friday at 11:59 PM
```

---

## Install

```bash
pip install blackboard-cli
bb setup-browsers   # install Chromium for Blackboard scraping (one-time)
```

> **Requires Python 3.11+** — check with `python3 --version`.
> Don't have it? Download from [python.org/downloads](https://www.python.org/downloads/) (macOS/Windows)
> or run `brew install python@3.11` (macOS with Homebrew).

---

## Quick Start

```bash
bb init    # first-time setup — LMS URL, notification preferences, AI provider
bb auth    # log in to Blackboard (opens a browser window)
bb sync    # sync deadlines, grades, and announcements
bb due     # show what's coming up
bb chat    # open the AI assistant
```

---

## Commands

| Command | Description |
|---------|-------------|
| `bb init` | First-time setup wizard |
| `bb auth` | Log in to Blackboard (headed browser) |
| `bb sync` | Sync all data from Blackboard |
| `bb due` | Upcoming deadlines table (`--days 14`, `--course BTP200`) |
| `bb grades` | Grade table (`--course BTP200`) |
| `bb ann` | Recent announcements (`--unread`) |
| `bb status` | Session health, last sync, DB stats |
| `bb chat` | AI assistant — ask anything about your courses |
| `bb <COURSE>` | Browse course content (e.g. `bb BTP200`) |
| `bb download <COURSE>` | Download course files (`--all`, `--type pdf`) |
| `bb open <COURSE> <item>` | Open a course item in your browser |
| `bb mcp-server` | Start MCP server for Claude Desktop |
| `bb auto-setup` | Install/remove OS-native auto-sync |
| `bb setup-browsers` | Install Chromium for scraping |

---

## `bb chat` — Ask your AI anything

`bb chat` is an interactive AI assistant that knows your real Blackboard data. It never makes up grades or deadlines — it queries your local database.

```bash
$ bb chat
🎓 bb chat — ask me anything about your courses
Type /help for commands, /exit to quit

You: do I have anything due tomorrow?
🤖 Yes — BTP200 Lab 4 is due tomorrow at 11:59 PM (worth 5%).

You: generate a study plan for my INT222 exam on Friday
🤖 Here's a 3-day study plan for INT222...

You: /sync
🔄 Syncing...
✓ Synced 2 new deadlines, 1 new grade.
```

**AI providers** (auto-detected, in priority order):
1. **Ollama** (free, private, offline) — install from [ollama.com](https://ollama.com), then `ollama pull qwen3:30b-a3b`
2. **Claude API** — set `[ai] provider = "claude"` and `api_key = "sk-..."` in `~/.bb/config.toml`
3. **OpenAI API** — set `[ai] provider = "openai"` and `api_key = "sk-..."` in `~/.bb/config.toml`

---

## Claude Desktop Integration (MCP)

Connect `bb chat`'s tools directly to Claude Desktop — ask Claude about your deadlines and grades without leaving your AI chat.

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bb-cli": {
      "command": "bb",
      "args": ["mcp-server"]
    }
  }
}
```

Claude Desktop will now have access to all 13 bb-cli tools: deadlines, grades, announcements, course content, and more.

---

## Configuration

`~/.bb/config.toml` is created by `bb init`. Example:

```toml
[lms]
url = "https://your-school.blackboard.com"
adapter = "blackboard_ultra"

[ai]
provider = "ollama"          # ollama | claude | openai
model = "qwen3:30b-a3b"         # for Ollama

[notifications]
providers = ["terminal"]     # terminal | ntfy | telegram | discord
```

---

## Notifications

`bb` can notify you when new deadlines or grades appear:

- **Terminal** — macOS/Linux native notifications (no setup)
- **ntfy** — push to any device via [ntfy.sh](https://ntfy.sh) (no account needed)
- **Telegram** — configure bot token in `~/.bb/config.toml`
- **Discord** — configure webhook URL in `~/.bb/config.toml`

---

## Auto-sync

Set up automatic syncing so your data stays fresh:

```bash
bb auto-setup           # installs launchd (macOS) or crontab (Linux)
bb auto-setup --disable # removes the scheduler
```

Default: syncs every 4 hours silently in the background.

---

## Development

```bash
git clone https://github.com/Bruce1508/bb-cli
cd bb-cli
uv sync --all-groups    # install deps
uv run pytest tests/    # run tests
uv run bb --help        # run CLI
```

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/)

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built for Seneca Polytechnic students. Works with any Blackboard Ultra institution.*
