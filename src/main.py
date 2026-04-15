#!/usr/bin/env python3
"""
GreenClaw CPU — The Ultimate Body for a SOUL

MIT License | Local-first AI Agent | Freedom is Key

Usage:
    python -m src.main                              # Interactive chat
    python -m src.main --model ollama --name llama3.2
    python -m src.main --model openai --api-key sk-... --name gpt-4o
    python -m src.main --soul my-custom-soul
    python -m src.main --health-check
"""

import argparse
import asyncio
import logging
import os
import sys
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_config, reload_config
from src.models.factory import create_provider
from src.soul.soul_manager import SoulManager
from src.memory.memory import Memory
from src.agent.agent import Agent

__version__ = "0.1.0"


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for GreenClaw."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="greenchlaw",
        description="GreenClaw CPU — The Ultimate Body for a SOUL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  greenclaw                              # Ollama local mode (default)
  greenclaw --model openai --name gpt-4o  # OpenAI cloud mode
  greenclaw --health-check               # Check all systems
  greenclaw --soul developer             # Use 'developer' soul

Environment variables:
  GREENCLAW_PROVIDER     Override model provider
  GREENCLAW_MODEL        Override model name
  OPENAI_API_KEY         OpenAI API key
  ANTHROPIC_API_KEY      Anthropic API key
  GREENCLAW_CONFIG       Path to config.yaml
  GREENCLAW_PORT         Server port (default: 51234 for CPU)
  GREENCLAW_HOST         Server bind address

Run multiple GreenClaw versions simultaneously:
  GREENCLAW_CPU:           --port 51234
  GREENCLAW_GPU:           --port 51235
  GREENCLAW_KIDGUARDIAN:   --port 51236
        """,
    )

    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=None,
        help="Server port (default: 51234 for GreenClaw CPU). "
             "Multiple GreenClaw versions can run simultaneously on different ports.",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default=None,
        help="Server bind address (default: 0.0.0.0)",
    )

    parser.add_argument(
        "--model", "--model-provider",
        dest="model_provider",
        default=None,
        help="Model provider: ollama, openai, anthropic, openrouter (default: ollama)",
    )
    parser.add_argument(
        "--name", "--model-name",
        dest="model_name",
        default=None,
        help="Model name to use (default: llama3.2 for ollama)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="API key for cloud providers",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=None,
        help="Custom base URL for OpenAI-compatible APIs",
    )
    parser.add_argument(
        "--ollama-url",
        dest="ollama_url",
        default=None,
        help="Ollama server URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--soul",
        dest="soul",
        default=None,
        help="Active soul/personality name (default: default)",
    )
    parser.add_argument(
        "--soul-dir",
        dest="soul_dir",
        default=None,
        help="Soul files directory",
    )
    parser.add_argument(
        "--config",
        dest="config",
        default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run health check on all components",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming responses",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"GreenClaw CPU {__version__}",
    )

    return parser.parse_args()


async def health_check(args: argparse.Namespace, config) -> int:
    """Run health check on all systems."""
    print("\n" + "═" * 50)
    print("  🩺 GreenClaw Health Check")
    print("═" * 50)

    port = args.port or config.server.port
    host = args.host or config.server.host
    print(f"\n🖥️  Server:")
    print(f"   Port: {port}")
    print(f"   Host: {host}")

    # Model provider
    print(f"\n📡 Model Provider:")
    print(f"   Provider: {args.model_provider or config.model.provider}")
    print(f"   Model:    {args.model_name or config.model.name}")

    provider = create_provider(
        provider_name=args.model_provider or config.model.provider,
        model_name=args.model_name or config.model.name,
        api_key=args.api_key or config.model.api_key,
        base_url=args.base_url or config.model.base_url,
        ollama_url=args.ollama_url or config.model.ollama_url,
    )

    print(f"   URL:      {provider}")
    print("   Checking... ", end="", flush=True)

    try:
        healthy = await provider.health_check()
        if healthy:
            print("✅ Connected")
        else:
            print("❌ Failed")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    await provider.close()

    # Soul
    print(f"\n🧬 Soul System:")
    soul_dir = args.soul_dir or config.soul.soul_dir
    soul_name = args.soul or config.soul.active_soul
    print(f"   Soul Dir:  {soul_dir}")
    print(f"   Active:    {soul_name}")

    soul_path = Path(soul_dir).expanduser() / soul_name
    if soul_path.exists():
        print("   Status:    ✅ Found")
    else:
        print("   Status:    ⚠️  Not found (will use defaults)")

    # Memory
    print(f"\n🧠 Memory:")
    print(f"   Enabled:   {config.memory.enabled}")
    print(f"   Dir:      {config.memory.memory_dir}")

    print(f"\n" + "═" * 50)
    print("  ✅ Health check complete")
    print("═" * 50 + "\n")

    return 0


async def chat_loop(agent: Agent) -> None:
    """Run the interactive chat loop."""
    print("\n" + "─" * 50)
    print("  🦎 GreenClaw CPU — Type 'exit' or 'quit' to stop")
    print("  💡 Tip: Use /soul <name> to switch personalities")
    print("  💡 Tip: Use /health to check system status")
    print("  💡 Tip: Use /clear to clear conversation memory")
    print("  💡 Tip: Use /souls to list available souls")
    print("─" * 50 + "\n")

    while True:
        try:
            user_input = input("👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.lower() in ("exit", "quit", "q"):
            print("\n👋 Goodbye!")
            break

        if user_input.startswith("/soul "):
            soul_name = user_input[6:].strip()
            agent.switch_soul(soul_name)
            print(f"✅ Switched to soul: {soul_name}")
            continue

        if user_input.lower() == "/health":
            status = await agent.health_check()
            print(f"   Model: {'✅' if status.get('model') else '❌'}  ", end="")
            print(f"Soul: {'✅' if status.get('soul') else '❌'}  ", end="")
            print(f"Memory: {'✅' if status.get('memory') else '❌'}")
            continue

        if user_input.lower() == "/clear":
            agent.memory.clear()
            print("🧹 Memory cleared")
            continue

        if user_input.lower() == "/souls":
            souls = agent.list_souls()
            print(f"📂 Available souls: {', '.join(souls) if souls else '(none)'}")
            continue

        # Process message
        try:
            await agent.run(user_input)
        except Exception as e:
            print(f"\n⚠️  Error: {e}")
            logging.exception("Chat error")


async def main_async(args: argparse.Namespace) -> int:
    """Async main function."""
    # Load config
    config_path = args.config or os.environ.get("GREENCLAW_CONFIG", "config.yaml")
    config = reload_config(config_path)

    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info(f"GreenClaw CPU v{__version__} starting...")

    # Health check mode
    if args.health_check:
        return await health_check(args, config)

    # Build provider kwargs
    provider_kwargs = {}
    if args.model_provider:
        provider_kwargs["provider_name"] = args.model_provider
    if args.model_name:
        provider_kwargs["model_name"] = args.model_name
    if args.api_key:
        provider_kwargs["api_key"] = args.api_key
    if args.base_url:
        provider_kwargs["base_url"] = args.base_url
    if args.ollama_url:
        provider_kwargs["ollama_url"] = args.ollama_url

    # Create provider
    cfg = args.model_provider or config.model.provider
    mn = args.model_name or config.model.name
    ak = args.api_key or config.model.api_key
    bu = args.base_url or config.model.base_url
    ou = args.ollama_url or config.model.ollama_url

    provider = create_provider(
        provider_name=cfg,
        model_name=mn,
        api_key=ak,
        base_url=bu,
        ollama_url=ou,
    )

    # Server settings
    port = args.port or config.server.port
    host = args.host or config.server.host

    # Soul manager
    soul_dir = args.soul_dir or config.soul.soul_dir
    soul_name = args.soul or config.soul.active_soul
    soul_manager = SoulManager(soul_dir=soul_dir, active_soul=soul_name)

    # Memory
    memory = Memory(
        memory_dir=config.memory.memory_dir,
        consolidation_threshold=config.memory.consolidation_threshold,
        enabled=config.memory.enabled,
    )

    # Agent
    stream = not args.no_stream
    agent = Agent(
        model_provider=provider,
        soul_manager=soul_manager,
        memory=memory,
        stream=stream,
    )

    # Handle signals gracefully
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        print("\n\n🛑 Shutting down gracefully...")
        asyncio.create_task(agent.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    try:
        # Welcome message
        print(f"""
╔═══════════════════════════════════════════════════╗
║                                                   ║
║     🦎 GreenClaw CPU v{__version__}                       ║
║     The Ultimate Body for a SOUL                  ║
║     MIT License | Freedom is Key                  ║
║                                                   ║
║     Provider: {cfg:<36}║
║     Model:    {mn:<36}║
║     Soul:     {soul_name:<36}║
║     Port:     {port:<36}║
║                                                   ║
╚═══════════════════════════════════════════════════╝
""")

        await chat_loop(agent)

    finally:
        await agent.close()

    return 0


def main() -> int:
    """Main entry point."""
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        return 130


if __name__ == "__main__":
    sys.exit(main())
