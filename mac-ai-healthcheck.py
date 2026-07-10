#!/usr/bin/env python3
"""
Mac AI Diagnostic Pipeline: Triage -> Dynamic Capture -> Deep HTML Analysis

What this does:
1. Triage: Collects a fast local snapshot of Mac process CPU, memory, startup items,
   disk usage, memory pressure, thermal state, and LaunchAgents.
2. AI Pass 1 (Planner): Analyzes the triage and generates a custom Bash script
   targeting the specific processes acting up. It is strictly prompted to bound output.
3. Execution: Runs the AI-generated targeted Bash script and enforces a character limit.
4. AI Pass 2 (Analyst): Analyzes the deep capture output and generates a styled HTML
   report with startup item audit, specific fix commands, and impact estimates.
5. Launch: Opens the generated report in the default browser.

Setup:
    python3 -m pip install -r requirements.txt

    # Anthropic: choose an API key, auth token, or SSO sign-in
    export ANTHROPIC_API_KEY="sk-ant-..."
    export ANTHROPIC_AUTH_TOKEN="..."
    ant auth login

    # Other cloud providers
    export OPENAI_API_KEY="sk-..."
    export GEMINI_API_KEY="..."

    # Local Ollama
    ollama serve
    ollama pull llama3.1

Run:
    python3 mac-ai-healthcheck.py
    python3 mac-ai-healthcheck.py --provider anthropic
    python3 mac-ai-healthcheck.py --provider openai
    python3 mac-ai-healthcheck.py --provider gemini
    python3 mac-ai-healthcheck.py --provider ollama --model llama3.1
"""

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import platform
import re
import subprocess
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
    from anthropic import Anthropic
except ImportError:
    anthropic = None
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai as google_genai
except ImportError:
    google_genai = None

# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
WHITE = "\033[37m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Sticky last-used provider/model memory. Failure to read or write this file
# never prevents the diagnostic from running.
CONFIG_DIR = Path(
    os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config")
) / "mac-ai-healthcheck"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Ollama exposes an OpenAI-compatible API on this URL by default.
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1",
)

# The planner produces a bounded Bash script. The analyst may produce a long HTML report.
PLANNER_MAX_TOKENS = 16000
ANALYST_MAX_TOKENS = 64000


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=timeout,
        )
        if result.stdout.strip():
            return result.stdout.strip()
        if result.stderr.strip():
            return result.stderr.strip()
        return ""
    except subprocess.TimeoutExpired:
        return f"[command timed out: {' '.join(cmd)}]"
    except Exception as e:
        return f"[command failed: {' '.join(cmd)}: {e}]"


def color_for_percent(value):
    if value >= 40: return RED
    if value >= 15: return YELLOW
    return GREEN


def severity_label(value):
    if value >= 40: return f"{RED}HIGH{RESET}"
    if value >= 15: return f"{YELLOW}MED {RESET}"
    return f"{GREEN}LOW {RESET}"


def mem_severity_label(value):
    if value >= 10: return f"{RED}HIGH{RESET}"
    if value >= 4:  return f"{YELLOW}MED {RESET}"
    return f"{GREEN}LOW {RESET}"


def short_name(command):
    command = command.strip()
    if not command: return "unknown"
    lower = command.lower()

    if "microsoft teams" in lower or "msteams" in lower: return "Microsoft Teams"
    if "windowserver" in lower: return "WindowServer"
    if "mds_stores" in lower: return "Spotlight mds_stores"
    if re.search(r"/support/mds(\s|$)", lower): return "Spotlight mds"
    if "mdworker" in lower: return "Spotlight mdworker"
    if "corespotlightd" in lower: return "CoreSpotlight"
    if "onedrive" in lower: return "OneDrive"
    if "audacity" in lower: return "Audacity"
    if "slack" in lower: return "Slack"
    if "outlook" in lower: return "Outlook"
    if "microsoft edge" in lower: return "Microsoft Edge"
    if "visual studio code" in lower or "code helper" in lower: return "VS Code"
    if "xcode" in lower or "sourcekit" in lower or "lldb-rpc-server" in lower: return "Xcode"
    if "finder" in lower: return "Finder"
    if "dock.app" in lower: return "Dock"
    if "xprotectservice" in lower or "xprotectd" in lower: return "xprotectd"
    if "vtdecoderxpcservice" in lower: return "VTDecoderXPCService"
    if lower.endswith("python") or "/python" in lower: return "Python"
    if "iterm" in lower: return "iTerm2"
    if "zoom" in lower: return "Zoom"
    if "dropbox" in lower: return "Dropbox"
    if "1password" in lower: return "1Password"
    if "alfred" in lower: return "Alfred"
    if "bartender" in lower: return "Bartender"
    if "cleanmymac" in lower: return "CleanMyMac"
    if "little snitch" in lower: return "Little Snitch"
    if "logi" in lower: return "Logi Options"
    if "steam" in lower: return "Steam"
    if "chrome" in lower: return "Google Chrome"
    if "firefox" in lower: return "Firefox"
    if "safari" in lower: return "Safari"
    if "notion" in lower: return "Notion"
    if "spotify" in lower: return "Spotify"

    return command.split("/")[-1].split()[0]


def parse_ps(output):
    rows = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line: continue
        parts = line.split(None, 4)
        if len(parts) < 5: continue
        pid, pcpu, pmem, etime, command = parts
        try:
            cpu, mem = float(pcpu), float(pmem)
        except ValueError:
            continue
        rows.append({
            "pid": pid, "cpu": cpu, "mem": mem, "etime": etime,
            "command": command, "name": short_name(command),
        })
    return rows


def group_by_name(rows, key):
    grouped = defaultdict(float)
    for row in rows:
        grouped[row["name"]] += row[key]
    return sorted(grouped.items(), key=lambda x: x[1], reverse=True)


def get_login_items():
    raw = run_cmd(
        ["osascript", "-e", 'tell application "System Events" to get the name of every login item'],
        timeout=8,
    )
    if raw and not raw.startswith("[command"):
        items = [i.strip() for i in raw.split(",") if i.strip()]
        return items
    return []


def collect_launch_agents():
    """List third-party LaunchAgents and LaunchDaemons (non-Apple)."""
    results = {"user_agents": [], "system_agents": [], "system_daemons": []}
    locations = [
        (Path.home() / "Library/LaunchAgents", "user_agents"),
        (Path("/Library/LaunchAgents"), "system_agents"),
        (Path("/Library/LaunchDaemons"), "system_daemons"),
    ]
    for base_path, key in locations:
        if base_path.exists():
            try:
                plists = sorted(base_path.glob("*.plist"))
                for p in plists[:60]:
                    label = p.stem
                    # Separate Apple vs third-party
                    is_apple = label.startswith("com.apple.") or label.startswith("com.openssh")
                    if not is_apple:
                        results[key].append(label)
            except PermissionError:
                pass
    return results


def get_launchctl_third_party():
    """Active launchd services that are NOT Apple services."""
    raw = run_cmd(["launchctl", "list"], timeout=10)
    lines = []
    for line in raw.splitlines()[1:]:  # skip header
        parts = line.split(None, 2)
        if len(parts) == 3:
            pid, _, label = parts
            if not label.startswith("com.apple.") and not label.startswith("0x"):
                running = pid != "-"
                lines.append({"pid": pid, "label": label, "running": running})
    return lines[:50]


def get_disk_metrics():
    return {
        "df_h": run_cmd(["df", "-h", "/"], timeout=5),
        "iostat": run_cmd(["iostat", "-d", "disk0", "1", "1"], timeout=8),
        "available_gb": _parse_disk_available(),
    }


def _parse_disk_available():
    try:
        out = run_cmd(["df", "-k", "/"], timeout=5)
        for line in out.splitlines():
            if line.startswith("/"):
                parts = line.split()
                if len(parts) >= 4:
                    available_kb = int(parts[3])
                    return round(available_kb / 1_048_576, 1)
    except Exception:
        pass
    return None


def _extract_swap_used() -> str:
    """Parse 'Swapouts' or look for swap line from sysctl."""
    try:
        swap_raw = run_cmd(["sysctl", "vm.swapusage"], timeout=5)
        if swap_raw and "used" in swap_raw:
            return swap_raw
    except Exception:
        pass
    return "n/a"


def get_extra_system_metrics():
    vm_stat = run_cmd(["vm_stat"])
    return {
        "timestamp_local": dt.datetime.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "sw_vers": run_cmd(["sw_vers"]),
        "uptime": run_cmd(["uptime"]),
        "memory_pressure": run_cmd(["memory_pressure"], timeout=15),
        "vm_stat": vm_stat,
        "swap_usage": _extract_swap_used(),
        "thermal_state": run_cmd(["pmset", "-g", "therm"]),
        "battery": run_cmd(["pmset", "-g", "batt"], timeout=5),
    }


def collect_diagnostics():
    ps_out = run_cmd(["ps", "-Ao", "pid=,pcpu=,pmem=,etime=,command="])
    rows = parse_ps(ps_out)
    cpu_grouped = group_by_name(rows, "cpu")
    mem_grouped = group_by_name(rows, "mem")
    cpu_map = dict(cpu_grouped)
    mem_map = dict(mem_grouped)

    login_items = get_login_items()
    launch_agents = collect_launch_agents()
    launchctl_third_party = get_launchctl_third_party()
    disk_metrics = get_disk_metrics()

    spotlight_total = sum(cpu_map.get(n, 0) for n in [
        "Spotlight mdworker", "Spotlight mds", "Spotlight mds_stores", "CoreSpotlight"
    ])
    ui_total = sum(cpu_map.get(n, 0) for n in [
        "WindowServer", "WindowManager", "Finder", "Dock"
    ])

    return {
        "rows": rows,
        "cpu_grouped": cpu_grouped,
        "mem_grouped": mem_grouped,
        "cpu_map": cpu_map,
        "mem_map": mem_map,
        "login_items": login_items,
        "launch_agents": launch_agents,
        "launchctl_third_party": launchctl_third_party,
        "disk_metrics": disk_metrics,
        "summary_metrics": {
            "spotlight_cpu_total": round(spotlight_total, 1),
            "ui_display_cpu_total": round(ui_total, 1),
            "process_count": len(rows),
            "login_item_count": len(login_items),
            "third_party_launch_agents": len(launch_agents["user_agents"]) + len(launch_agents["system_agents"]),
            "third_party_daemons": len(launch_agents["system_daemons"]),
        },
        "system_metrics": get_extra_system_metrics(),
    }


def _bar(value, max_value=100, width=20):
    filled = int(round(value / max_value * width))
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


def _parse_memory_pressure_level(mp_output: str) -> str:
    lower = mp_output.lower()
    if "critical" in lower: return f"{RED}CRITICAL{RESET}"
    if "warn" in lower:     return f"{YELLOW}WARNING{RESET}"
    if "normal" in lower:   return f"{GREEN}NORMAL{RESET}"
    return f"{DIM}unknown{RESET}"


def _parse_thermal_level(thermal_output: str) -> str:
    lower = thermal_output.lower()
    if "reducespeedyes" in lower or "cpuspeedlimit" in lower: return f"{RED}THROTTLED{RESET}"
    if "normal" in lower:  return f"{GREEN}NORMAL{RESET}"
    return f"{DIM}{thermal_output[:40]}{RESET}"


def render_local_report(diag):
    sm = diag["system_metrics"]
    summ = diag["summary_metrics"]
    now = sm.get("timestamp_local", "")
    uptime = sm.get("uptime", "")
    sw_vers_lines = sm.get("sw_vers", "")
    os_line = next((l.split(":")[-1].strip() for l in sw_vers_lines.splitlines() if "ProductVersion" in l), "")
    product_name = next((l.split(":")[-1].strip() for l in sw_vers_lines.splitlines() if "ProductName" in l), "macOS")
    arch = sm.get("machine", platform.machine())

    mem_pressure_raw = sm.get("memory_pressure", "")
    thermal_raw = sm.get("thermal_state", "")
    swap_raw = sm.get("swap_usage", "n/a")

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}{CYAN}  Mac Diagnostic Triage  {now}{RESET}")
        print(f"{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"  {BOLD}OS:{RESET}      {product_name} {os_line}  |  {arch}")
        print(f"  {BOLD}Uptime:{RESET}  {uptime}")
        print(f"  {BOLD}Procs:{RESET}   {summ['process_count']} running")
        disk_avail = diag["disk_metrics"].get("available_gb")
        if disk_avail is not None:
            disk_color = RED if disk_avail < 10 else YELLOW if disk_avail < 30 else GREEN
            print(f"  {BOLD}Disk:{RESET}    {disk_color}{disk_avail} GB free{RESET}")

        # System health indicators
        print(f"\n{BOLD}  SYSTEM HEALTH{RESET}")
        print(f"  Memory Pressure : {_parse_memory_pressure_level(mem_pressure_raw)}")
        print(f"  Thermal State   : {_parse_thermal_level(thermal_raw)}")
        if swap_raw and "n/a" not in swap_raw:
            print(f"  Swap Usage      : {YELLOW}{swap_raw}{RESET}")

        # Top CPU consumers
        print(f"\n{BOLD}  TOP CPU CONSUMERS{RESET}  (grouped by app)")
        print(f"  {'SEV ':5} {'App':<28} {'CPU%':>6}  {'Bar'}")
        print(f"  {'-'*58}")
        for name, value in diag["cpu_grouped"][:18]:
            sev = severity_label(value)
            col = color_for_percent(value)
            bar = _bar(value, max_value=60, width=16)
            print(f"  {sev} {name:<28} {col}{value:6.1f}%{RESET}  {col}{bar}{RESET}")

        # Top memory consumers
        print(f"\n{BOLD}  TOP MEMORY CONSUMERS{RESET}  (% of RAM)")
        print(f"  {'SEV ':5} {'App':<28} {'MEM%':>6}  {'Bar'}")
        print(f"  {'-'*58}")
        for name, value in diag["mem_grouped"][:12]:
            sev = mem_severity_label(value)
            col = color_for_percent(value * 3)  # scale mem to same visual range
            bar = _bar(value, max_value=20, width=16)
            print(f"  {sev} {name:<28} {col}{value:6.1f}%{RESET}  {col}{bar}{RESET}")

        # Startup items
        login_items = diag.get("login_items", [])
        la = diag.get("launch_agents", {})
        lc = diag.get("launchctl_third_party", [])

        print(f"\n{BOLD}  STARTUP ITEMS{RESET}")
        if login_items:
            print(f"  {YELLOW}Login Items ({len(login_items)}):{RESET}")
            for item in login_items:
                print(f"    • {item}")
        else:
            print(f"  Login Items: {DIM}(none or not accessible){RESET}")

        user_agents = la.get("user_agents", [])
        sys_agents  = la.get("system_agents", [])
        sys_daemons = la.get("system_daemons", [])

        if user_agents:
            print(f"\n  {YELLOW}User LaunchAgents ({len(user_agents)}):{RESET}")
            for a in user_agents[:20]:
                print(f"    • {a}")
            if len(user_agents) > 20:
                print(f"    ... and {len(user_agents) - 20} more")

        if sys_agents:
            print(f"\n  {YELLOW}System LaunchAgents ({len(sys_agents)}):{RESET}")
            for a in sys_agents[:15]:
                print(f"    • {a}")
            if len(sys_agents) > 15:
                print(f"    ... and {len(sys_agents) - 15} more")

        if sys_daemons:
            print(f"\n  {YELLOW}System LaunchDaemons ({len(sys_daemons)}):{RESET}")
            for d in sys_daemons[:15]:
                print(f"    • {d}")
            if len(sys_daemons) > 15:
                print(f"    ... and {len(sys_daemons) - 15} more")

        running_third_party = [s for s in lc if s["running"]]
        if running_third_party:
            print(f"\n  {MAGENTA}Active Third-Party launchd Services ({len(running_third_party)}):{RESET}")
            for svc in running_third_party[:20]:
                print(f"    PID {svc['pid']:>6}  {svc['label']}")

        # Quick flags
        flags = []
        spotlight_cpu = summ.get("spotlight_cpu_total", 0)
        if spotlight_cpu > 20:
            flags.append(f"{RED}[!] Spotlight indexing at {spotlight_cpu:.1f}% CPU — add exclusions or re-index{RESET}")
        if diag["cpu_map"].get("Microsoft Teams", 0) > 30:
            flags.append(f"{RED}[!] Microsoft Teams is a heavy CPU consumer — disable auto-start if not needed{RESET}")
        if diag["cpu_map"].get("OneDrive", 0) > 10:
            flags.append(f"{YELLOW}[!] OneDrive elevated CPU — check sync backlog{RESET}")
        if len(login_items) > 8:
            flags.append(f"{YELLOW}[!] {len(login_items)} login items — review and prune{RESET}")
        if len(user_agents) > 10:
            flags.append(f"{YELLOW}[!] {len(user_agents)} user LaunchAgents — several may be safe to disable{RESET}")
        if diag["disk_metrics"].get("available_gb", 999) < 10:
            flags.append(f"{RED}[!] Low disk space — less than 10 GB free{RESET}")
        mem_pressure_lower = mem_pressure_raw.lower()
        if "critical" in mem_pressure_lower or "warn" in mem_pressure_lower:
            flags.append(f"{RED}[!] Memory pressure is elevated — close unused apps or upgrade RAM{RESET}")

        if flags:
            print(f"\n{BOLD}  QUICK FLAGS{RESET}")
            for f in flags:
                print(f"  {f}")

        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}\n")

    return buffer.getvalue()


def make_json_safe_diag(diag):
    top_processes = sorted(diag["rows"], key=lambda r: r["cpu"], reverse=True)[:30]
    la = diag.get("launch_agents", {})
    return {
        "summary_metrics": diag["summary_metrics"],
        "top_cpu_by_app": diag["cpu_grouped"][:20],
        "top_mem_by_app": diag["mem_grouped"][:15],
        "top_processes": [
            {"pid": r["pid"], "cpu_percent": r["cpu"], "mem_percent": r["mem"], "name": r["name"]}
            for r in top_processes
        ],
        "system_metrics": diag["system_metrics"],
        "startup": {
            "login_items": diag.get("login_items", []),
            "user_launch_agents": la.get("user_agents", [])[:40],
            "system_launch_agents": la.get("system_agents", [])[:20],
            "system_launch_daemons": la.get("system_daemons", [])[:20],
            "active_third_party_services": [
                {"pid": s["pid"], "label": s["label"]}
                for s in diag.get("launchctl_third_party", []) if s["running"]
            ][:30],
        },
        "disk": diag.get("disk_metrics", {}),
    }


# ==============================================================================
# LLM PROVIDERS
# ==============================================================================
def fail(message: str):
    print(f"{RED}Error: {message}{RESET}")
    sys.exit(1)


PROVIDER_CLASSES = {}


def register_provider(cls):
    PROVIDER_CLASSES[cls.name] = cls
    return cls


class LLMProvider:
    """Common completion interface used by both AI phases."""

    name = "base"
    default_model = None
    setup_help = ""

    def __init__(self, model: str):
        self.model = model

    def complete(
        self,
        prompt,
        *,
        temperature=None,
        max_tokens=8192,
        stream=False,
        system=None,
    ) -> str:
        raise NotImplementedError


@register_provider
class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-4-8"
    setup_help = textwrap.dedent("""\
        Anthropic / Claude setup — choose one:
          - SSO sign-in:
              brew install anthropics/tap/ant
              ant auth login
          - API key:
              export ANTHROPIC_API_KEY='sk-ant-...'
          - Auth token:
              export ANTHROPIC_AUTH_TOKEN='...'
          Optional model override: --model or ANTHROPIC_MODEL
          Default model: claude-opus-4-8""")

    def __init__(self, model):
        super().__init__(model)
        if Anthropic is None:
            fail(
                "Anthropic SDK not installed. "
                "Run: python3 -m pip install --upgrade anthropic\n\n"
                + self.setup_help
            )

        # The zero-argument client allows the SDK to resolve an API key,
        # auth token, or supported CLI/SSO credentials.
        self.client = Anthropic()

    def complete(
        self,
        prompt,
        *,
        temperature=None,
        max_tokens=8192,
        stream=False,
        system=None,
    ):
        # Adaptive thinking and temperature cannot be used together, so
        # temperature is intentionally ignored for Anthropic.
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        if system:
            kwargs["system"] = system

        try:
            if stream:
                with self.client.messages.stream(**kwargs) as response_stream:
                    message = response_stream.get_final_message()
            else:
                message = self.client.messages.create(**kwargs)

        except anthropic.AuthenticationError as exc:
            fail(
                f"Anthropic authentication failed ({str(exc)[:100]}).\n\n"
                + self.setup_help
            )

        except TypeError as exc:
            if "authentication" in str(exc).lower():
                fail(
                    "No Anthropic credentials were found.\n\n"
                    + self.setup_help
                )
            raise

        return "".join(
            block.text
            for block in message.content
            if getattr(block, "type", None) == "text"
        )


@register_provider
class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"
    setup_help = textwrap.dedent("""\
        OpenAI setup:
          1. Export an API key:
               export OPENAI_API_KEY='sk-...'
          2. Optional model override: --model or OPENAI_MODEL
             Default model: gpt-4o""")

    def __init__(self, model):
        super().__init__(model)
        if OpenAI is None:
            fail(
                "OpenAI SDK not installed. "
                "Run: python3 -m pip install --upgrade openai\n\n"
                + self.setup_help
            )
        if not os.getenv("OPENAI_API_KEY"):
            fail("OPENAI_API_KEY is not set.\n\n" + self.setup_help)
        self.client = OpenAI()

    def complete(
        self,
        prompt,
        *,
        temperature=None,
        max_tokens=8192,
        stream=False,
        system=None,
    ):
        messages = []

        if system:
            messages.append({
                "role": "system",
                "content": system,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        # GPT-4o rejects completion limits above 16,384 tokens.
        # Cap only the OpenAI request so providers with larger limits are unaffected.
        safe_max_tokens = min(max_tokens, 16_384)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": safe_max_tokens,
        }

        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


@register_provider
class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.5-pro"
    setup_help = textwrap.dedent("""\
        Google Gemini setup:
          1. Export an API key:
               export GEMINI_API_KEY='...'
             or:
               export GOOGLE_API_KEY='...'
          2. Optional model override: --model or GEMINI_MODEL
             Default model: gemini-2.5-pro""")

    def __init__(self, model):
        super().__init__(model)
        if google_genai is None:
            fail(
                "Google Gemini SDK not installed. "
                "Run: python3 -m pip install --upgrade google-genai\n\n"
                + self.setup_help
            )
        if not (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        ):
            fail("No Gemini API key was found.\n\n" + self.setup_help)
        self.client = google_genai.Client()

    def complete(
        self,
        prompt,
        *,
        temperature=None,
        max_tokens=8192,
        stream=False,
        system=None,
    ):
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        config = {"max_output_tokens": max_tokens}
        if temperature is not None:
            config["temperature"] = temperature

        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=config,
        )
        return response.text or ""


@register_provider
class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "llama3.1"
    setup_help = textwrap.dedent("""\
        Ollama setup:
          1. Start the server:
               ollama serve
          2. Download a model:
               ollama pull llama3.1
          3. Optional model override: --model or OLLAMA_MODEL
             Default model: llama3.1""")

    def __init__(self, model):
        super().__init__(model)
        if OpenAI is None:
            fail(
                "The OpenAI SDK is required for the Ollama client. "
                "Run: python3 -m pip install --upgrade openai\n\n"
                + self.setup_help
            )
        self.client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",
        )

    def complete(
        self,
        prompt,
        *,
        temperature=None,
        max_tokens=8192,
        stream=False,
        system=None,
    ):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            fail(
                f"Could not connect to Ollama or run model '{self.model}': {exc}\n\n"
                + self.setup_help
            )
        return response.choices[0].message.content or ""


PROVIDERS = tuple(PROVIDER_CLASSES)
DEFAULT_MODELS = {
    name: provider_class.default_model
    for name, provider_class in PROVIDER_CLASSES.items()
}


def build_provider(provider_name: str, model: str) -> LLMProvider:
    provider_class = PROVIDER_CLASSES.get(provider_name)
    if provider_class is None:
        fail(
            f"Unknown provider '{provider_name}'. "
            f"Choose from: {', '.join(PROVIDERS)}"
        )
    return provider_class(model)


# ------------------------------------------------------------------------------
# Provider selection and remembered settings
# ------------------------------------------------------------------------------
def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(config, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def resolve_provider_and_model(args, config):
    """Resolve the provider and model using flags, settings, credentials, and defaults."""

    if args.provider:
        provider = args.provider
        source = "--provider flag"
    elif os.getenv("PROVIDER"):
        provider = os.getenv("PROVIDER", "").lower()
        source = "PROVIDER environment variable"
    elif os.getenv("HEALTHCHECK_PROVIDER"):
        provider = os.getenv("HEALTHCHECK_PROVIDER", "").lower()
        source = "HEALTHCHECK_PROVIDER environment variable"
    elif config.get("provider"):
        provider = str(config["provider"]).lower()
        source = "remembered from last run"
    elif os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        provider = "anthropic"
        source = "Anthropic credentials detected"
    elif os.getenv("OPENAI_API_KEY"):
        provider = "openai"
        source = "OpenAI credentials detected"
    elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        provider = "gemini"
        source = "Gemini credentials detected"
    else:
        provider = "ollama"
        source = "local fallback"

    if provider not in PROVIDERS:
        fail(
            f"Unknown provider '{provider}'. "
            f"Choose from: {', '.join(PROVIDERS)}"
        )

    if args.model:
        model = args.model
    elif os.getenv(f"{provider.upper()}_MODEL"):
        model = os.getenv(f"{provider.upper()}_MODEL")
    elif config.get("models", {}).get(provider):
        model = config["models"][provider]
    else:
        model = DEFAULT_MODELS[provider]

    return provider, model, source


def remember_choice(config, provider, model):
    config["provider"] = provider
    config.setdefault("models", {})[provider] = model
    save_config(config)


def print_provider_banner(provider, model, source):
    print(
        f"{BOLD}{CYAN}Provider:{RESET} {provider}   {DIM}·{RESET}   "
        f"{BOLD}{CYAN}model:{RESET} {model}   {DIM}·{RESET}   "
        f"{DIM}source: {source}{RESET}"
    )


# ==============================================================================
# AI RUN 1: THE PLANNER
# ==============================================================================
def plan_dynamic_capture(provider, diag):
    compact_json = json.dumps(make_json_safe_diag(diag), indent=2)
    prompt = textwrap.dedent(f"""
        You are Phase 1 of an automated macOS diagnostic pipeline.
        Below is an initial fast triage snapshot of the system.

        Your task is to write a specific, targeted Bash script to capture deep diagnostic data
        tailored ONLY to the bottlenecks or heavy processes identified in the triage.

        CRITICAL RULES FOR OUTPUT BOUNDING:
        You MUST prevent massive output. The result of this script goes to an LLM, so every command must be strictly capped.
        1. If using `lsof`, you MUST pipe it to `| head -n 30`.
        2. If using `top`, use `-l 1` instead of multiple samples, and pipe to `| head -n 30`.
        3. If using `ps`, pipe to `| head -n 30`.
        4. If using `log show`, limit the time window and output lines (e.g., `log show --last 2m | head -n 50`).
        5. DO NOT run any command that risks outputting hundreds of lines of text.
        6. SECURITY SCANNERS (xprotectd, syspolicyd, trustd): If these are active, do NOT use `fs_usage`.
           Instead, use `sudo lsof -c xprotectd | head -n 30` and `log show --predicate 'process == "xprotectd"' --info --last 2m | head -n 50`.
        7. Start with #!/usr/bin/env bash
        8. Define these two helper functions exactly:
           section() {{ echo; echo "===================="; echo "== $1"; echo "===================="; }}
           finish_section() {{ echo "== End: $1"; echo; }}
        9. Use the helper functions to organize output.
        10. Do NOT write any interactive commands.
        11. Output ONLY the raw bash code wrapped in a ```bash block.
        12. STARTUP INVESTIGATION: For each active third-party LaunchAgent or login item, include a section
            that checks its resource consumption: `ps aux | grep -i AGENT_NAME | head -n 5` and
            `log show --predicate 'process == "AGENT_NAME"' --last 2m 2>/dev/null | head -n 20`.
        13. DISK: Include `df -h`, `du -sh ~/Library/Caches/* 2>/dev/null | sort -rh | head -n 10`,
            and `ls -lah ~/Library/Logs/ 2>/dev/null | head -n 10`.
        14. MEMORY: Include `vm_stat`, `sysctl vm.swapusage`, and `memory_pressure`.

        Compact metrics JSON:
        ```json
        {compact_json}
        ```
    """).strip()

    content = provider.complete(
        prompt,
        temperature=0.2,
        max_tokens=PLANNER_MAX_TOKENS,
    )
    match = re.search(r"```bash(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


# ==============================================================================
# AI RUN 2: THE ANALYST (HTML GENERATOR)
# ==============================================================================
def analyze_deep_capture_html(provider, capture_output):
    prompt = textwrap.dedent(f"""
        You are Phase 2 of an automated macOS diagnostic pipeline.
        Below is the raw output from a targeted Bash diagnostic capture script executed on a Mac.

        Provide a final, comprehensive system optimization report.

        CRITICAL FORMATTING REQUIREMENT:
        Output the entire response as a fully formed, standalone valid HTML document
        (including `<!DOCTYPE html>`, `<html>`, `<head>`, `<style>`, `<body>`).
        Inside the `<style>` block, use modern professional CSS:
        - Clean sans-serif system fonts (-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif)
        - Max-width 960px, centered, comfortable padding
        - Color coding: red (#e74c3c) for HIGH impact, orange (#e67e22) for MEDIUM, green (#27ae60) for LOW/safe
        - A dark top banner with the title, timestamp, and machine info
        - Cards/sections with light gray backgrounds and subtle border-radius
        - Tables with alternating row colors
        - Inline code styled with monospace background
        - A sticky "Quick Wins" sidebar or highlighted box near the top
        Do NOT wrap your answer in markdown code blocks. Return raw HTML only.

        REQUIRED CONTENT SECTIONS (in this order):

        1. HEADER BANNER
           Machine info, macOS version, date of report.

        2. EXECUTIVE SUMMARY (2-4 sentences)
           Clear plain-English verdict: what is hurting performance most and why.

        3. QUICK WINS BOX (highlighted, near top)
           3-5 specific terminal commands or System Settings steps the user can do RIGHT NOW
           to get an immediate improvement. Include the exact command with copy-paste formatting.
           Estimate the expected improvement for each (e.g., "saves ~8% CPU at login").

        4. TOP RESOURCE BOTTLENECKS TABLE
           Columns: Rank | Process/App | CPU% | MEM% | Severity | Root Cause | Recommended Action
           Rank by combined evidence severity. Use colored severity badges.

        5. STARTUP ITEM AUDIT
           For EVERY login item and LaunchAgent found, create a table with columns:
           Item Name | Type (Login/LaunchAgent/Daemon) | Currently Active? | Recommendation | Action Command
           Recommendations must be one of: KEEP | DISABLE | REMOVE
           For DISABLE: provide the exact `launchctl unload` command or System Settings path.
           For REMOVE: provide the exact `rm` command for the plist or the Login Items removal step.
           Estimate the performance/resource savings for disabling each item (e.g., "~2% CPU, ~150 MB RAM at startup").
           Flag items that are clearly unnecessary at login (e.g., Zoom helper, Teams helper if Teams not opened at startup).

        6. MEMORY ANALYSIS
           Parse vm_stat output to report: free memory, wired memory, compressed pages, page-outs.
           Interpret swap usage and memory pressure level.
           Recommend specific actions: RAM upgrade threshold, apps to quit, memory-heavy browser tabs, etc.

        7. DISK HEALTH
           Interpret df output and cache sizes.
           List top cache directories consuming space.
           Provide exact commands to safely clear stale caches (e.g., `rm -rf ~/Library/Caches/com.example.app`).
           Flag if disk is under 15 GB free and explain why that impacts performance (virtual memory paging).

        8. SPOTLIGHT & INDEXING
           Explain current Spotlight CPU usage.
           Provide exact commands to add exclusions (`mdutil -i off /path`) for common heavy directories
           (node_modules, build folders, ~/Downloads if not needed).
           Explain how to check indexing status with `mdutil -s /`.

        9. PROCESS-SPECIFIC DEEP DIVE
           For each of the top 5 CPU/memory consumers, provide:
           - What the process actually does
           - Why it might be consuming resources right now
           - Specific settings to change in its preferences
           - Whether it can be safely quit/restarted without data loss
           - The exact terminal command to kill it if needed: `kill -9 $(pgrep -x processname)`

        10. THERMAL & POWER ANALYSIS
            Interpret pmset thermal output.
            If throttling detected, explain how it reduces performance and what causes it.
            Provide steps: clean cooling vents, check for runaway processes, reduce display brightness, etc.

        11. OPTIMIZATION ROADMAP
            Prioritized numbered list: immediate (today), short-term (this week), long-term (this month).
            Each step: what to do, expected improvement, estimated time to complete, risk level (Low/Medium).

        12. MONITORING COMMANDS
            5-6 useful terminal one-liners the user can bookmark for ongoing monitoring:
            e.g., `top -o cpu`, `vm_stat 3`, `log stream --predicate '...'`, etc.
            Brief explanation of what each shows.

        Capture Output:
        ```text
        {capture_output}
        ```
    """).strip()

    content = provider.complete(
        prompt,
        temperature=0.3,
        max_tokens=ANALYST_MAX_TOKENS,
        stream=True,
    )

    if content.startswith("```html"):
        content = content.replace("```html", "", 1).rstrip("` \n")
    elif content.startswith("```"):
        content = content.replace("```", "", 1).rstrip("` \n")

    return content.strip()


def save_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args():
    setup_sections = "\n\n".join(
        cls.setup_help for cls in PROVIDER_CLASSES.values() if cls.setup_help
    )
    parser = argparse.ArgumentParser(
        description="Run Mac diagnostics with a 2-stage AI pipeline returning an HTML report.",
        epilog="provider setup\n" + ("-" * 40) + "\n" + setup_sections,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider", choices=PROVIDERS, default=None,
        help="LLM provider. Falls back to PROVIDER, HEALTHCHECK_PROVIDER, "
             "your remembered choice, detected credentials, then Ollama.",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model for the chosen provider. Falls back to <PROVIDER>_MODEL, then the "
             "last model used with that provider, then a built-in default "
             f"({', '.join(f'{p}={m}' for p, m in DEFAULT_MODELS.items())}).",
    )
    parser.add_argument("--out-dir", default=".", help="Directory where report files are saved.")
    return parser.parse_args()


def main():
    args = parse_args()
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir).expanduser().resolve()

    cfg = load_config()
    provider_name, model, source = resolve_provider_and_model(args, cfg)
    print_provider_banner(provider_name, model, source)
    provider = build_provider(provider_name, model)
    remember_choice(cfg, provider_name, model)

    # 1. INITIAL TRIAGE
    print(f"\n{BOLD}{CYAN}== Phase 1: Initial Triage =={RESET}")
    diag = collect_diagnostics()
    local_report_plain = render_local_report(diag)
    print(local_report_plain)

    # 2. AI RUN 1 (Plan the Capture)
    print(f"{BOLD}{YELLOW}== Phase 2: AI Generating Targeted Capture Script =={RESET}")
    bash_script_code = plan_dynamic_capture(provider, diag)

    script_path = out_dir / f"dynamic_capture_{timestamp}.sh"
    save_text(script_path, bash_script_code)
    os.chmod(script_path, 0o755)
    print(f"Generated and saved capture script to: {script_path}")

    # 3. EXECUTE TARGETED CAPTURE
    print(f"{BOLD}{MAGENTA}== Phase 3: Executing Capture =={RESET}")
    capture_out_path = out_dir / f"capture_output_{timestamp}.txt"

    try:
        result = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True, text=True, timeout=120,
        )
        capture_output = result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired as e:
        capture_output = f"Execution timed out. Partial output:\n{e.output or ''}"

    MAX_CHARS = 100_000
    if len(capture_output) > MAX_CHARS:
        print(f"{YELLOW}Warning: Capture output is large ({len(capture_output)} chars). Truncating to prevent API limits.{RESET}")
        half = MAX_CHARS // 2
        capture_output = (
            capture_output[:half]
            + "\n\n...[MASSIVE OUTPUT TRUNCATED FOR API LIMITS]...\n\n"
            + capture_output[-half:]
        )

    save_text(capture_out_path, capture_output)
    print(f"Saved capture output to: {capture_out_path}")

    # 4. AI RUN 2 (Final HTML Analysis)
    print(f"\n{BOLD}{GREEN}== Phase 4: AI Deep Analysis (HTML Generation) =={RESET}")
    try:
        final_html_analysis = analyze_deep_capture_html(provider, capture_output)
    except Exception as e:
        print(f"{RED}Analysis failed. Error: {e}{RESET}")
        sys.exit(1)

    analysis_path = out_dir / f"final_analysis_{timestamp}.html"
    save_text(analysis_path, final_html_analysis)
    print(f"Saved HTML optimization report to: {analysis_path}")

    # 5. AUTOMATICALLY LAUNCH IN BROWSER
    print(f"{BOLD}{CYAN}== Phase 5: Launching Report in Default Browser =={RESET}")
    try:
        subprocess.run(["open", str(analysis_path)], check=True)
        print(f"{GREEN}Success! Opened {analysis_path.name}{RESET}")
    except Exception as e:
        print(f"{RED}Failed to automatically open HTML page: {e}{RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
