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
- **An LLM provider** — pick one at runtime with `--provider`:
  - **OpenAI** (`gpt-4o` default) — needs `OPENAI_API_KEY`
  - **Anthropic / Claude** (`claude-opus-4-8` default) — needs `ANTHROPIC_API_KEY`, or sign in with SSO via `ant auth login`

## Installation

```bash
# Clone the repository
git clone https://github.com/brunoterkaly/mac-performance-triage.git
cd mac-performance-triage

# Install dependencies
pip install -r requirements.txt

# Configure whichever provider you'll use:
#   OpenAI:
export OPENAI_API_KEY="sk-..."
#   Anthropic / Claude — either an API key:
export ANTHROPIC_API_KEY="sk-ant-..."
#   ...or SSO, with no key to manage:
ant auth login
```

## Usage

```bash
# Choose a provider (required the first time; remembered afterward)
python3 mac-ai-healthcheck.py --provider anthropic
python3 mac-ai-healthcheck.py --provider openai

# Your last-used provider is remembered, so later runs can omit it
python3 mac-ai-healthcheck.py

# Pick a specific model for the chosen provider
python3 mac-ai-healthcheck.py --provider anthropic --model claude-opus-4-8
python3 mac-ai-healthcheck.py --provider openai --model gpt-4o-mini

# Save reports to a specific directory
python3 mac-ai-healthcheck.py --out-dir ~/Desktop/reports
```

On startup the tool prints a banner showing the active provider, model, and where
that choice came from (flag, env var, or remembered from your last run). Run
`python3 mac-ai-healthcheck.py --help` for copy-pasteable setup steps for each provider.

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | LLM provider: `openai` or `anthropic` | Last-used (remembered); required on first run |
| `--model` | Model for the chosen provider | `openai=gpt-4o`, `anthropic=claude-opus-4-8` (or `<PROVIDER>_MODEL` env / last-used) |
| `--out-dir` | Directory for output files | `.` (current directory) |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HEALTHCHECK_PROVIDER` | Default provider (`openai`/`anthropic`) when `--provider` is omitted |
| `OPENAI_API_KEY` | OpenAI API key (required for `--provider openai`) |
| `ANTHROPIC_API_KEY` | Anthropic API key (for `--provider anthropic`; or use `ant auth login` SSO instead) |
| `OPENAI_MODEL` / `ANTHROPIC_MODEL` | Override the model for that provider without `--model` |

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
| `No provider selected` | Pass `--provider openai` or `--provider anthropic` (remembered afterward) |
| `OPENAI_API_KEY not set` | Run `export OPENAI_API_KEY="sk-..."` |
| `Anthropic authentication failed` | Run `ant auth login` (SSO), or `export ANTHROPIC_API_KEY="sk-ant-..."` |
| `openai` / `anthropic` module not found | Run `pip install -r requirements.txt` |
| Script timeout | Some system commands may be slow; retry or check Activity Monitor |
| Large capture output warning | Normal for busy systems; output is auto-truncated |

## Security & Privacy

- All diagnostics run **locally** on your Mac.
- Process names and system stats are sent to the **selected provider's** API (OpenAI or Anthropic) for analysis.
- No data is stored remotely beyond that provider's standard API data handling.
- Review the generated `.sh` script before running if you prefer manual control.

## License

[MIT](LICENSE)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
