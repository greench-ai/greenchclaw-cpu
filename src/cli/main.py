#!/usr/bin/env python3
"""
GreenClaw CLI — single entry point.

Usage:
    greenchclaw              Start chatting
    greenchclaw --onboard    Run setup wizard
    greenchclaw --config     Show/edit config
    greenchclaw --health     System health check
    greenchclaw --version    Show version
    greenchclaw --help       Help
"""

import argparse
import sys
from pathlib import Path

# ── Version ────────────────────────────────────────────────────────────────────
__version__ = "0.1.0"


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_onboard():
    """Launch the first-run onboarding wizard."""
    from .onboard import run_onboarding
    run_onboarding()


def cmd_config(args):
    """Show or edit the config file."""
    import yaml
    from src.config import get_config

    cfg = get_config()
    config_path = Path("config.yaml")

    if args.edit:
        # Open in default editor
        import subprocess
        editor = subprocess.os.environ.get("EDITOR", "nano")
        subprocess.call([editor, str(config_path)])
        print(f"[i] Config saved to {config_path}")
        return

    # Pretty-print current config
    print(f"\n{'─' * 50}")
    print(f"  GreenClaw Config  ({config_path})")
    print(f"{'─' * 50}\n")
    print(f"  Provider:   {cfg.model.provider}")
    print(f"  Model:      {cfg.model.name}")
    print(f"  Ollama URL: {cfg.model.ollama_url}")
    print(f"  Soul dir:   {cfg.soul.soul_dir}")
    print(f"  Active soul:{cfg.soul.active_soul}")
    print(f"  Port:       {cfg.server.port}")
    print(f"  Host:       {cfg.server.host}")
    print(f"  Memory:     {'enabled' if cfg.memory.enabled else 'disabled'}")
    print(f"\n{'─' * 50}")
    print(f"  Edit with: greenchclaw --config --edit")
    print(f"{'─' * 50}\n")


def cmd_health():
    """Run a quick health check of all systems."""
    import urllib.request
    import shutil

    checks = []

    # Python
    checks.append(("Python", True, f"v{sys.version.split()[0]}"))

    # Config
    try:
        from src.config import get_config
        cfg = get_config()
        checks.append(("Config file", True, f"{cfg.model.provider}/{cfg.model.name}"))
    except Exception as e:
        checks.append(("Config file", False, str(e)))

    # Ollama
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        tags = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3).read()
        data = __import__("yaml").safe_load(tags)
        models = [m["name"] for m in data.get("models", [])]
        checks.append(("Ollama", True, f"{len(models)} model(s): {', '.join(models[:3])}{'…' if len(models) > 3 else ''}"))
    except Exception:
        checks.append(("Ollama", False, "not reachable at localhost:11434"))

    # GreenClaw itself
    try:
        from src.soul.soul_manager import SoulManager
        from src.models.factory import create_model
        checks.append(("GreenClaw modules", True, "all loaded"))
    except Exception as e:
        checks.append(("GreenClaw modules", False, str(e)))

    # Disk space
    try:
        import shutil as sh
        total, used, free = sh.disk_usage("/")
        pct = used / total * 100
        checks.append(("Disk space", True, f"{free // (1024**3)} GB free ({pct:.0f}% used)"))
    except Exception:
        pass

    # Print table
    print(f"\n{'─' * 52}")
    print(f"  {__import__('inspect').stack()[0][0].__module__} GreenClaw v{__version__} — Health Check")
    print(f"{'─' * 52}\n")
    max_label = max(len(c[0]) for c in checks)
    for label, ok, detail in checks:
        status = "\033[0;32m✓ OK\033[0m" if ok else "\033[0;31m✗ FAIL\033[0m"
        print(f"  {label:<{max_label}}  {status}  {detail}")
    print(f"\n{'─' * 52}\n")

    all_ok = all(c[1] for c in checks)
    if all_ok:
        print("  \033[0;32mAll systems healthy! Run 'greenchclaw' to start.\033[0m\n")
    else:
        print("  \033[0;31mSome checks failed. Run 'greenchclaw --onboard' to re-configure.\033[0m\n")
        sys.exit(1)


def cmd_chat(args):
    """Start the interactive chat loop."""
    try:
        from src.main import main as chat_main
        chat_main(args)
    except ImportError as e:
        print(f"[✗] Could not load GreenClaw core: {e}")
        print("[i] Run 'greenchclaw --onboard' to set up first.")
        sys.exit(1)


def cmd_serve(args):
    """Start the GreenClaw web server."""
    try:
        from src.web.server import run_server
        host = args.host or "0.0.0.0"
        port = args.port or 51234
        print(f"Starting GreenClaw web server on {host}:{port}")
        print(f"Open http://localhost:{port} in your browser")
        run_server(host=host, port=port, reload=args.reload)
    except ImportError as e:
        print(f"[✗] Could not load web server: {e}")
        print("[i] Install web dependencies: pip install greenchclaw-cpu[all]")
        sys.exit(1)


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="greenchclaw",
        description=f"GreenClaw CPU v{__version__} — The Ultimate Body for a SOUL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  greenchclaw               Start chatting
  greenchclaw --onboard     First-time setup wizard
  greenchclaw --config      Show current config
  greenchclaw --health      Check all systems
  greenchclaw --help        Show this help
""",
    )
    p.add_argument("--onboard", action="store_true",
                   help="Run the first-time setup wizard")
    p.add_argument("--config", action="store_true",
                   help="Show current configuration")
    p.add_argument("--edit", action="store_true",
                   help="Open config.yaml in your editor (use with --config)")
    p.add_argument("--health", action="store_true",
                   help="Run a system health check")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    p.add_argument("--model", dest="model", metavar="PROVIDER",
                   help="Model provider (ollama, openai, anthropic, openrouter)")
    p.add_argument("--name", dest="name", metavar="MODEL",
                   help="Model name (e.g. llama3.2, gpt-4o)")
    p.add_argument("--api-key", dest="api_key", metavar="KEY",
                   help="API key (or set OPENAI_API_KEY / ANTHROPIC_API_KEY env var)")
    p.add_argument("--soul", dest="soul", metavar="NAME",
                   help="Soul/personality name to activate")
    p.add_argument("--port", dest="port", type=int, metavar="PORT",
                   help="Server port (default: 51234)")
    p.add_argument("--no-stream", action="store_true",
                   help="Disable streaming responses")
    p.add_argument("--log-level", dest="log_level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Logging level")
    # Serve / web subcommands
    sub = p.add_subparsers(dest="subcommand", help="Available subcommands")

    serve_sp = sub.add_parser("serve", help="Start the web server on port 51234")
    serve_sp.add_argument("--host", default="0.0.0.0", help="Host to bind")
    serve_sp.add_argument("--port", type=int, default=51234, help="Port to bind")
    serve_sp.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    serve_sp.set_defaults(func=cmd_serve)

    web_sp = sub.add_parser("web", help="Alias for 'serve'")
    web_sp.add_argument("--host", default="0.0.0.0", help="Host to bind")
    web_sp.add_argument("--port", type=int, default=51234, help="Port to bind")
    web_sp.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    web_sp.set_defaults(func=cmd_serve)

    return p


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Dispatch
    if args.onboard:
        cmd_onboard()
    elif args.config:
        cmd_config(args)
    elif args.health:
        cmd_health()
    elif getattr(args, "func", None) is not None:
        args.func(args)
    else:
        cmd_chat(args)


if __name__ == "__main__":
    main()
