"""Chat engine for bb chat — Ollama provider, tool dispatch, REPL."""
from __future__ import annotations

import inspect
import json
import types
import typing
from typing import TYPE_CHECKING

from bb.tools import TOOL_REGISTRY

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
}


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

    def _reset_history(self) -> None:
        from bb.ai.prompts import SYSTEM_PROMPT
        self._msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

    def clear_history(self) -> None:
        """Reset conversation history to initial state."""
        self._reset_history()

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
            "No AI provider configured.\n"
            "• Make sure Ollama is running: brew services start ollama\n"
            "• Then pull a model: ollama pull qwen3:30b-a3b"
        )

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
        think = self._cfg.ai.think

        for _ in range(MAX_TOOL_ROUNDS):
            with Status("⟳ Thinking...", console=con, spinner="dots"):
                response = _ollama.chat(
                    model=self.model,
                    messages=self._msgs,
                    tools=tools,
                    think=think,
                )
            msg = response.message
            msg_dict: dict = {"role": "assistant", "content": msg.content or ""}

            if not msg.tool_calls:
                self._msgs.append(msg_dict)
                return msg.content or ""

            # Build tool_calls list for history
            tc_list = []
            for tc in msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                tc_list.append({"function": {"name": tc.function.name, "arguments": args}})
            msg_dict["tool_calls"] = tc_list
            self._msgs.append(msg_dict)

            # Execute tools and inject results
            for tc in msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                con.print(f"[dim]🔧 {_tool_label(tc.function.name)}...[/dim]")
                result = dispatch_tool(tc.function.name, args)
                self._msgs.append({"role": "tool", "content": result})

        return "I reached my limit processing your request. Please try a simpler question."


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
        con.print("[yellow]⚠ Ollama not available.[/yellow]")
        con.print("• Start it: [bold]brew services start ollama[/bold]")
        con.print("• Pull a model: [bold]ollama pull qwen3:30b-a3b[/bold]")
        return

    if query:
        # Single-shot mode
        con.print(f"[dim]({engine.get_provider_display()})[/dim]")
        response = engine.process_turn(query, console=con)
        con.print(response)
        return

    # Interactive REPL
    con.print(
        f"[bold cyan]🤖 bb-cli AI[/bold cyan] [dim]— "
        f"Your Blackboard assistant ({engine.get_provider_display()})[/dim]"
    )
    con.print("[dim]Type '/exit' to quit, '/help' for commands[/dim]\n")

    while True:
        try:
            user_input = con.input("[bold]You:[/bold] ").strip()
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
        con.print(f"\n[bold cyan]bb:[/bold cyan] {response}\n")


def _handle_slash(cmd_line: str, engine: "ChatEngine", con: "Console") -> bool:
    """Dispatch slash commands inside the REPL. Returns True if should exit."""
    import subprocess

    cmd = cmd_line.split()[0].lower()

    if cmd in ("/exit", "/quit"):
        con.print("👋 See you later!")
        return True

    elif cmd == "/clear":
        engine.clear_history()
        con.print("[dim]Conversation cleared.[/dim]")

    elif cmd == "/sync":
        con.print("[dim]Running bb sync...[/dim]")
        result = subprocess.run(["bb", "sync"], capture_output=True, text=True)
        if result.returncode == 0:
            con.print("[green]✔[/green] Sync complete.")
        else:
            con.print("[yellow]⚠[/yellow] Could not run sync. Try `bb sync` from terminal.")

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
