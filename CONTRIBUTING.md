# Contributing

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork this repository
2. Clone your fork: `git clone https://github.com/<your-username>/mac-performance-triage.git`
3. Create a feature branch: `git checkout -b my-feature`
4. Make your changes
5. Test locally: `python3 mac-ai-healthcheck.py`
6. Commit and push: `git push origin my-feature`
7. Open a Pull Request

## Guidelines

- Keep changes focused — one feature or fix per PR
- Test on macOS before submitting
- Follow existing code style (no linter configured yet — just match what's there)
- Update `README.md` if your change affects usage or setup

## Reporting Issues

Please include:
- macOS version (`sw_vers`)
- Python version (`python3 --version`)
- Full error output
- Steps to reproduce

## Ideas for Contributions

- Add support for additional AI providers (Anthropic, local models)
- Improve process name detection in `short_name()`
- Add a `--dry-run` flag to skip script execution
- Unit tests for parsing functions
- CI workflow for linting
