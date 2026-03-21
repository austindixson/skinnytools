"""Agent loop benchmark: simulates a real ReAct tool-calling loop.

This is the benchmark that actually matches the tweeter's problem.
His agent makes tool calls in a loop, each result accumulates in context,
and eventually a result contains a copy of the session — recursive amplification.

This benchmark:
1. Sends messages with tool definitions to the LLM
2. The LLM requests tool calls (just like a real agent)
3. We simulate tool execution and return realistic results
4. Those results go into context (raw vs skinnytools-filtered)
5. The loop continues for N turns
6. We measure how context grows turn-by-turn

Two runs: one raw, one with skinnytools filtering every tool result.
"""

from __future__ import annotations

import json
import os
import time
import base64
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Use MiniMax for the loop benchmark (cheaper for many calls)
MODEL = "minimax/minimax-m2.5"
MODEL_LABEL = "MiniMax M2.5"
INPUT_COST_PER_M = 0.40
OUTPUT_COST_PER_M = 1.10

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from skinnytools.core.pipeline import process
from skinnytools.core.budget import BudgetTracker
from skinnytools.models.config import PipelineConfig
from skinnytools.utils.text import format_size


# ─── Tool Definitions ────────────────────────────────────────────────────────
# These are the tools the LLM can call — same kinds the tweeter's agent uses

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_service",
            "description": "Check if a service is running and get its status, logs, and metrics",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service to check"
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exec_command",
            "description": "Execute a shell command and return its output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_report",
            "description": "Get a report of the current agent session including conversation history and tool usage",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_history": {
                        "type": "boolean",
                        "description": "Whether to include full conversation history"
                    }
                },
                "required": []
            }
        }
    },
]


# ─── Simulated Tool Results ──────────────────────────────────────────────────
# These simulate what real tools return — including the recursive case

def simulate_tool_result(
    tool_name: str,
    args: dict,
    conversation_history: list[dict],
    turn: int,
) -> str:
    """Simulate a tool execution and return a realistic result.

    The key insight: some tools (like exec/session_report) return data
    that includes the conversation history itself — this is the recursive
    amplification bug.
    """

    if tool_name == "check_service":
        svc = args.get("service_name", "unknown")
        return json.dumps({
            "service": svc,
            "status": "running",
            "uptime": "3d 14h 22m",
            "pid": 12345 + turn,
            "port": 8000 + turn,
            "health_check": "OK",
            "metrics": {
                "cpu_percent": 23.4 + turn * 2,
                "memory_mb": 512 + turn * 50,
                "requests_per_sec": 1200 + turn * 100,
                "error_rate": 0.001 * turn,
                "p50_ms": 12,
                "p95_ms": 45 + turn * 5,
                "p99_ms": 120 + turn * 15,
                "active_connections": 42 + turn * 3,
            },
            "recent_logs": [
                f"2024-01-01T{12+turn}:{i:02d}:00Z INFO Request processed in {10+i}ms"
                for i in range(20)
            ],
            "config": {
                f"setting_{i}": f"value_{i}" for i in range(10)
            },
            "dependencies": [
                {"name": f"dep_{i}", "status": "healthy", "latency_ms": 5 + i}
                for i in range(5)
            ],
        }, indent=2)

    elif tool_name == "exec_command":
        cmd = args.get("command", "")
        if "status" in cmd or "ps" in cmd or "systemctl" in cmd:
            # Normal command output
            lines = [f"  {i+1}. service_{i}: running (pid {1000+i})" for i in range(10)]
            return "System Status:\n" + "\n".join(lines)
        elif "log" in cmd or "tail" in cmd or "journal" in cmd:
            # Log output — can be large
            return "\n".join(
                f"2024-01-01T{12+turn}:{i:02d}:00Z INFO Processing request {i}"
                for i in range(100)
            )
        else:
            return f"$ {cmd}\nCommand completed successfully."

    elif tool_name == "read_file":
        path = args.get("path", "")
        if "config" in path:
            return json.dumps({
                "database": {"host": "db.internal", "port": 5432, "pool_size": 20},
                "redis": {"host": "redis.internal", "port": 6379},
                "services": {f"svc_{i}": {"port": 8000+i, "replicas": 2} for i in range(8)},
            }, indent=2)
        elif "log" in path:
            return "\n".join(
                f"2024-01-01T12:{i:02d}:00Z INFO Line {i}" for i in range(50)
            )
        else:
            return f"Contents of {path}:\n" + "data line\n" * 20

    elif tool_name == "get_session_report":
        # THIS IS THE KILLER: returns a dump that includes the conversation history
        # This is exactly what causes the recursive amplification
        include_history = args.get("include_history", True)

        report = {
            "session_id": "bench-session-001",
            "started_at": "2024-01-01T12:00:00Z",
            "turns": turn,
            "total_tool_calls": turn * 2,
            "token_usage": {
                "prompt_tokens": sum(len(json.dumps(m)) // 4 for m in conversation_history),
                "completion_tokens": turn * 200,
            },
        }

        if include_history:
            # THE RECURSIVE BIT: embedding the full conversation (including
            # all previous tool results) inside this tool result
            report["conversation_history"] = conversation_history
            report["artifacts"] = {
                "files_read": [f"/path/to/file_{i}" for i in range(turn)],
                "commands_run": [f"command_{i}" for i in range(turn)],
            }

        return json.dumps(report, indent=2)

    return f"Unknown tool: {tool_name}"


# ─── LLM Calling ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TurnResult:
    turn: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: float
    tool_calls_made: int
    context_chars: int
    error: str | None = None


def call_llm_with_tools(messages: list[dict], label: str = "") -> dict:
    """Call LLM with tool definitions and return full response."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/skinnytools/benchmark",
        "X-Title": "skinnytools-agent-loop-bench",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    start = time.monotonic()
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    latency = (time.monotonic() - start) * 1000

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "latency_ms": latency}

    data = resp.json()
    data["latency_ms"] = latency
    return data


# ─── Agent Loop ──────────────────────────────────────────────────────────────

def run_agent_loop(
    use_skinnytools: bool,
    max_turns: int = 10,
    label: str = "",
) -> list[TurnResult]:
    """Run a simulated agent loop for max_turns.

    The agent is asked to check all services after a restart.
    It will make tool calls, get results, and continue until done
    or context is exhausted.
    """
    budget = BudgetTracker(total_budget=500_000) if use_skinnytools else None
    config = PipelineConfig()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a DevOps assistant managing 8 services. "
                "Use the available tools to check each service, review logs, "
                "and generate a session report. Check services one at a time. "
                "After checking all services, call get_session_report to summarize. "
                "Be thorough — check each service individually."
            ),
        },
        {
            "role": "user",
            "content": (
                "The computer restarted. Can you make sure all of our services are online? "
                "Check each one: api, auth, database, cache, worker, scheduler, gateway, monitor. "
                "Then get a session report."
            ),
        },
    ]

    turn_results: list[TurnResult] = []
    total_tool_calls = 0

    for turn in range(1, max_turns + 1):
        context_chars = sum(len(json.dumps(m)) for m in messages)
        tag = f"{'SKINNY' if use_skinnytools else 'RAW':>6}"
        print(f"    {tag} Turn {turn}: {format_size(context_chars)} context, {total_tool_calls} tool calls so far...", end=" ", flush=True)

        # Call LLM
        response = call_llm_with_tools(messages, f"{label}_turn{turn}")

        if "error" in response:
            print(f"ERROR: {response['error'][:60]}")
            turn_results.append(TurnResult(
                turn=turn,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=response.get("latency_ms", 0),
                cost_usd=0,
                tool_calls_made=0,
                context_chars=context_chars,
                error=response["error"],
            ))
            break

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        latency = response.get("latency_ms", 0)
        cost = (prompt_tokens * INPUT_COST_PER_M / 1_000_000) + (
            completion_tokens * OUTPUT_COST_PER_M / 1_000_000
        )

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # Count tool calls this turn
        tool_calls = message.get("tool_calls", [])
        turn_tool_calls = len(tool_calls)
        total_tool_calls += turn_tool_calls

        print(f"{prompt_tokens:,} prompt tok, {turn_tool_calls} tool calls, {latency:.0f}ms")

        # Append assistant message
        messages.append(message)

        # If no tool calls, the model is done
        if not tool_calls or finish_reason == "stop":
            turn_results.append(TurnResult(
                turn=turn,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency,
                cost_usd=cost,
                tool_calls_made=turn_tool_calls,
                context_chars=context_chars,
            ))
            break

        # Execute each tool call and add results
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}
            call_id = tc.get("id", "")

            # Simulate tool execution
            raw_result = simulate_tool_result(
                tool_name, tool_args, messages, turn
            )

            # Apply skinnytools if enabled
            if use_skinnytools and len(raw_result) > 1024:
                filtered_result, stats = process(raw_result, config, budget)
                if budget:
                    budget = budget.with_consumption(len(filtered_result))
                result_content = filtered_result
            else:
                result_content = raw_result

            # Add tool result to conversation (OpenAI format)
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_content,
            })

        turn_results.append(TurnResult(
            turn=turn,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency,
            cost_usd=cost,
            tool_calls_made=turn_tool_calls,
            context_chars=context_chars,
        ))

    return turn_results


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_benchmark():
    if not OPENROUTER_KEY:
        print("ERROR: OPENROUTER_API_KEY not set")
        return

    print("=" * 80)
    print("  skinnytools Agent Loop Benchmark")
    print(f"  Model: {MODEL_LABEL} ({MODEL})")
    print("  Task: Check 8 services after restart, then get session report")
    print("  This simulates the exact problem from the tweet")
    print("=" * 80)

    max_turns = 15

    # ── Run 1: Raw (no skinnytools) ───────────────────────────────────────
    print()
    print(f"  RUN 1: Raw (no filtering)")
    print(f"  {'─' * 60}")
    raw_results = run_agent_loop(use_skinnytools=False, max_turns=max_turns, label="raw")

    # ── Run 2: With skinnytools ───────────────────────────────────────────
    print()
    print(f"  RUN 2: With skinnytools filtering")
    print(f"  {'─' * 60}")
    skinny_results = run_agent_loop(use_skinnytools=True, max_turns=max_turns, label="skinny")

    # ── Results ───────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  RESULTS: Turn-by-Turn Comparison")
    print("=" * 80)
    print()
    print(f"{'Turn':<6} {'Raw Ctx':>10} {'Raw Tok':>10} {'Skinny Ctx':>10} {'Skinny Tok':>10} {'Ctx Saved':>10} {'Tok Saved':>10}")
    print("-" * 68)

    max_common = min(len(raw_results), len(skinny_results))
    for i in range(max_common):
        r = raw_results[i]
        s = skinny_results[i]
        ctx_saved = 1.0 - (s.context_chars / r.context_chars) if r.context_chars > 0 else 0
        tok_saved = 1.0 - (s.prompt_tokens / r.prompt_tokens) if r.prompt_tokens > 0 else 0
        print(
            f"  {r.turn:<4} "
            f"{format_size(r.context_chars):>10} {r.prompt_tokens:>10,} "
            f"{format_size(s.context_chars):>10} {s.prompt_tokens:>10,} "
            f"{ctx_saved:>9.1%} {tok_saved:>9.1%}"
        )

    # Show remaining turns if one run went longer
    if len(raw_results) > max_common:
        for i in range(max_common, len(raw_results)):
            r = raw_results[i]
            print(f"  {r.turn:<4} {format_size(r.context_chars):>10} {r.prompt_tokens:>10,} {'(done)':>10} {'—':>10} {'—':>10} {'—':>10}")
    if len(skinny_results) > max_common:
        for i in range(max_common, len(skinny_results)):
            s = skinny_results[i]
            print(f"  {s.turn:<4} {'(done)':>10} {'—':>10} {format_size(s.context_chars):>10} {s.prompt_tokens:>10,} {'—':>10} {'—':>10}")

    # ── Totals ────────────────────────────────────────────────────────────
    raw_total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in raw_results)
    skinny_total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in skinny_results)
    raw_total_cost = sum(r.cost_usd for r in raw_results)
    skinny_total_cost = sum(r.cost_usd for r in skinny_results)
    raw_total_tool_calls = sum(r.tool_calls_made for r in raw_results)
    skinny_total_tool_calls = sum(r.tool_calls_made for r in skinny_results)
    raw_total_latency = sum(r.latency_ms for r in raw_results)
    skinny_total_latency = sum(r.latency_ms for r in skinny_results)
    raw_errors = sum(1 for r in raw_results if r.error)
    skinny_errors = sum(1 for r in skinny_results if r.error)

    # Final context sizes
    raw_final_ctx = raw_results[-1].context_chars if raw_results else 0
    skinny_final_ctx = skinny_results[-1].context_chars if skinny_results else 0

    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Metric':<30} {'Raw':>15} {'skinnytools':>15} {'Savings':>12}")
    print("-" * 72)
    print(f"{'Turns completed':<30} {len(raw_results):>15} {len(skinny_results):>15}")
    print(f"{'Tool calls made':<30} {raw_total_tool_calls:>15} {skinny_total_tool_calls:>15}")
    print(f"{'Final context size':<30} {format_size(raw_final_ctx):>15} {format_size(skinny_final_ctx):>15} {1.0 - skinny_final_ctx/raw_final_ctx:.1%}" if raw_final_ctx > 0 else "")
    print(f"{'Total tokens (all turns)':<30} {raw_total_tokens:>15,} {skinny_total_tokens:>15,} {1.0 - skinny_total_tokens/raw_total_tokens:.1%}" if raw_total_tokens > 0 else "")
    print(f"{'Total cost':<30} {'$'+f'{raw_total_cost:.4f}':>15} {'$'+f'{skinny_total_cost:.4f}':>15} {'$'+f'{raw_total_cost - skinny_total_cost:.4f}':>12}" if raw_total_cost > 0 else "")
    print(f"{'Total latency':<30} {f'{raw_total_latency/1000:.1f}s':>15} {f'{skinny_total_latency/1000:.1f}s':>15}")
    print(f"{'Errors / context overflows':<30} {raw_errors:>15} {skinny_errors:>15}")

    if raw_final_ctx > 0 and skinny_final_ctx > 0:
        print()
        # Context growth rate
        if len(raw_results) > 1:
            raw_growth = (raw_results[-1].context_chars - raw_results[0].context_chars) / len(raw_results)
            skinny_growth = (skinny_results[-1].context_chars - skinny_results[0].context_chars) / len(skinny_results)
            print(f"  Context growth per turn:")
            print(f"    Raw:         {format_size(int(raw_growth))} chars/turn")
            print(f"    skinnytools: {format_size(int(skinny_growth))} chars/turn")
            if raw_growth > 0:
                print(f"    Reduction:   {1.0 - skinny_growth/raw_growth:.1%}")

    # Save results
    output = {
        "model": MODEL,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task": "Check 8 services after restart + session report",
        "raw": {
            "turns": len(raw_results),
            "tool_calls": raw_total_tool_calls,
            "final_context_chars": raw_final_ctx,
            "total_tokens": raw_total_tokens,
            "total_cost_usd": round(raw_total_cost, 6),
            "errors": raw_errors,
            "per_turn": [
                {
                    "turn": r.turn,
                    "context_chars": r.context_chars,
                    "prompt_tokens": r.prompt_tokens,
                    "tool_calls": r.tool_calls_made,
                    "latency_ms": round(r.latency_ms),
                    "error": r.error,
                }
                for r in raw_results
            ],
        },
        "skinnytools": {
            "turns": len(skinny_results),
            "tool_calls": skinny_total_tool_calls,
            "final_context_chars": skinny_final_ctx,
            "total_tokens": skinny_total_tokens,
            "total_cost_usd": round(skinny_total_cost, 6),
            "errors": skinny_errors,
            "per_turn": [
                {
                    "turn": r.turn,
                    "context_chars": r.context_chars,
                    "prompt_tokens": r.prompt_tokens,
                    "tool_calls": r.tool_calls_made,
                    "latency_ms": round(r.latency_ms),
                    "error": r.error,
                }
                for r in skinny_results
            ],
        },
    }
    results_path = Path(__file__).parent / "results"
    results_path.mkdir(exist_ok=True)
    out_file = results_path / f"agent_loop_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    run_benchmark()
