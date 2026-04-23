"""Command-line interface for C.E.H.

Provides the `ceh` CLI entry point using Typer.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import rich
import typer
from rich.console import Console

from c_e_h.agent import Agent, AgentConfig
from c_e_h.logging_config import LOG_LEVELS, setup_logging
from c_e_h.shutdown import GracefulShutdown
from c_e_h.streaming import stream_display

# Lazy import for UI modules (avoid requiring Rich at import time for basic commands)
_UI_Dashboard = None
_UI_SessionBrowser = None
_UI_EnhancedStreamDisplay = None


def _get_ui_modules():
    """Lazy-load UI modules to avoid import errors."""
    global _UI_Dashboard, _UI_SessionBrowser, _UI_EnhancedStreamDisplay
    if _UI_Dashboard is None:
        from c_e_h.ui import Dashboard, EnhancedStreamDisplay, SessionBrowser
        _UI_Dashboard = Dashboard
        _UI_EnhancedStreamDisplay = EnhancedStreamDisplay
        _UI_SessionBrowser = SessionBrowser
    return _UI_Dashboard, _UI_SessionBrowser, _UI_EnhancedStreamDisplay

logger = logging.getLogger(__name__)

# Global verbose flag for CLI-level verbose output
_verbose: bool = False

app = typer.Typer(
    name="ceh",
    help="Core Engine Hub — Local AI Agent Framework",
    add_completion=False,
)


@app.command()
def run(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Path to GGUF model file.",
    ),
    n_gpu_layers: int = typer.Option(
        -1,
        "--gpu-layers",
        "-g",
        help="Number of layers to offload to GPU. -1 = all layers.",
    ),
    n_ctx: int = typer.Option(
        8192,
        "--ctx-size",
        "-c",
        help="Context window size in tokens.",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-C",
        help="Path to agent.md config file.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging verbosity level.",
        case_sensitive=False,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG log level, SQL tracing, memory reporting).",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output.",
        is_flag=True,
    ),
) -> None:
    """Start the agent with a specified GGUF model."""
    global _verbose
    _verbose = verbose
    effective_level: str = "DEBUG" if debug else log_level
    setup_logging(log_level=effective_level, debug=debug, verbose=verbose)
    if config:
        agent = Agent.from_agent_md(config)
    else:
        agent = Agent(AgentConfig(model_path=model, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx))

    rich.print("[bold green]C.E.H.[/bold green] — Agent started")
    rich.print(f"  Config: {agent.config.name} v{agent.config.version}")
    rich.print("  Type 'quit' or 'exit' to leave, 'help' for commands.\n")

    _run_repl(agent)


def _run_repl(agent: "Agent") -> None:
    """Run an interactive REPL loop for the agent.

    Supports commands:
      <text>       — Send prompt to agent
      /help        — Show help
      /status      — Show agent status
      /config      — Show current config
      /clear       — Clear context
      /quit, /exit — Exit the REPL
    """
    console = Console()

    while True:
        try:
            prompt = console.input("[bold green]> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            break

        stripped = prompt.strip()
        if not stripped:
            continue

        if stripped in ("quit", "exit", "/quit", "/exit"):
            console.print("[yellow]Goodbye![/yellow]")
            break

        if stripped in ("/help", "help", "?"):
            _print_help()
            continue

        if stripped in ("/status", "status"):
            _print_status(agent)
            continue

        if stripped in ("/config", "config"):
            _print_config(agent)
            continue

        if stripped in ("/clear", "clear"):
            agent.state.context.clear()
            console.print("[dim]Context cleared.[/dim]")
            continue

        # Send to agent
        try:
            response = agent.run(stripped)
            console.print(f"\n[bold blue]{response}[/bold blue]\n")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]\n")


def _print_help() -> None:
    """Print REPL help message."""
    help_text = """
[bold]Available Commands:[/bold]
  [cyan]/help[/cyan]          Show this help message
  [cyan]/status[/cyan]        Show agent status (steps, mode, errors)
  [cyan]/config[/cyan]        Show current configuration
  [cyan]/clear[/cyan]         Clear conversation context
  [cyan]/quit, /exit[/cyan]   Exit the REPL
  [dim]<any text>[/dim]  Send as prompt to the agent
"""
    rich.print(help_text)


def _print_status(agent: "Agent") -> None:
    """Print agent status."""
    console = Console()
    status = agent.state
    console.print(f"""
[bold]Agent Status:[/bold]
  Steps:    {status.step_count}
  Mode:     {status.mode}
  Errors:   {status.auto_errors}
  Context:  {len(status.context)} messages
""")


def _print_config(agent: "Agent") -> None:
    """Print current agent config."""
    cfg = agent.config
    console = Console()
    console.print(f"""
[bold]Agent Configuration:[/bold]
  Name:           {cfg.name}
  Version:        {cfg.version}
  Model:          {cfg.model_path}
  GPU Layers:     {cfg.n_gpu_layers}
  Context Size:   {cfg.n_ctx}
  Temperature:    {cfg.temperature}
  Permission:     {cfg.permission_mode}
  Log Level:      {cfg.log_level}
""")


@app.command()
def interactive(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Path to GGUF model file.",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-C",
        help="Path to agent.md config file.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging verbosity level.",
        case_sensitive=False,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG log level, SQL tracing, memory reporting).",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output.",
        is_flag=True,
    ),
) -> None:
    """Start the interactive CLI with a specified GGUF model."""
    global _verbose
    _verbose = verbose
    effective_level: str = "DEBUG" if debug else log_level
    setup_logging(log_level=effective_level, debug=debug, verbose=verbose)
    if config:
        agent = Agent.from_agent_md(config)
    else:
        agent = Agent(AgentConfig(model_path=model))

    rich.print("[bold blue]C.E.H.[/bold blue] — Interactive mode")
    rich.print(f"  Config: {agent.config.name} v{agent.config.version}")
    rich.print("  Type 'quit' or 'exit' to leave, 'help' for commands.\n")

    _run_repl(agent)


@app.command()
def stream(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Path to GGUF model file.",
    ),
    prompt: str = typer.Option(
        ...,
        "--prompt",
        "-p",
        help="Prompt to send to the model.",
    ),
    max_tokens: int = typer.Option(
        512,
        "--max-tokens",
        "-n",
        help="Maximum tokens to generate.",
    ),
    temperature: float = typer.Option(
        0.7,
        "--temperature",
        "-t",
        help="Sampling temperature.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging verbosity level.",
        case_sensitive=False,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG log level, SQL tracing, memory reporting).",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output.",
        is_flag=True,
    ),
) -> None:
    """Generate a streaming response from the model."""
    global _verbose
    _verbose = verbose
    effective_level: str = "DEBUG" if debug else log_level
    setup_logging(log_level=effective_level, debug=debug, verbose=verbose)

    from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

    config = ModelConfig(
        path=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    backend = LlamaBackend(config)

    try:
        backend.load()

        def _callback(chunk: dict) -> None:
            """Log each streaming chunk at DEBUG level."""
            logging.getLogger(__name__).debug(
                "stream_chunk tokens=%d",
                chunk.get("usage", {}).get("completion_tokens", 0),
            )

        rich.print("[bold green]Streaming:[/bold green] Starting...")
        result = stream_display(
            backend.complete(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                callback=_callback,
            ),
            title="C.E.H. Streaming",
            show_metrics=True,
        )
        rich.print()
        rich.print(f"[dim]Tokens:[/dim] {result.token_count}  "
                    f"[dim]Prompt:[/dim] {result.prompt_tokens}  "
                    f"[dim]Gen:[/dim] {result.generation_time:.3f}s  "
                    f"[dim]Speed:[/dim] {result.tokens_per_second:.1f} tok/s")

        # Debug output: memory usage
        if debug:
            from c_e_h.logging_config import get_memory_usage
            mem = get_memory_usage()
            rich.print(f"[dim]Memory:[/dim] RSS={mem['rss_mb']:.2f} MB")
    except BackendError as exc:
        rich.print(f"[bold red]Backend error:[/bold red] {exc}")
        sys.exit(1)
    finally:
        backend.close()


@app.command()
def version(
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging verbosity level.",
        case_sensitive=False,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG log level, SQL tracing, memory reporting).",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output.",
        is_flag=True,
    ),
) -> None:
    """Print the installed C.E.H. version."""
    global _verbose
    _verbose = verbose
    effective_level: str = "DEBUG" if debug else log_level
    setup_logging(log_level=effective_level, debug=debug, verbose=verbose)
    from c_e_h import __version__

    rich.print(f"C.E.H. v{__version__}")


# ---------------------------------------------------------------------------
# Model subcommand group
# ---------------------------------------------------------------------------
model_app = typer.Typer(
    name="model",
    help="Model management (download, list, remove).",
    add_completion=False,
)


@model_app.command("download")
def model_download(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Model ID to download from the registry.",
    ),
) -> None:
    """Download a model from the registry."""
    from c_e_h.model_registry import (
        DEFAULT_MODEL_DIR,
        DEFAULT_REGISTRY_PATH,
        DownloadError,
        ModelNotFoundError,
        ModelRegistry,
        download_model,
    )

    try:
        registry = ModelRegistry(DEFAULT_REGISTRY_PATH)
        info = registry.get_model(name)
    except ModelNotFoundError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    rich.print(f"[bold green]Downloading:[/bold green] {info.name}")
    rich.print(f"  Source: {info.source}")
    rich.print(f"  SHA256: {info.sha256}")
    rich.print(f"  Destination: {info.path}")

    try:
        dest = download_model(
            url=info.source,
            destination=info.path,
            expected_sha256=info.sha256,
            registry_path=DEFAULT_REGISTRY_PATH,
            model_dir=DEFAULT_MODEL_DIR,
        )
        rich.print(f"[bold green]Download complete:[/bold green] {dest}")
    except DownloadError as exc:
        rich.print(f"[bold red]Download failed:[/bold red] {exc}")
        sys.exit(1)


@model_app.command("list")
def model_list() -> None:
    """List all registered models."""
    from c_e_h.model_registry import ModelRegistry

    registry = ModelRegistry(DEFAULT_REGISTRY_PATH)
    models = registry.list_models()

    if not models:
        rich.print("[yellow]No models registered.[/yellow]")
        return

    rich.print("[bold]Registered Models:[/bold]")
    for m in models:
        recommended_marker = " [bold green](recommended)[/bold green]" if m.recommended else ""
        rich.print(f"  [bold]{m.id}[/bold]{recommended_marker}")
        rich.print(f"    Name:     {m.name}")
        rich.print(f"    Path:     {m.path}")
        rich.print(f"    Size:     {m.size_bytes:,} bytes")
        rich.print(f"    Context:  {m.context_window} tokens")
        rich.print(f"    Quant:    {m.quantization}")
        rich.print(f"    License:  {m.license}")
        rich.print()


@model_app.command("remove")
def model_remove(
    id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Model ID to remove from the registry.",
    ),
) -> None:
    """Remove a model from the registry."""
    from c_e_h.model_registry import ModelNotFoundError, ModelRegistry

    registry = ModelRegistry(DEFAULT_REGISTRY_PATH)
    try:
        info = registry.get_model(id)
    except ModelNotFoundError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    removed = registry.remove_model(id)
    if removed:
        rich.print(f"[bold green]Removed:[/bold green] {info.name} ({id})")
    else:
        rich.print(f"[yellow]Model not found:[/yellow] {id}")


@model_app.command("show")
def model_show(
    id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Model ID to show details for.",
    ),
) -> None:
    """Show detailed information about a registered model."""
    from c_e_h.model_registry import ModelNotFoundError, ModelRegistry

    registry = ModelRegistry(DEFAULT_REGISTRY_PATH)
    try:
        info = registry.get_model(id)
    except ModelNotFoundError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    rich.print(f"[bold]{info.name}[/bold] ({info.id})")
    rich.print(f"  Path:           {info.path}")
    rich.print(f"  Size:           {info.size_bytes:,} bytes")
    rich.print(f"  Context Window: {info.context_window} tokens")
    rich.print(f"  Quantization:   {info.quantization}")
    rich.print(f"  Source:         {info.source}")
    rich.print(f"  License:        {info.license}")
    rich.print(f"  SHA256:         {info.sha256}")
    recommended_marker = " [bold green](recommended)[/bold green]" if info.recommended else ""
    rich.print(f"  Recommended:    {info.recommended}{recommended_marker}")


@model_app.command("verify")
def model_verify(
    id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Model ID to verify.",
    ),
) -> None:
    """Verify a model file's SHA256 checksum."""
    from c_e_h.model_registry import ModelNotFoundError, ModelRegistry

    registry = ModelRegistry(DEFAULT_REGISTRY_PATH)
    try:
        info = registry.get_model(id)
    except ModelNotFoundError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    result = registry.verify_model(id)
    if result:
        rich.print(f"[bold green]PASS:[/bold green] SHA256 verification passed for {info.name} ({id})")
    else:
        rich.print(f"[bold red]FAIL:[/bold red] SHA256 verification failed or file not found for {info.name} ({id})")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Session subcommand group
# ---------------------------------------------------------------------------
session_app = typer.Typer(
    name="session",
    help="Session management (create, list, switch, delete).",
    add_completion=False,
)


@session_app.command("new")
def session_new(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Session name.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Model identifier for this session.",
    ),
    system_prompt: Optional[str] = typer.Option(
        None,
        "--system-prompt",
        "-s",
        help="System prompt for this session.",
    ),
) -> None:
    """Create a new session."""
    from c_e_h.session_manager import SessionError, SessionManager

    try:
        sm = SessionManager()
        session = sm.create_session(
            name=name,
            system_prompt=system_prompt,
            model=model,
        )
        rich.print(f"[bold green]Session created:[/bold green] {session.id}")
        rich.print(f"  Name:       {session.name}")
        rich.print(f"  Created:    {session.created_at}")
        rich.print(f"  Model:      {session.model or 'default'}")
    except SessionError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)


@session_app.command("list")
def session_list() -> None:
    """List all sessions."""
    from c_e_h.session_manager import SessionManager

    sm = SessionManager()
    sessions = sm.list_sessions()

    if not sessions:
        rich.print("[yellow]No sessions found.[/yellow]")
        return

    rich.print("[bold]Sessions:[/bold]")
    for s in sessions:
        rich.print(f"  [bold]{s.id}[/bold] — {s.name}")
        rich.print(f"    Messages:   {s.message_count}")
        rich.print(f"    Last used:  {s.last_accessed}")
        if s.model:
            rich.print(f"    Model:      {s.model}")
        rich.print()


@session_app.command("switch")
def session_switch(
    id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Session ID to switch to.",
    ),
) -> None:
    """Switch to an existing session."""
    from c_e_h.session_manager import SessionManager

    sm = SessionManager()
    session = sm.get_session(id)
    if session is None:
        rich.print(f"[bold red]Session not found:[/bold red] {id}")
        sys.exit(1)

    sm.update_last_accessed(id)
    rich.print(f"[bold green]Switched to session:[/bold green] {session.id}")
    rich.print(f"  Name:       {session.name}")
    rich.print(f"  Messages:   {session.message_count}")
    rich.print(f"  Last used:  {session.last_accessed}")


@session_app.command("delete")
def session_delete(
    id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Session ID to delete.",
    ),
) -> None:
    """Delete a session and all its messages."""
    from c_e_h.session_manager import SessionError, SessionManager

    sm = SessionManager()
    try:
        deleted = sm.delete_session(id)
    except SessionError as exc:
        rich.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    if deleted:
        rich.print(f"[bold green]Deleted session:[/bold green] {id}")
    else:
        rich.print(f"[yellow]Session not found:[/yellow] {id}")


app.add_typer(model_app)  # register model subcommand group
app.add_typer(session_app)  # register session subcommand group

# ---------------------------------------------------------------------------
# Cleanup command
# ---------------------------------------------------------------------------


@app.command()
def cleanup(
    max_age_days: int = typer.Option(
        30,
        "--max-age-days",
        "-a",
        help="Maximum age in days before a session is considered expired.",
    ),
    max_sessions: int = typer.Option(
        100,
        "--max-sessions",
        "-s",
        help="Maximum number of sessions to retain.",
    ),
    no_archive: bool = typer.Option(
        False,
        "--no-archive",
        "-n",
        help="Disable archiving before deletion (delete directly).",
        is_flag=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Show what would be cleaned up without making changes.",
        is_flag=True,
    ),
) -> None:
    """Clean up old sessions based on TTL and count limits.

    This command performs two cleanup passes:

    1. TTL-based expiration: Removes sessions older than ``max_age_days``
       based on the ``last_accessed`` timestamp.

    2. Max session count enforcement: If the total session count exceeds
       ``max_sessions``, the oldest sessions are archived or deleted until
       the limit is met.
    """
    from c_e_h.session_manager import CleanupError, SessionError, SessionManager

    sm = SessionManager()

    if dry_run:
        rich.print("[bold yellow]DRY RUN:[/bold yellow] No changes will be made.")
        # List sessions that would be cleaned up
        sessions = sm.list_sessions()
        if not sessions:
            rich.print("[dim]No sessions found.[/dim]")
            return

        # Show expired sessions
        now = datetime.now(timezone.utc)
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max_age_days)

        expired = []
        for s in sessions:
            try:
                last_accessed = datetime.fromisoformat(s.last_accessed)
                if last_accessed < cutoff:
                    expired.append(s)
            except (ValueError, TypeError):
                pass

        if expired:
            rich.print(f"[bold red]Expired sessions ({len(expired)}):[/bold red]")
            for s in expired:
                rich.print(f"  [bold]{s.id}[/bold] — {s.name} (last accessed: {s.last_accessed})")
        else:
            rich.print("[bold green]No expired sessions.[/bold green]")

        # Check max session count
        if len(sessions) > max_sessions:
            excess = len(sessions) - max_sessions
            rich.print(f"[bold yellow]Excess sessions ({excess} over limit of {max_sessions}):[/bold yellow]")
            sorted_sessions = sorted(sessions, key=lambda s: s.last_accessed)
            for s in sorted_sessions[:excess]:
                rich.print(f"  [bold]{s.id}[/bold] — {s.name} (last accessed: {s.last_accessed})")
        else:
            rich.print(f"[bold green]Session count ({len(sessions)}) within limit ({max_sessions}).[/bold green]")
        return

    try:
        report = sm.cleanup_old_sessions(
            max_age_days=max_age_days,
            max_session_count=max_sessions,
            archive=not no_archive,
        )
    except (CleanupError, SessionError) as exc:
        rich.print(f"[bold red]Cleanup error:[/bold red] {exc}")
        sys.exit(1)

    # Display report
    rich.print("[bold green]Cleanup Report:[/bold green]")
    rich.print(f"  Sessions scanned:    {report.sessions_scanned}")
    rich.print(f"  Sessions deleted:    {report.sessions_deleted}")
    rich.print(f"  Sessions archived:   {report.sessions_archived}")
    rich.print(f"  Messages archived:   {report.messages_archived}")
    rich.print(f"  Space freed:         {report.space_freed_bytes:,} bytes")
    rich.print(f"  Archive directory:   {report.archive_dir}")


# ---------------------------------------------------------------------------
# Plugin subcommand group
# ---------------------------------------------------------------------------
plugin_app = typer.Typer(
    name="plugin",
    help="Plugin management (list, info).",
    add_completion=False,
)


@plugin_app.command("list")
def plugin_list() -> None:
    """List all discovered plugins."""
    from c_e_h.plugin import PluginManager

    pm = PluginManager()
    pm.discover_plugins()
    plugins = pm.list_plugins()

    if not plugins:
        rich.print("[yellow]No plugins discovered.[/yellow]")
        return

    rich.print("[bold]Discovered Plugins:[/bold]")
    for p in plugins:
        status_marker = {
            "loaded": "[bold green](loaded)[/bold green]",
            "error": "[bold red](error)[/bold red]",
            "unloaded": "[dim](unloaded)[/dim]",
        }.get(p["status"], "")
        rich.print(f"  [bold]{p['name']}[/bold] v{p['version']} {status_marker}")
        if p["description"]:
            rich.print(f"    {p['description']}")
        rich.print()


app.add_typer(plugin_app)  # register plugin subcommand group

# ---------------------------------------------------------------------------
# Dashboard command
# ---------------------------------------------------------------------------


@app.command("dashboard")
def dashboard(
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Path to GGUF model file (optional, for metrics display).",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-C",
        help="Path to agent.md config file.",
    ),
    refresh: float = typer.Option(
        2.0,
        "--refresh",
        "-r",
        help="Refresh interval in seconds.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging verbosity level.",
        case_sensitive=False,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode.",
        is_flag=True,
    ),
) -> None:
    """Launch the interactive C.E.H. dashboard.

    Displays a multi-panel real-time view of agent status, sessions,
    messages, and metrics. Press 'q' to quit, '?' for help.
    """
    effective_level: str = "DEBUG" if debug else log_level
    setup_logging(log_level=effective_level, debug=debug, verbose=False)

    Dashboard, _, _ = _get_ui_modules()

    if config:
        agent = Agent.from_agent_md(config)
    elif model:
        agent = Agent(AgentConfig(model_path=model))
    else:
        agent = Agent()

    from c_e_h.session_manager import SessionManager

    try:
        sm = SessionManager()
    except Exception:
        sm = None

    rich.print("[bold green]Starting C.E.H. Dashboard...[/bold green]")
    rich.print("  Press [cyan]q[/cyan] to quit, [cyan]?[/cyan] for help")
    rich.print()

    dash = Dashboard(agent, session_manager=sm, refresh_interval=refresh)
    try:
        dash.run()
    except KeyboardInterrupt:
        pass
    finally:
        dash.stop()
        rich.print("[dim]Dashboard stopped.[/dim]")


@app.command("sessions")
def sessions_ui(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter sessions by name.",
    ),
    create: Optional[str] = typer.Option(
        None,
        "--create",
        "-c",
        help="Create a new session with the given name.",
    ),
    delete: Optional[str] = typer.Option(
        None,
        "--delete",
        "-d",
        help="Delete the session with the given ID.",
    ),
    select: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Run in interactive mode with keyboard input.",
        is_flag=True,
    ),
) -> None:
    """Launch the session management UI.

    Displays a table of all sessions with options to filter, create,
    delete, or interactively select sessions.
    """
    from c_e_h.session_manager import SessionManager

    try:
        sm = SessionManager()
    except Exception as e:
        rich.print(f"[bold red]Error connecting to session database:[/bold red] {e}")
        sys.exit(1)

    _, SessionBrowser, _ = _get_ui_modules()
    browser = SessionBrowser(sm)

    if create:
        session = browser.create_session(create)
        if session:
            rich.print(f"  ID: {session.id}")
            rich.print(f"  Messages: {session.message_count}")
        return

    if delete:
        browser.delete_session(delete)
        return

    if select:
        selected = browser.interactive_mode()
        if selected:
            rich.print(f"\n[bold green]Selected session:[/bold green] {selected}")
        return

    browser.render(filter)


def main() -> None:
    """Entry point for the `ceh` CLI."""
    shutdown = GracefulShutdown()

    def _cleanup() -> None:
        """Cleanup callback for graceful shutdown."""
        # Cleanup sequence: save session → close LLM → close DB → release locks
        # (Placeholder — actual implementations depend on active resources)
        pass

    shutdown.register(_cleanup)

    try:
        app()
    except KeyboardInterrupt:
        # If user presses Ctrl+C outside the signal handler context,
        # trigger shutdown manually.
        shutdown._handle_signal(sys.SIGINT, None)
    finally:
        shutdown.unregister()


def get_verbose() -> bool:
    """Return the current global verbose flag.

    Returns:
        ``True`` if verbose mode is enabled, ``False`` otherwise.
    """
    return _verbose


def _validate_log_level(value: str) -> str:
    """Validate that *value* is a recognised log level.

    Typer calls this callback before the command handler.

    Args:
        value: The raw string from the CLI.

    Returns:
        The upper-cased log level string.

    Raises:
        typer.BadParameter: If the value is not recognised.
    """
    upper = value.upper()
    if upper not in LOG_LEVELS:
        raise typer.BadParameter(
            f"Invalid log level: {value!r}. Must be one of {LOG_LEVELS}"
        )
    return upper


if __name__ == "__main__":
    main()
