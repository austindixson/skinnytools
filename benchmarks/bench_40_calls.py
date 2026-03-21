"""40-tool-call benchmark: raw vs skinnytools context growth.

Simulates a realistic agent session with 40 tool calls and measures
context growth turn-by-turn. Makes real LLM calls at checkpoints
to get actual token counts.

The scenario: agent managing infrastructure after a restart.
- Checks 8 services (8 calls)
- Reads config files (4 calls)
- Tails logs for each service (8 calls)
- Runs diagnostic commands (8 calls)
- Gets session reports periodically (4 calls — THE RECURSIVE BOMBS)
- Checks dependencies (4 calls)
- Final health summary calls (4 calls)
= 40 tool calls total
"""

from __future__ import annotations

import json
import os
import time
import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "minimax/minimax-m2.5"
INPUT_COST_PER_M = 0.40
OUTPUT_COST_PER_M = 1.10

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from skinnytools.core.pipeline import process
from skinnytools.core.budget import BudgetTracker
from skinnytools.models.config import PipelineConfig
from skinnytools.utils.text import format_size


# ─── Tool Call Schedule ──────────────────────────────────────────────────────
# 40 tool calls in a realistic order

TOOL_SCHEDULE = [
    # Phase 1: Check all 8 services (calls 1-8)
    ("check_service", {"service_name": "api-gateway"}),
    ("check_service", {"service_name": "auth-service"}),
    ("check_service", {"service_name": "user-service"}),
    ("check_service", {"service_name": "payment-service"}),
    ("check_service", {"service_name": "notification-service"}),
    ("check_service", {"service_name": "search-service"}),
    ("check_service", {"service_name": "analytics-service"}),
    ("check_service", {"service_name": "scheduler-service"}),

    # Phase 2: Read config files (calls 9-12)
    ("read_file", {"path": "/etc/myapp/database.yml"}),
    ("read_file", {"path": "/etc/myapp/redis.yml"}),
    ("read_file", {"path": "/etc/myapp/services.yml"}),
    ("read_file", {"path": "/etc/myapp/nginx.conf"}),

    # Phase 3: Session report #1 — RECURSIVE BOMB (call 13)
    ("get_session_report", {"include_history": True}),

    # Phase 4: Tail logs for each service (calls 14-21)
    ("tail_logs", {"service": "api-gateway", "lines": 100}),
    ("tail_logs", {"service": "auth-service", "lines": 100}),
    ("tail_logs", {"service": "user-service", "lines": 100}),
    ("tail_logs", {"service": "payment-service", "lines": 100}),
    ("tail_logs", {"service": "notification-service", "lines": 100}),
    ("tail_logs", {"service": "search-service", "lines": 100}),
    ("tail_logs", {"service": "analytics-service", "lines": 100}),
    ("tail_logs", {"service": "scheduler-service", "lines": 100}),

    # Phase 5: Diagnostic commands (calls 22-29)
    ("exec_command", {"command": "df -h"}),
    ("exec_command", {"command": "free -m"}),
    ("exec_command", {"command": "top -b -n1 | head -20"}),
    ("exec_command", {"command": "netstat -tlnp"}),
    ("exec_command", {"command": "docker ps --format json"}),
    ("exec_command", {"command": "systemctl list-units --failed"}),
    ("exec_command", {"command": "journalctl -p err --since '1 hour ago'"}),
    ("exec_command", {"command": "ss -s"}),

    # Phase 6: Session report #2 — BIGGER RECURSIVE BOMB (call 30)
    ("get_session_report", {"include_history": True}),

    # Phase 7: Check dependencies (calls 31-34)
    ("check_dependency", {"name": "postgresql", "host": "db.internal"}),
    ("check_dependency", {"name": "redis", "host": "redis.internal"}),
    ("check_dependency", {"name": "elasticsearch", "host": "es.internal"}),
    ("check_dependency", {"name": "rabbitmq", "host": "mq.internal"}),

    # Phase 8: Final checks (calls 35-38)
    ("exec_command", {"command": "curl -s http://localhost:8080/health"}),
    ("exec_command", {"command": "curl -s http://localhost:8081/health"}),
    ("exec_command", {"command": "curl -s http://localhost:8082/health"}),
    ("read_file", {"path": "/var/log/myapp/error.log"}),

    # Phase 9: Session report #3 — BIGGEST RECURSIVE BOMB (call 39)
    ("get_session_report", {"include_history": True}),

    # Phase 10: Final session report with artifacts (call 40)
    ("get_session_report", {"include_history": True, "include_artifacts": True}),
]


# ─── Tool Simulators ─────────────────────────────────────────────────────────

def simulate_check_service(args: dict, call_num: int) -> str:
    svc = args["service_name"]
    return json.dumps({
        "service": svc,
        "status": "running",
        "uptime": f"{call_num + 2}d 14h {call_num * 7}m",
        "pid": 10000 + call_num * 137,
        "port": 8000 + call_num,
        "health": "OK",
        "version": f"2.{call_num}.0",
        "metrics": {
            "cpu_percent": 15.2 + call_num * 3.1,
            "memory_mb": 256 + call_num * 64,
            "heap_used_mb": 180 + call_num * 40,
            "gc_pause_ms": 12 + call_num,
            "threads": 24 + call_num * 2,
            "requests_per_sec": 800 + call_num * 150,
            "error_rate": 0.001 * call_num,
            "p50_ms": 8 + call_num,
            "p95_ms": 25 + call_num * 4,
            "p99_ms": 80 + call_num * 12,
            "active_connections": 30 + call_num * 5,
            "queue_depth": call_num * 2,
        },
        "recent_logs": [
            f"2024-01-01T12:{i:02d}:00Z INFO [{svc}] Request handled in {8 + i}ms"
            for i in range(15)
        ],
        "config": {
            "max_connections": 100,
            "timeout_ms": 30000,
            "retry_count": 3,
            "circuit_breaker": "closed",
            "rate_limit": f"{1000 + call_num * 100}/min",
        },
        "dependencies": [
            {"name": f"dep-{i}", "status": "connected", "latency_ms": 2 + i}
            for i in range(4)
        ],
        "_meta": {"check_duration_ms": 45, "cached": False, "node": "worker-1"},
    }, indent=2)


def simulate_read_file(args: dict, call_num: int) -> str:
    path = args["path"]
    if "database" in path:
        return json.dumps({
            "production": {
                "host": "db-primary.internal",
                "port": 5432,
                "database": "myapp_production",
                "pool_size": 25,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 3600,
                "ssl": True,
                "read_replicas": [
                    {"host": f"db-replica-{i}.internal", "port": 5432, "weight": 1}
                    for i in range(3)
                ],
            },
            "connection_string": "postgresql://user:***@db-primary.internal:5432/myapp_production",
        }, indent=2)
    elif "redis" in path:
        return json.dumps({
            "cluster": {
                "nodes": [f"redis-{i}.internal:6379" for i in range(6)],
                "password": "***",
                "db": 0,
                "max_connections": 50,
                "socket_timeout": 5,
            }
        }, indent=2)
    elif "services" in path:
        return json.dumps({
            "services": {
                f"svc-{i}": {
                    "host": f"svc-{i}.internal",
                    "port": 8000 + i,
                    "replicas": 2 + (i % 3),
                    "health_check": f"/health",
                    "timeout_ms": 5000,
                }
                for i in range(8)
            }
        }, indent=2)
    elif "nginx" in path:
        return "\n".join([
            "upstream backend {",
            *[f"    server app-{i}.internal:8080 weight={i+1};" for i in range(4)],
            "}",
            "",
            "server {",
            "    listen 80;",
            "    server_name api.example.com;",
            "    location / {",
            "        proxy_pass http://backend;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_connect_timeout 60s;",
            "        proxy_read_timeout 120s;",
            "    }",
            "}",
        ])
    elif "error.log" in path:
        lines = []
        for i in range(80):
            if i % 20 == 0:
                lines.append(f"2024-01-01T12:{i:02d}:00Z ERROR Connection pool exhausted")
                lines.append("Traceback (most recent call last):")
                for f in range(8):
                    lines.append(f'  File "handler_{f}.py", line {f*10}, in process')
                    lines.append(f"    await db.execute(query_{f})")
                lines.append("asyncpg.exceptions.TooManyConnectionsError: too many connections")
            else:
                lines.append(f"2024-01-01T12:{i:02d}:00Z INFO Request processed OK")
        return "\n".join(lines)
    else:
        return f"Contents of {path}:\n" + "line\n" * 20


def simulate_tail_logs(args: dict, call_num: int) -> str:
    svc = args["service"]
    lines = args.get("lines", 100)
    log_lines = []
    for i in range(lines):
        ts = f"2024-01-01T{12 + i // 60}:{i % 60:02d}:00Z"
        if i % 30 == 0:
            log_lines.append(f"{ts} WARN [{svc}] Slow query detected: {120 + i}ms")
        elif i % 50 == 0:
            log_lines.append(f"{ts} ERROR [{svc}] Connection timeout to db-primary")
        else:
            log_lines.append(f"{ts} INFO [{svc}] Request {1000 + i} handled in {5 + i % 20}ms")
    return "\n".join(log_lines)


def simulate_exec_command(args: dict, call_num: int) -> str:
    cmd = args["command"]
    if "df" in cmd:
        return (
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/sda1       100G   67G   33G  67% /\n"
            "/dev/sdb1       500G  312G  188G  62% /data\n"
            "tmpfs            16G  2.1G   14G  14% /tmp\n"
        )
    elif "free" in cmd:
        return (
            "              total    used    free  shared  buff/cache   available\n"
            "Mem:          32768   24576    2048    1024       6144        7168\n"
            "Swap:          8192    1024    7168\n"
        )
    elif "top" in cmd:
        lines = ["  PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND"]
        for i in range(15):
            lines.append(
                f" {1000+i} app       20   0 {2+i}g  {512+i*64}m  {128+i*16}m S  {5+i*3:.1f}  {2+i*0.5:.1f}  {i}:42.{i:02d} svc-{i}"
            )
        return "\n".join(lines)
    elif "netstat" in cmd or "ss" in cmd:
        lines = ["Proto Recv-Q Send-Q Local Address           Foreign Address         State"]
        for i in range(12):
            lines.append(f"tcp        0      0 0.0.0.0:{8000+i}          0.0.0.0:*               LISTEN")
        return "\n".join(lines)
    elif "docker" in cmd:
        return json.dumps([
            {"ID": hashlib.md5(f"c{i}".encode()).hexdigest()[:12],
             "Image": f"myapp/svc-{i}:latest",
             "Status": f"Up {i+1} hours",
             "Ports": f"0.0.0.0:{8000+i}->8080/tcp",
             "Names": f"svc-{i}"}
            for i in range(8)
        ], indent=2)
    elif "systemctl" in cmd:
        return "0 loaded units listed."
    elif "journalctl" in cmd:
        lines = []
        for i in range(40):
            lines.append(f"Jan 01 12:{i:02d}:00 worker-1 svc-{i%8}[{10000+i}]: ERROR Connection pool limit reached")
        return "\n".join(lines)
    elif "curl" in cmd:
        return json.dumps({"status": "healthy", "uptime": "3d 14h", "version": "2.1.0",
                           "checks": {"database": "ok", "redis": "ok", "disk": "ok"}})
    return f"$ {cmd}\nOK"


def simulate_check_dependency(args: dict, call_num: int) -> str:
    return json.dumps({
        "name": args["name"],
        "host": args["host"],
        "status": "connected",
        "latency_ms": 2.3 + call_num * 0.5,
        "version": f"14.{call_num}",
        "connections": {"active": 20 + call_num, "idle": 5, "max": 100},
        "replication": {
            "role": "primary",
            "replicas": 2,
            "lag_bytes": 0,
        },
    }, indent=2)


def simulate_session_report(args: dict, conversation: list[dict], call_num: int) -> str:
    """THE RECURSIVE BOMB: embeds the full conversation history."""
    include_history = args.get("include_history", False)
    include_artifacts = args.get("include_artifacts", False)

    report = {
        "session_id": "infra-check-20240101",
        "started_at": "2024-01-01T12:00:00Z",
        "duration_seconds": call_num * 15,
        "tool_calls_completed": call_num,
        "status": "in_progress",
        "token_usage": {
            "prompt_tokens": sum(len(json.dumps(m)) // 4 for m in conversation),
            "completion_tokens": call_num * 150,
            "total": sum(len(json.dumps(m)) // 4 for m in conversation) + call_num * 150,
        },
    }

    if include_history:
        # THIS IS THE KILLER: the full conversation including all prior tool results
        report["conversation_history"] = conversation

    if include_artifacts:
        report["artifacts"] = {
            "services_checked": [f"svc-{i}" for i in range(8)],
            "files_read": ["/etc/myapp/database.yml", "/etc/myapp/redis.yml",
                          "/etc/myapp/services.yml", "/etc/myapp/nginx.conf"],
            "commands_run": ["df -h", "free -m", "top", "netstat", "docker ps",
                           "systemctl", "journalctl", "ss -s"],
            "summary": "All 8 services running. " * 20,
        }

    return json.dumps(report, indent=2)


def simulate_tool(name: str, args: dict, conversation: list[dict], call_num: int) -> str:
    if name == "check_service":
        return simulate_check_service(args, call_num)
    elif name == "read_file":
        return simulate_read_file(args, call_num)
    elif name == "tail_logs":
        return simulate_tail_logs(args, call_num)
    elif name == "exec_command":
        return simulate_exec_command(args, call_num)
    elif name == "check_dependency":
        return simulate_check_dependency(args, call_num)
    elif name == "get_session_report":
        return simulate_session_report(args, conversation, call_num)
    return f"Unknown tool: {name}"


# ─── LLM Token Measurement ──────────────────────────────────────────────────

def measure_real_tokens(messages: list[dict]) -> tuple[int, float]:
    """Make a real LLM call to get actual token count. Returns (prompt_tokens, cost)."""
    if not OPENROUTER_KEY:
        # Estimate if no API key
        chars = sum(len(json.dumps(m)) for m in messages)
        return chars // 4, 0.0

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/skinnytools/benchmark",
        "X-Title": "skinnytools-40call-bench",
    }
    # Flatten for OpenRouter compatibility
    flat = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = json.dumps(content)
        if role == "tool":
            role = "user"
            content = f"[Tool Result]\n{content}"
        if flat and flat[-1]["role"] == role:
            flat[-1]["content"] += "\n\n" + content
        else:
            flat.append({"role": role, "content": content})

    payload = {
        "model": MODEL,
        "messages": flat,
        "max_tokens": 10,  # minimal — we just want the prompt token count
        "temperature": 0,
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            pt = usage.get("prompt_tokens", 0)
            cost = pt * INPUT_COST_PER_M / 1_000_000
            return pt, cost
    except Exception:
        pass

    chars = sum(len(json.dumps(m)) for m in messages)
    return chars // 4, 0.0


# ─── Main Benchmark ─────────────────────────────────────────────────────────

@dataclass
class TurnData:
    call_num: int
    tool_name: str
    raw_result_size: int
    filtered_result_size: int
    raw_context_chars: int
    filtered_context_chars: int
    raw_tokens: int = 0
    filtered_tokens: int = 0
    is_checkpoint: bool = False


def run_benchmark():
    print("=" * 80)
    print("  skinnytools 40-Call Benchmark")
    print("  Simulated infrastructure check with 4 recursive session reports")
    print("=" * 80)
    print()

    system_msg = {
        "role": "system",
        "content": "You are a DevOps assistant checking infrastructure after a restart.",
    }
    user_msg = {
        "role": "user",
        "content": "The server restarted. Check all 8 services, read configs, tail logs, run diagnostics, and give me session reports.",
    }

    # Two parallel conversations
    raw_messages = [system_msg, user_msg]
    filtered_messages = [system_msg, user_msg]

    budget = BudgetTracker(total_budget=500_000)
    config = PipelineConfig()

    turns: list[TurnData] = []
    checkpoints = {1, 5, 10, 13, 20, 25, 30, 35, 39, 40}  # measure real tokens here

    print(f"{'#':<4} {'Tool':<28} {'Result':>8} {'Filtered':>8} {'Raw Ctx':>10} {'Filt Ctx':>10} {'Saved':>7}")
    print("-" * 80)

    for i, (tool_name, tool_args) in enumerate(TOOL_SCHEDULE, 1):
        # Simulate assistant requesting this tool
        assistant_msg = {
            "role": "assistant",
            "content": f"Calling {tool_name}({json.dumps(tool_args)})",
        }
        raw_messages.append(assistant_msg)
        filtered_messages.append(dict(assistant_msg))

        # Simulate tool execution
        raw_result = simulate_tool(tool_name, tool_args, raw_messages, i)
        raw_result_size = len(raw_result)

        # Apply skinnytools
        if len(raw_result) > 1024:
            filtered_result, stats = process(raw_result, config, budget)
            budget = budget.with_consumption(len(filtered_result))
        else:
            filtered_result = raw_result
        filtered_result_size = len(filtered_result)

        # Add tool results to conversations
        raw_messages.append({"role": "user", "content": f"[Tool Result: {tool_name}]\n{raw_result}"})
        filtered_messages.append({"role": "user", "content": f"[Tool Result: {tool_name}]\n{filtered_result}"})

        raw_ctx = sum(len(json.dumps(m)) for m in raw_messages)
        filt_ctx = sum(len(json.dumps(m)) for m in filtered_messages)
        ctx_saved = 1.0 - (filt_ctx / raw_ctx) if raw_ctx > 0 else 0

        is_cp = i in checkpoints
        marker = " *" if is_cp else ""

        turn = TurnData(
            call_num=i,
            tool_name=tool_name,
            raw_result_size=raw_result_size,
            filtered_result_size=filtered_result_size,
            raw_context_chars=raw_ctx,
            filtered_context_chars=filt_ctx,
            is_checkpoint=is_cp,
        )

        # Highlight session reports
        label = tool_name
        if tool_name == "get_session_report":
            label = "SESSION REPORT"

        print(
            f"{i:<4} {label:<28} "
            f"{format_size(raw_result_size):>8} "
            f"{format_size(filtered_result_size):>8} "
            f"{format_size(raw_ctx):>10} "
            f"{format_size(filt_ctx):>10} "
            f"{ctx_saved:>6.1%}{marker}"
        )

        turns.append(turn)

    # ── Real Token Measurements at Checkpoints ────────────────────────────
    print()
    print("=" * 80)
    print("  REAL TOKEN MEASUREMENTS (API calls at checkpoints)")
    print("=" * 80)
    print()

    # Rebuild conversations up to each checkpoint and measure
    raw_rebuild = [system_msg, user_msg]
    filt_rebuild = [system_msg, user_msg]
    budget2 = BudgetTracker(total_budget=500_000)

    checkpoint_data = []

    print(f"{'Call #':<8} {'Raw Tokens':>12} {'Filt Tokens':>12} {'Token Saved':>12} {'Raw Cost':>10} {'Filt Cost':>10}")
    print("-" * 68)

    for i, (tool_name, tool_args) in enumerate(TOOL_SCHEDULE, 1):
        assistant_msg = {"role": "assistant", "content": f"Calling {tool_name}({json.dumps(tool_args)})"}
        raw_rebuild.append(assistant_msg)
        filt_rebuild.append(dict(assistant_msg))

        raw_result = simulate_tool(tool_name, tool_args, raw_rebuild, i)
        if len(raw_result) > 1024:
            filtered_result, _ = process(raw_result, config, budget2)
            budget2 = budget2.with_consumption(len(filtered_result))
        else:
            filtered_result = raw_result

        raw_rebuild.append({"role": "user", "content": f"[Tool Result: {tool_name}]\n{raw_result}"})
        filt_rebuild.append({"role": "user", "content": f"[Tool Result: {tool_name}]\n{filtered_result}"})

        if i in checkpoints:
            print(f"  Measuring call #{i}...", end=" ", flush=True)
            raw_tok, raw_cost = measure_real_tokens(raw_rebuild)
            filt_tok, filt_cost = measure_real_tokens(filt_rebuild)
            saving = 1.0 - (filt_tok / raw_tok) if raw_tok > 0 else 0

            # Update turn data
            for t in turns:
                if t.call_num == i:
                    t.raw_tokens = raw_tok
                    t.filtered_tokens = filt_tok

            checkpoint_data.append((i, raw_tok, filt_tok, raw_cost, filt_cost))
            print(f"done")
            print(
                f"  {i:<6} {raw_tok:>12,} {filt_tok:>12,} "
                f"{saving:>11.1%} "
                f"${raw_cost:>9.4f} ${filt_cost:>9.4f}"
            )

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()

    final_raw_ctx = turns[-1].raw_context_chars
    final_filt_ctx = turns[-1].filtered_context_chars

    # Session report impact
    session_reports = [t for t in turns if t.tool_name == "get_session_report"]

    print(f"  Total tool calls: {len(turns)}")
    print(f"  Session reports (recursive bombs): {len(session_reports)}")
    print()
    print(f"  Final context size:")
    print(f"    Raw:         {format_size(final_raw_ctx)} chars")
    print(f"    Filtered:    {format_size(final_filt_ctx)} chars")
    print(f"    Saved:       {1.0 - final_filt_ctx / final_raw_ctx:.1%}")
    print()

    if checkpoint_data:
        final_cp = checkpoint_data[-1]
        first_cp = checkpoint_data[0]
        print(f"  Token usage (from real API measurements):")
        print(f"    After call #1:   Raw {first_cp[1]:>8,}  Filtered {first_cp[2]:>8,}")
        print(f"    After call #40:  Raw {final_cp[1]:>8,}  Filtered {final_cp[2]:>8,}")
        print(f"    Token savings:   {1.0 - final_cp[2] / final_cp[1]:.1%}")
        print()

        total_raw_cost = sum(c[3] for c in checkpoint_data)
        total_filt_cost = sum(c[4] for c in checkpoint_data)
        print(f"  Estimated session cost (measured at {len(checkpoint_data)} checkpoints):")
        print(f"    Raw:         ${total_raw_cost:.4f}")
        print(f"    Filtered:    ${total_filt_cost:.4f}")
        if total_raw_cost > 0:
            print(f"    Saved:       ${total_raw_cost - total_filt_cost:.4f} ({1.0 - total_filt_cost/total_raw_cost:.1%})")

    print()
    print("  Session report sizes (the recursive bombs):")
    for t in session_reports:
        pct = 1.0 - (t.filtered_result_size / t.raw_result_size) if t.raw_result_size > 0 else 0
        print(
            f"    Call #{t.call_num}: {format_size(t.raw_result_size)} → "
            f"{format_size(t.filtered_result_size)} ({pct:.1%} compressed)"
        )

    print()
    print("  Context growth rate:")
    if len(turns) > 1:
        # First half vs second half
        mid = len(turns) // 2
        raw_first_half = turns[mid].raw_context_chars - turns[0].raw_context_chars
        raw_second_half = turns[-1].raw_context_chars - turns[mid].raw_context_chars
        filt_first_half = turns[mid].filtered_context_chars - turns[0].filtered_context_chars
        filt_second_half = turns[-1].filtered_context_chars - turns[mid].filtered_context_chars

        print(f"    Raw  (calls 1-20):  +{format_size(raw_first_half)}")
        print(f"    Raw  (calls 21-40): +{format_size(raw_second_half)}")
        print(f"    Filt (calls 1-20):  +{format_size(filt_first_half)}")
        print(f"    Filt (calls 21-40): +{format_size(filt_second_half)}")
        print()
        if raw_second_half > raw_first_half * 1.5:
            print("    Raw context growth is ACCELERATING (recursive amplification!)")
        print(f"    Filtered growth is {filt_second_half / raw_second_half:.0%} of raw in second half" if raw_second_half > 0 else "")

    # Save
    output = {
        "model": MODEL,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_calls": len(turns),
        "session_reports": len(session_reports),
        "final_raw_context_chars": final_raw_ctx,
        "final_filtered_context_chars": final_filt_ctx,
        "context_savings_pct": round((1.0 - final_filt_ctx / final_raw_ctx) * 100, 1),
        "checkpoints": [
            {"call": c[0], "raw_tokens": c[1], "filtered_tokens": c[2],
             "raw_cost": round(c[3], 6), "filtered_cost": round(c[4], 6)}
            for c in checkpoint_data
        ],
        "per_call": [
            {"call": t.call_num, "tool": t.tool_name,
             "raw_result": t.raw_result_size, "filtered_result": t.filtered_result_size,
             "raw_context": t.raw_context_chars, "filtered_context": t.filtered_context_chars}
            for t in turns
        ],
    }
    results_path = Path(__file__).parent / "results"
    results_path.mkdir(exist_ok=True)
    out_file = results_path / f"forty_calls_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved to {out_file}")


if __name__ == "__main__":
    run_benchmark()
