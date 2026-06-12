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
- **OpenAI API key** (GPT-4o recommended)

## Installation

```bash
# Clone the repository
git clone https://github.com/brunoterkaly/mac-performance-triage.git
cd mac-performance-triage

# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your_api_key_here"
```

## Usage

```bash
# Run with defaults (gpt-4o model, output in current directory)
python3 mac-ai-healthcheck.py

# Specify a different model
python3 mac-ai-healthcheck.py --model gpt-4o-mini

# Save reports to a specific directory
python3 mac-ai-healthcheck.py --out-dir ~/Desktop/reports
```

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `--model` | OpenAI model to use | `gpt-4o` (or `OPENAI_MODEL` env var) |
| `--out-dir` | Directory for output files | `.` (current directory) |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | **(Required)** Your OpenAI API key |
| `OPENAI_MODEL` | Override the default model without using `--model` |

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
| `OPENAI_API_KEY not set` | Run `export OPENAI_API_KEY="sk-..."` |
| `openai` module not found | Run `pip install -r requirements.txt` |
| Script timeout | Some system commands may be slow; retry or check Activity Monitor |
| Large capture output warning | Normal for busy systems; output is auto-truncated |

## Security & Privacy

- All diagnostics run **locally** on your Mac.
- Process names and system stats are sent to the OpenAI API for analysis.
- No data is stored remotely beyond OpenAI's standard API data handling.
- Review the generated `.sh` script before running if you prefer manual control.

## License

[MIT](LICENSE)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
