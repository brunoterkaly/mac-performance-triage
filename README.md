# Mac AI Performance Healthcheck

Mac AI Performance Healthcheck is an AI-powered macOS diagnostic tool. It identifies performance problems, creates a targeted data-collection script, analyzes the results, and generates an HTML optimization report.

## What It Does

The tool runs a five-phase pipeline:

1. **Triage** — Collects a quick local snapshot of CPU usage, memory, startup items, disk usage, memory pressure, thermal state, and LaunchAgents.
2. **AI Planner** — Reviews the triage data and creates a targeted Bash script for the processes and system areas that need deeper inspection.
3. **Execution** — Runs the generated capture script with output and timeout limits.
4. **AI Analyst** — Reviews the captured data and creates an HTML report with recommended fixes, commands, priorities, and estimated impact.
5. **Launch** — Opens the report in your default browser.

## Sample Output

The generated HTML report can include:

- An executive summary of the main performance problems
- Quick fixes with copy-and-paste Terminal commands
- A table of the highest CPU and memory consumers
- A startup-item review with disable or removal recommendations
- Memory, disk, Spotlight, and thermal analysis
- Process-specific findings
- A prioritized optimization plan

## Requirements

- **macOS**
- **Python 3.9 or later**
- At least one supported AI provider:
  - **Anthropic**
  - **OpenAI**
  - **Google Gemini**
  - **Ollama**, which runs models locally without a cloud API key

## Supported Providers

| Provider | Typical default model | Authentication |
|----------|-----------------------|----------------|
| Anthropic | `claude-opus-4-8` | API key, auth token, or Anthropic CLI sign-in |
| OpenAI | `gpt-4o` | API key |
| Google Gemini | `gemini-2.5-pro` | API key |
| Ollama | `llama3.1` | No cloud credentials required |

You can override the default model with `--model` or the provider-specific model environment variable.

## Provider Selection

You can select a provider with the `--provider` command-line option or the `PROVIDER` environment variable.

When no provider is selected explicitly, the tool checks the available credentials in this order:

| Priority | Condition | Provider |
|----------|-----------|----------|
| 1 | `--provider` or `PROVIDER` is set | Explicitly selected provider |
| 2 | Anthropic credentials are available | Anthropic |
| 3 | `OPENAI_API_KEY` is set | OpenAI |
| 4 | `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set | Gemini |
| 5 | No cloud credentials are available | Ollama |

Anthropic credentials may come from `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or a supported Anthropic CLI sign-in profile.

## Installation

Clone the repository and install its Python dependencies:

```bash
git clone https://github.com/brunoterkaly/mac-performance-triage.git
cd mac-performance-triage

python3 -m pip install -r requirements.txt
```

## Authentication

### Anthropic with an API key

```bash
export ANTHROPIC_API_KEY="your_api_key_here"

python3 mac-ai-healthcheck.py --provider anthropic
```

### Anthropic with an auth token

```bash
export ANTHROPIC_AUTH_TOKEN="your_auth_token_here"

python3 mac-ai-healthcheck.py --provider anthropic
```

### Anthropic with CLI or SSO authentication

Authenticate with the supported Anthropic CLI:

```bash
ant auth login
```

Then run:

```bash
python3 mac-ai-healthcheck.py --provider anthropic
```

The tool should allow the Anthropic SDK or CLI integration to resolve the active credentials instead of requiring `ANTHROPIC_API_KEY` in every case.

### OpenAI

```bash
export OPENAI_API_KEY="your_api_key_here"

python3 mac-ai-healthcheck.py --provider openai
```

### Google Gemini

```bash
export GEMINI_API_KEY="your_api_key_here"

python3 mac-ai-healthcheck.py --provider gemini
```

You may also use `GOOGLE_API_KEY` when supported by your Google SDK configuration.

## Running Locally with Ollama

Ollama runs the model on your Mac, so no cloud API key is required.

Install Ollama, start its server, and download a model:

```bash
ollama serve
ollama pull llama3.1
```

Run the healthcheck:

```bash
python3 mac-ai-healthcheck.py \
  --provider ollama \
  --model llama3.1
```

Local models may produce simpler capture scripts and reports than larger cloud models.

To use a different Ollama server:

```bash
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```

## Usage

Run with automatic provider selection:

```bash
python3 mac-ai-healthcheck.py
```

Select a provider explicitly:

```bash
python3 mac-ai-healthcheck.py --provider anthropic
python3 mac-ai-healthcheck.py --provider openai
python3 mac-ai-healthcheck.py --provider gemini
python3 mac-ai-healthcheck.py --provider ollama
```

Select a specific model:

```bash
python3 mac-ai-healthcheck.py \
  --provider anthropic \
  --model claude-sonnet-4-6
```

```bash
python3 mac-ai-healthcheck.py \
  --provider openai \
  --model gpt-4o-mini
```

```bash
python3 mac-ai-healthcheck.py \
  --provider ollama \
  --model llama3.1
```

Save reports to a specific directory:

```bash
python3 mac-ai-healthcheck.py \
  --out-dir ~/Desktop/reports
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--provider` | Provider: `anthropic`, `openai`, `gemini`, or `ollama` | Automatic selection |
| `--model` | Model used by the selected provider | Provider default |
| `--out-dir` | Directory for generated files | Current directory |

The automatic provider order is:

```text
Anthropic → OpenAI → Gemini → Ollama
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_AUTH_TOKEN` | Anthropic authentication token |
| `OPENAI_API_KEY` | OpenAI API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_API_KEY` | Alternate Google API key variable |
| `PROVIDER` | Select `anthropic`, `openai`, `gemini`, or `ollama` |
| `ANTHROPIC_MODEL` | Override the default Anthropic model |
| `OPENAI_MODEL` | Override the default OpenAI model |
| `GEMINI_MODEL` | Override the default Gemini model |
| `OLLAMA_MODEL` | Override the default Ollama model |
| `OLLAMA_BASE_URL` | Ollama server URL; defaults to `http://localhost:11434/v1` |

## Output Files

Each run creates three timestamped files:

| File | Description |
|------|-------------|
| `dynamic_capture_<timestamp>.sh` | AI-generated diagnostic capture script |
| `capture_output_<timestamp>.txt` | Raw output from the capture script |
| `final_analysis_<timestamp>.html` | Complete HTML performance report |

## How It Works

```text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Local Triage   │────▶│  AI Plans Script │────▶│  Execute Script │
│  ps, vm_stat,   │     │  Targeted Bash   │     │  Bounded I/O    │
│  disk, thermal  │     └──────────────────┘     └────────┬────────┘
└─────────────────┘                                       │
                                                          ▼
                         ┌──────────────────┐     ┌─────────────────┐
                         │ Open in Browser  │◀────│ AI Generates    │
                         │                  │     │ HTML Report     │
                         └──────────────────┘     └─────────────────┘
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Provider API key is missing | Set the appropriate key, choose another provider, or use Ollama |
| Anthropic authentication fails | Set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`, or run `ant auth login` |
| Python provider module is missing | Run `python3 -m pip install -r requirements.txt` |
| Ollama connection is refused | Run `ollama serve` and confirm that the selected model is installed |
| Ollama model is missing | Run `ollama pull <model-name>` |
| Generated script times out | Retry or check Activity Monitor for blocked or overloaded processes |
| Capture output is large | This can happen on busy systems; the tool limits or truncates excessive output |

## Security and Privacy

All system-diagnostic commands run locally on your Mac.

When you use Anthropic, OpenAI, or Gemini, selected process information and system statistics are sent to that provider for analysis. The provider handles that data according to its own service terms and data policies.

When you use Ollama, the model runs locally and diagnostic data does not need to leave your Mac.

The generated Bash script may run system-inspection commands. Review the generated `.sh` file before running it when you want manual control over the commands.

Do not store API keys, access tokens, or other credentials in the repository.

## License

This project is licensed under the [MIT License](LICENSE).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change.