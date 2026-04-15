# GreenClaw CPU 🦎

**The Ultimate Body for a SOUL**

MIT License | Local-first AI Agent | Freedom is Key

---

## Install in One Command

```bash
curl -fsSL https://raw.githubusercontent.com/greench-ai/greenchclaw-cpu/main/install.sh | bash
```

**That's it.** Answer 3 questions, then start chatting.

### What happens next?

1. 🐣 **Answer 3 questions** — who you are, what your AI companion should be called, and how you want to run AI (local Ollama for free, or cloud APIs)
2. 🦎 **GreenClaw sets everything up** — writes your config, creates your personal Soul, pulls a model if needed
3. 💬 **Start chatting** — `greenchclaw` and you're live

### Ollama (free, local AI)

If you chose Ollama, make sure it's running first:

```bash
ollama serve
ollama pull llama3.2   # first time only
```

---

## What is GreenClaw?

GreenClaw CPU is a full-power AI agent that runs on **any machine** — no GPU needed. It works with local models (Ollama, Llamafile, LocalAI) **and** cloud APIs (OpenAI, Anthropic, OpenRouter). You configure everything. No artificial restrictions.

### Key Features

- 🖥️ **CPU-first**: Runs entirely on CPU with Ollama
- 🔓 **No lock-in**: Local models by default, cloud when you choose
- 🎭 **Swappable souls**: Change personality by swapping SOUL files
- 🧠 **Persistent memory**: Remembers conversations across sessions
- ⚡ **Streaming**: Real-time responses as they're generated
- 🔌 **Multi-instance**: Each version runs on its own port — run all GreenClaw versions simultaneously
- 📝 **MIT Licensed**: Full freedom to use, modify, distribute

## Quick Start

```bash
# One-command install (recommended)
curl -fsSL https://raw.githubusercontent.com/greench-ai/greenchclaw-cpu/main/install.sh | bash

# Re-run the setup wizard
greenchclaw --onboard

# Check system health
greenchclaw --health

# Show current config
greenchclaw --config

# Start chatting
greenchclaw

# Override options at runtime
greenchclaw --model openai --api-key sk-... --name gpt-4o
greenchclaw --port 51234
```

## Configuration

Edit `config.yaml` or use environment variables:

```yaml
model_provider: ollama
model_name: llama3.2
ollama_url: http://localhost:11434
soul_dir: ./souls
active_soul: default
server_port: 51234
server_host: 0.0.0.0
```

Or via environment:

```bash
export GREENCLAW_PROVIDER=openai
export GREENCLAW_MODEL=gpt-4o
export OPENAI_API_KEY=sk-...
export GREENCLAW_PORT=51234
```

## Soul System

Souls define identity, behavior, and memory. They're just markdown files:

```
souls/
└── default/
    ├── SOUL.md      # Core purpose and values
    ├── IDENTITY.md  # Who GreenClaw is
    ├── MEMORY.md    # Persistent memory
    ├── USER.md      # User preferences
    └── RULES.md     # Optional rules
```

Switch souls at runtime:

```
👤 You: /soul developer
✅ Switched to soul: developer
```

Create custom souls freely — Freedom is Key.

## Project Structure

```
greenchclaw-cpu/
├── src/
│   ├── main.py              # Entry point + chat loop
│   ├── config.py             # YAML + env config system
│   ├── models/
│   │   ├── base.py          # Abstract model interface
│   │   ├── ollama.py        # Ollama (OpenAI-compatible)
│   │   ├── openai.py        # OpenAI / OpenRouter / LocalAI
│   │   ├── anthropic.py     # Anthropic Claude API
│   │   └── factory.py       # Model factory
│   ├── soul/
│   │   ├── soul_manager.py  # Soul loading + switching
│   │   └── soul_files.py    # SOUL.md, IDENTITY.md, etc.
│   ├── memory/
│   │   ├── memory.py        # Conversation memory
│   │   └── consolidation.py # Auto-summarization
│   └── agent/
│       └── agent.py          # Core agent orchestration
├── souls/                    # Soul/personality files
├── tests/                    # Test suite
├── config.yaml              # Configuration
└── requirements.txt
```

## Command Line Options

```
python -m src.main [options]

Options:
  --model PROVIDER     Model provider (ollama, openai, anthropic, openrouter)
  --name MODEL        Model name
  --api-key KEY       API key for cloud providers
  --base-url URL      Custom API base URL
  --soul NAME         Active soul/personality
  --port PORT         Server port (default: 51234 for GreenClaw CPU)
  --host HOST         Server bind address (default: 0.0.0.0)
  --health-check      Check all systems
  --no-stream         Disable streaming responses
  --log-level LEVEL   Logging level (DEBUG, INFO, WARNING, ERROR)

Simultaneous instances:
  GreenClaw CPU:          --port 51234
  GreenClaw GPU:          --port 51235
  GreenClaw KidGuardian:  --port 51236
```

## Runtime Commands

When chatting, use these commands:

- `/soul <name>` — Switch to a different soul
- `/souls` — List available souls
- `/health` — Check system status
- `/clear` — Clear conversation memory
- `exit` / `quit` — End the session

## Adding New Model Providers

GreenClaw is extensible. To add a new provider:

1. Create `src/models/yourprovider.py` extending `ModelProvider`
2. Register it in `src/models/factory.py`

```python
from src.models.base import ModelProvider

class YourProvider(ModelProvider):
    async def generate(self, prompt, **kwargs):
        # Implement your provider
        pass

    async def chat(self, messages, **kwargs):
        # Implement your provider
        pass

    async def health_check(self):
        return True

# Register it
from src.models.factory import register_provider
register_provider("yourprovider", YourProvider)
```

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_soul_loading.py -v

# Run with coverage
pytest --cov=src tests/
```

## System Requirements

- Python 3.10+
- Ollama (for local mode)
- Any model that supports chat completions API

## Philosophy

**Freedom is Key.**

GreenClaw is designed to:
- Run on any machine, any budget
- Use any model the user chooses
- Never lock users into a specific provider
- Be fully transparent and controllable
- Remember everything important without being creepy

MIT License. Use it however you want.

---

**GreenClaw CPU** — The Ultimate Body for a SOUL.
