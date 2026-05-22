"""Chat engine for bb chat — Ollama provider, tool dispatch, REPL."""
from __future__ import annotations

import inspect
import json
import logging
import types
import typing
from pathlib import Path
from typing import TYPE_CHECKING

import bb.config as _config_module
from bb.tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)

_HISTORY_MAX = 50  # max messages persisted (user+assistant pairs only)

if TYPE_CHECKING:
    from rich.console import Console

    from bb.config import BBConfig

_TYPE_MAP: dict = {int: "integer", str: "string", bool: "boolean", float: "number"}
MAX_TOOL_ROUNDS = 5


# ---------------------------------------------------------------------------
# Tool schema building
# ---------------------------------------------------------------------------

def _json_type(annotation: object) -> str:
    """Convert a Python type annotation to a JSON Schema type string."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if args:
            return _json_type(args[0])
    # Python 3.10+ X | None syntax produces types.UnionType
    if isinstance(annotation, types.UnionType):
        args = [a for a in annotation.__args__ if a is not type(None)]
        if args:
            return _json_type(args[0])
    return _TYPE_MAP.get(annotation, "string")  # type: ignore[arg-type]


def _tool_description(fn: object) -> str:
    """Extract description from docstring — everything before 'Args:' section."""
    doc = inspect.getdoc(fn) or ""
    lines: list[str] = []
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith(("Args:", "Returns:", "Raises:")):
            break
        lines.append(stripped)
    return " ".join(ln for ln in lines if ln).strip()


def _build_props(fn: object) -> tuple[dict, list[str]]:
    """Return (properties_dict, required_list) from function signature."""
    sig = inspect.signature(fn)  # type: ignore[arg-type]
    props: dict = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            ann = str
        props[pname] = {"type": _json_type(ann)}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    return props, required


def build_ollama_tools() -> list[dict]:
    """Build Ollama-format tool schemas from TOOL_REGISTRY."""
    tools = []
    for name, fn in TOOL_REGISTRY.items():
        props, required = _build_props(fn)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": _tool_description(fn),
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return tools


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, args: dict) -> str:
    """Execute a tool from TOOL_REGISTRY. Returns JSON string result."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**args)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool call indicator labels
# ---------------------------------------------------------------------------

_TOOL_LABELS: dict[str, str] = {
    "get_upcoming_deadlines": "Checking deadlines",
    "get_grades": "Checking grades",
    "get_announcements": "Checking announcements",
    "get_course_list": "Listing courses",
    "get_sync_status": "Checking sync status",
    "get_course_content": "Reading course content",
    "search_content": "Searching content",
    "list_downloaded_files": "Listing downloaded files",
    "read_file_content": "Reading file",
    "summarize_content": "Reading file for summary",
    "generate_study_plan": "Gathering study materials",
    "extract_key_concepts": "Collecting course materials",
    "estimate_study_time": "Analyzing grades and deadlines",
}


def _strip_think(text: str) -> str:
    """Remove thinking blocks that Qwen3 and similar models emit.

    Handles two cases:
    - Full <think>...</think> block in content
    - Orphaned </think> (Ollama strips the opening tag but leaves the body + closing tag)
    """
    import re
    # Full block case
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Orphaned closing tag — everything before </think> is thinking noise
    if "</think>" in text:
        text = text.split("</think>", 1)[-1]
    return text.strip()


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"Running {name}")


# ---------------------------------------------------------------------------
# ChatEngine
# ---------------------------------------------------------------------------

class ChatEngine:
    """Manages conversation history and routes turns to the Ollama provider."""

    def __init__(self, cfg: "BBConfig") -> None:  # noqa: F821
        self._cfg = cfg
        self.provider, self.model = self._detect_provider()
        self._msgs: list[dict] = []
        self._reset_history()

    def _history_path(self) -> Path:
        return _config_module.BB_DIR / "chat_history.json"

    def _load_history(self) -> list[dict]:
        """Load persisted user+assistant messages. Returns [] on any failure."""
        path = self._history_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.debug("chat_history: could not load: %s", exc)
        return []

    def _save_history(self, user_content: str, assistant_content: str) -> None:
        """Append a user+assistant pair to the history file (atomic write, FIFO trim)."""
        history = self._load_history()
        history.append({"role": "user", "content": user_content})
        history.append({"role": "assistant", "content": assistant_content})
        # Trim oldest messages first to keep at most _HISTORY_MAX entries
        if len(history) > _HISTORY_MAX:
            history = history[-_HISTORY_MAX:]
        path = self._history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.rename(path)
        except Exception as exc:
            logger.debug("chat_history: could not save: %s", exc)

    def _reset_history(self) -> None:
        from bb.ai.prompts import SYSTEM_PROMPT
        self._msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Inject persisted history after system prompt
        self._msgs.extend(self._load_history())

    def clear_history(self) -> None:
        """Reset conversation history to system prompt only and wipe the history file."""
        from bb.ai.prompts import SYSTEM_PROMPT
        self._msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        path = self._history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text("[]", encoding="utf-8")
            tmp.rename(path)
        except Exception as exc:
            logger.debug("chat_history: could not clear: %s", exc)

    def _detect_provider(self) -> tuple[str, str]:
        """Auto-detect best available Ollama model. Returns (provider, model)."""
        from bb.ai.providers.ollama import get_model, is_available

        if not is_available():
            return "none", ""

        preferred = self._cfg.ai.model or ""
        model = get_model(preferred)
        if model:
            return "ollama", model

        return "none", ""

    def get_provider_display(self) -> str:
        if self.provider == "none":
            return "none"
        think_tag = " • think=on" if self._cfg.ai.think else ""
        return f"{self.provider} • {self.model}{think_tag}"

    def process_turn(self, user_input: str, console: "Console | None" = None) -> str:  # noqa: F821
        """Process one user turn and return the assistant response text."""
        if self.provider == "ollama":
            return self._ollama_turn(user_input, console)
        return (
            "No AI provider found. bb chat needs an LLM to work.\n\n"
            "Option 1 — Claude API (easiest, free tier available):\n"
            "  1. Get a free API key at https://console.anthropic.com\n"
            "  2. Add to ~/.bb/config.toml:\n"
            "       [ai]\n"
            "       provider = \"claude\"\n"
            "       api_key = \"sk-ant-...\"\n\n"
            "Option 2 — Ollama (free, runs fully offline):\n"
            "  1. Install: https://ollama.com\n"
            "  2. Pull a model: ollama pull qwen2.5:7b  (~4.7 GB)\n"
            "  3. Run: ollama serve\n\n"
            "Then restart bb chat."
        )

    def _stream_answer(self, con: "Console", _ollama: object, think: bool) -> str:  # noqa: F821
        """Stream the final answer token-by-token, rendering live to the console.

        Uses Rich Live so tokens appear immediately. The "bb: " prefix is included
        inside the Live render so it moves with the text as it grows. Tools are
        disabled on this call — the model is answering, not calling tools.
        <think> blocks are stripped on every refresh so thinking noise never shows.

        Returns the complete stripped text (for history storage).
        """
        from rich.live import Live
        from rich.text import Text

        chunks: list[str] = []

        with Live(Text("bb: "), console=con, refresh_per_second=15, transient=False) as live:
            for chunk in _ollama.chat(
                model=self.model,
                messages=self._msgs,
                tools=[],
                think=think,
                stream=True,
            ):
                token = (chunk.message.content or "") if chunk.message else ""
                if token:
                    chunks.append(token)
                    visible = _strip_think("".join(chunks))
                    live.update(Text(f"bb: {visible}"))

        con.print()  # blank line after streamed output
        return _strip_think("".join(chunks))

    def _ollama_turn(self, user_input: str, console: "Console | None") -> str:
        try:
            import ollama as _ollama
        except ImportError:
            return "Ollama package not installed. Run: uv add ollama"

        from rich.console import Console as RichConsole
        from rich.status import Status

        con = console or RichConsole()
        self._msgs.append({"role": "user", "content": user_input})
        tools = build_ollama_tools()
        # think is the single source of truth — do not also inject /no_think into the prompt
        think = self._cfg.ai.think

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                # Every round offers the full tool list. The model decides whether to call
                # tools — we don't restrict after round 0 (that broke multi-step tool calls).
                with Status("⟳ Thinking...", console=con, spinner="dots"):
                    response = _ollama.chat(
                        model=self.model,
                        messages=self._msgs,
                        tools=tools,
                        think=think,
                    )
                msg = response.message

                if not msg.tool_calls:
                    # Final answer — stream it so tokens appear live.
                    # _stream_answer renders directly to console and returns the full text.
                    # We do NOT append to self._msgs before streaming: if _stream_answer raises,
                    # the except block's pop() will correctly target the user message, not a
                    # half-committed assistant message.
                    response_text = self._stream_answer(con, _ollama, think)
                    self._msgs.append({"role": "assistant", "content": response_text})
                    self._save_history(user_input, response_text)
                    return ""  # already rendered; signal run_chat not to print again

                # Decode arguments once, then use for both history and dispatch
                decoded_calls = []
                for tc in msg.tool_calls:
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    call_id = getattr(tc, "id", None) or tc.function.name
                    decoded_calls.append((tc.function.name, args, call_id))

                self._msgs.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": call_id, "function": {"name": name, "arguments": args}}
                        for name, args, call_id in decoded_calls
                    ],
                })

                for name, args, call_id in decoded_calls:
                    con.print(f"[dim]🔧 {_tool_label(name)}...[/dim]")
                    result = dispatch_tool(name, args)
                    self._msgs.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    })

            limit_msg = "I reached my limit processing your request. Please try a simpler question."
            self._msgs.append({"role": "assistant", "content": limit_msg})
            return limit_msg
        except Exception as exc:
            self._msgs.pop()  # remove the user message so history stays consistent
            # Surface Ollama-specific errors as readable messages rather than tracebacks
            err = str(exc)
            if "model runner has unexpectedly stopped" in err or "500" in err:
                return (
                    "The local AI model crashed — likely ran out of memory. "
                    "Try restarting Ollama (`ollama serve`) or switching to a smaller model."
                )
            if "connection" in err.lower() or "connect" in err.lower():
                return "Cannot reach Ollama. Is it running? Try: `ollama serve`"
            raise


# ---------------------------------------------------------------------------
# REPL entry point
# ---------------------------------------------------------------------------

_SLASH_HELP = (
    "  /exit, /quit — leave chat\n"
    "  /clear       — reset conversation\n"
    "  /sync        — run bb sync\n"
    "  /courses     — list your courses\n"
    "  /think       — toggle think mode (deep reasoning on/off)\n"
    "  /help        — show this message"
)


def run_chat(
    query: str | None = None,
    cfg: "BBConfig | None" = None,
    console: "Console | None" = None,
) -> None:
    """Entry point for `bb chat`. Pass query for single-shot; omit for REPL."""
    from rich.console import Console as RichConsole

    from bb.config import load_config

    if cfg is None:
        cfg = load_config()
    con = console or RichConsole()

    engine = ChatEngine(cfg)

    if engine.provider == "none":
        con.print("[yellow]⚠ No AI provider found. bb chat needs an LLM to work.[/yellow]")
        con.print("")
        con.print("[bold]Option 1 — Claude API (easiest, free tier available):[/bold]")
        con.print("  1. Get a free API key at [link]https://console.anthropic.com[/link]")
        con.print("  2. Add to ~/.bb/config.toml:")
        con.print('       [ai]\n       provider = "claude"\n       api_key = "sk-ant-..."')
        con.print("")
        con.print("[bold]Option 2 — Ollama (free, runs fully offline):[/bold]")
        con.print("  1. Install: [link]https://ollama.com[/link]")
        con.print("  2. Pull a model: [bold]ollama pull qwen2.5:7b[/bold]  (~4.7 GB)")
        con.print("  3. Run: [bold]ollama serve[/bold]")
        con.print("")
        con.print("Then restart bb chat.")
        return

    if query:
        # Single-shot mode
        con.print(f"[dim]({engine.get_provider_display()})[/dim]")
        response = engine.process_turn(query, console=con)
        if response:  # "" means streaming already rendered the answer
            con.print(response)
        return

    # Interactive REPL
    con.print(
        f"[bold cyan]🤖 bb-cli AI[/bold cyan] [dim]— "
        f"Your Blackboard assistant ({engine.get_provider_display()})[/dim]"
    )
    con.print("[dim]Type '/exit' to quit, '/help' for commands[/dim]")

    # First-run hint: show example queries when there is no prior history
    if len(engine._msgs) == 1:  # only system prompt = fresh session
        con.print(
            "[dim]  Try: 'what's due this week?' · 'any new announcements?' · 'show my grades'[/dim]"
        )
    con.print()

    while True:
        try:
            prompt_label = "[bold]You [think]:[/bold]" if engine._cfg.ai.think else "[bold]You:[/bold]"
            user_input = con.input(prompt_label + " ").strip()
        except (EOFError, KeyboardInterrupt):
            con.print("\n👋 See you later!")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            should_exit = _handle_slash(user_input, engine, con)
            if should_exit:
                break
            continue

        response = engine.process_turn(user_input, console=con)
        if response:
            # Non-streaming path: error messages, limit notices, etc.
            con.print(f"\n[bold cyan]bb:[/bold cyan] {response}\n")


def _handle_slash(cmd_line: str, engine: "ChatEngine", con: "Console") -> bool:
    """Dispatch slash commands inside the REPL. Returns True if should exit."""
    cmd = cmd_line.split()[0].lower()

    if cmd in ("/exit", "/quit"):
        con.print("👋 See you later!")
        return True

    elif cmd == "/clear":
        engine.clear_history()
        con.print("[dim]Conversation cleared.[/dim]")

    elif cmd == "/sync":
        import subprocess
        import sys
        con.print("[dim]Running bb sync...[/dim]")
        result = subprocess.run(
            [sys.executable, "-m", "bb.cli", "sync"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            con.print("[green]✔[/green] Sync complete.")
        else:
            con.print("[yellow]⚠[/yellow] Sync failed — try `bb sync` from terminal.")

    elif cmd == "/courses":
        from bb.tools.queries import get_course_list
        courses = get_course_list()
        if courses:
            con.print("📚 Courses: " + ", ".join(courses))
        else:
            con.print("[dim]No courses found. Run `bb sync` first.[/dim]")

    elif cmd == "/think":
        engine._cfg.ai.think = not engine._cfg.ai.think
        state = "ON 🧠" if engine._cfg.ai.think else "OFF ⚡"
        con.print(f"[dim]Think mode: {state}[/dim]")

    elif cmd == "/help":
        con.print(_SLASH_HELP)

    else:
        con.print(f"[dim]Unknown command: {cmd}. Type /help for list.[/dim]")

    return False
