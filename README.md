# Mac AI Performance Healthcheck

An AI-powered macOS performance diagnostic tool that triages system issues, generates targeted capture scripts, and produces a comprehensive HTML optimization report — all automatically.

## What It Does

This tool runs a **5-phase pipeline**:

1. **Triage** — Collects a fast local snapshot of CPU, memory, startup items, disk usage, memory pressure, thermal state, and LaunchAgents.
2. **AI Pass 1 (Planner)** — Analyzes the triage data and generates a custom Bash script targeting the specific processes causing issues.
3. **Execution** — Runs the AI-generated capture script with enforced output limits.
4. **AI Pass 2 (Analyst)** — Analyzes the deep capture output and generates a styled HTML report with actionable fix commands and per-item impact estimates.
5. **Launch** — Opens the report in your default browser.

## Sample Output

The generated HTML report includes:

- Executive summary of performance bottlenecks
- Quick wins with copy-paste terminal commands
- Top resource bottlenecks table (CPU%, MEM%, severity)
- Startup item audit with disable/remove recommendations
- Memory, disk, Spotlight, and thermal analysis
- Process-specific deep dives
- Prioritized optimization roadmap

## Requirements

- **macOS** (uses macOS-specific system commands)
- **Python 3.9+**
- **One of the supported AI providers:**
  - **Anthropic** (Claude Opus 4.8 — the default)
  - **OpenAI** (GPT-4o)
  - **Google Gemini** (Gemini 2.5 Pro)
  - **Ollama** — run a model **fully locally**, no API key, no cloud

## Provider Selection

The tool works with **Anthropic (Claude)**, **OpenAI (GPT)**, **Google (Gemini)**,
or **Ollama (local models)**. It picks a provider automatically based on which API
key is set, and falls back to a fully local Ollama model when no cloud key is
present. You can always force a choice with `--provider` or the `PROVIDER` env var.

| Situation | Provider used |
|-----------|---------------|
| `--provider` / `PROVIDER` is set | That provider (explicit) |
| `ANTHROPIC_API_KEY` is set | Anthropic |
| else `OPENAI_API_KEY` is set | OpenAI |
| else `GEMINI_API_KEY` / `GOOGLE_API_KEY` is set | Gemini |
| no cloud key at all | Ollama (local) |

## Installation

```bash
# Clone the repository
git clone https://github.com/alkari/mac-performance-triage.git
cd mac-performance-triage

# Install dependencies (bundles all provider SDKs)
pip install -r requirements.txt

# Set the API key for whichever cloud provider you want to use
export ANTHROPIC_API_KEY="your_api_key_here"   # Claude (default)
export OPENAI_API_KEY="your_api_key_here"      # GPT
export GEMINI_API_KEY="your_api_key_here"      # Gemini
```

### Running locally with Ollama (no API key)

```bash
# Install Ollama from https://ollama.com, then:
ollama serve            # start the local server
ollama pull llama3.1    # pull a model (one time)

python3 mac-ai-healthcheck.py --provider ollama --model llama3.1
```

> Local models are smaller than frontier cloud models; the generated capture
> script and HTML report may be simpler. Point at a non-default host with the
> `OLLAMA_BASE_URL` env var (default `http://localhost:11434/v1`).

## Usage

```bash
# Run with defaults (auto-detect provider; Claude/claude-opus-4-8 if available)
python3 mac-ai-healthcheck.py

# Force a specific provider
python3 mac-ai-healthcheck.py --provider openai
python3 mac-ai-healthcheck.py --provider gemini
python3 mac-ai-healthcheck.py --provider ollama --model llama3.1

# Pick a specific model (uses the matching provider's SDK)
python3 mac-ai-healthcheck.py --model claude-sonnet-4-6
python3 mac-ai-healthcheck.py --provider openai --model gpt-4o-mini

# Save reports to a specific directory
python3 mac-ai-healthcheck.py --out-dir ~/Desktop/reports
```

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | AI provider: `anthropic`, `openai`, `gemini`, or `ollama` | auto-detect (Anthropic > OpenAI > Gemini > Ollama) |
| `--model` | Model to use | provider default (`claude-opus-4-8` / `gpt-4o` / `gemini-2.5-pro` / `llama3.1`) |
| `--out-dir` | Directory for output files | `.` (current directory) |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required for the Anthropic provider) |
| `OPENAI_API_KEY` | Your OpenAI API key (required for the OpenAI provider) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Your Google AI key (required for the Gemini provider) |
| `PROVIDER` | Force a provider (`anthropic`, `openai`, `gemini`, `ollama`) without `--provider` |
| `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `GEMINI_MODEL` / `OLLAMA_MODEL` | Override the default model per provider |
| `OLLAMA_BASE_URL` | Ollama server URL (default `http://localhost:11434/v1`) |

## Output Files

Each run produces three timestamped files:

| File | Description |
|------|-------------|
| `dynamic_capture_<timestamp>.sh` | AI-generated targeted capture script |
| `capture_output_<timestamp>.txt` | Raw output from the capture script |
| `final_analysis_<timestamp>.html` | Full HTML optimization report |

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Local Triage   │────▶│  AI Plans Script │────▶│  Execute Script │
│  (ps, vm_stat,  │     │  (targeted bash) │     │  (bounded I/O)  │
│   disk, thermal)│     └──────────────────┘     └────────┬────────┘
└─────────────────┘                                       │
                                                          ▼
                         ┌──────────────────┐     ┌─────────────────┐
                         │  Open in Browser │◀────│  AI Generates   │
                         │                  │     │  HTML Report    │
                         └──────────────────┘     └─────────────────┘
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `..._API_KEY not set` | Set the key for your chosen provider, or pick another with `--provider` |
| `anthropic` / `openai` / `google-genai` module not found | Run `pip install -r requirements.txt` |
| Ollama: connection refused | Start the server with `ollama serve` and pull the model (`ollama pull <model>`) |
| Script timeout | Some system commands may be slow; retry or check Activity Monitor |
| Large capture output warning | Normal for busy systems; output is auto-truncated |

## Security & Privacy

- All diagnostics run **locally** on your Mac.
- With a **cloud provider** (Anthropic, OpenAI, Gemini), process names and system stats are sent to that provider's API for analysis, subject to its standard data handling.
- With **Ollama**, the model runs entirely on your machine — **no data leaves your Mac**.
- Review the generated `.sh` script before running if you prefer manual control.

## License

[MIT](LICENSE)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
