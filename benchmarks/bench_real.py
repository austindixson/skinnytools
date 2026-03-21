"""Real benchmark: skinnytools vs raw tool results through multiple LLMs.

Tests MiniMax M2.5 and Claude Opus via OpenRouter.
Simulates ferroclaw/openclaw-style agent sessions with realistic tool results,
measures token usage, latency, cost, and response quality with and without
skinnytools filtering.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load API key
load_dotenv(Path(__file__).parent.parent / ".env")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "minimax/minimax-m2.5": {
        "label": "MiniMax M2.5",
        "input_cost_per_m": 0.40,
        "output_cost_per_m": 1.10,
    },
    "anthropic/claude-opus-4": {
        "label": "Claude Opus",
        "input_cost_per_m": 15.00,
        "output_cost_per_m": 75.00,
    },
}

# Import skinnytools
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig
from skinnytools.utils.text import estimate_tokens, format_size


# ─── Test Scenarios ──────────────────────────────────────────────────────────

def build_scenarios() -> list[dict]:
    """Build realistic ferroclaw/openclaw-style agent scenarios."""

    scenarios = []

    # ── Scenario 1: Recursive Session Dump ────────────────────────────────
    # The exact problem from the tweet: exec tool returns session JSON
    inner_conversation = json.dumps([
        {"role": "user", "content": "check all services"},
        {"role": "assistant", "content": "I'll check each service. " + "Analyzing system state " * 500},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tool_1",
             "content": json.dumps({
                 "services": [{"name": f"svc_{i}", "status": "running",
                               "logs": f"2024-01-01T00:00:00Z Starting service {i}\n" * 50}
                              for i in range(20)]
             })}
        ]},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "Let me analyze each service... " + "checking " * 2000},
            {"type": "text", "text": "All 20 services are running."}
        ]},
    ])
    scenarios.append({
        "name": "recursive_session_dump",
        "description": "exec tool returns embedded session JSON (the tweet problem)",
        "system": "You are a DevOps assistant. Answer concisely.",
        "history": [
            {"role": "user", "content": "the computer restarted, can you make sure all of our services are online?"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll check the service status now."}
            ]},
        ],
        "tool_result": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "exec_1",
                 "content": inner_conversation}
            ],
        },
        "followup": "Based on the output, are all services online? Just say yes or no and list any that are down.",
    })

    # ── Scenario 2: Massive JSON API Response ─────────────────────────────
    # A typical bloated API response with nulls, metadata, empty fields
    api_response = json.dumps({
        "data": [
            {
                "id": i,
                "name": f"resource_{i}",
                "description": None,
                "tags": [],
                "metadata": {},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
                "deleted_at": None,
                "_links": {"self": f"/api/resources/{i}", "parent": "/api/resources"},
                "_meta": {"version": 1, "etag": f"W/\"abc{i}\""},
                "_embedded": {"owner": {"id": 1, "name": None}},
                "attributes": {
                    f"attr_{j}": f"value_{j}" if j % 3 == 0 else None
                    for j in range(20)
                },
                "nested": {
                    "level1": {
                        "level2": {
                            "level3": None,
                            "data": "actual_value" if i % 5 == 0 else None,
                        }
                    }
                },
            }
            for i in range(200)
        ],
        "pagination": {"total": 5000, "page": 1, "per_page": 200, "pages": 25},
        "links": {"next": "/api/resources?page=2", "prev": None},
    }, indent=2)
    scenarios.append({
        "name": "bloated_api_response",
        "description": "200-item API response with nulls, metadata, empty fields",
        "system": "You are an API data analyst. Be concise.",
        "history": [
            {"role": "user", "content": "How many resources do we have and what are the first 3?"},
        ],
        "tool_result": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "api_1",
                 "content": api_response}
            ],
        },
        "followup": "Summarize: how many total resources, and name the first 3.",
    })

    # ── Scenario 3: Log Dump with Stack Traces ────────────────────────────
    log_lines = []
    for i in range(500):
        if i == 150:
            log_lines.append("2024-01-01T12:30:00Z ERROR Unhandled exception:")
            log_lines.append("Traceback (most recent call last):")
            for frame in range(25):
                log_lines.append(f'  File "module_{frame}.py", line {frame*10}, in handler_{frame}')
                log_lines.append(f"    process_request_{frame}(data)")
            log_lines.append("RuntimeError: database connection pool exhausted")
        elif i % 10 == 0:
            log_lines.append(f"2024-01-01T12:{i//60:02d}:{i%60:02d}Z WARN Connection retry attempt {i}")
        else:
            log_lines.append(f"2024-01-01T12:{i//60:02d}:{i%60:02d}Z INFO Processing request {i} OK")
    scenarios.append({
        "name": "log_dump_with_traces",
        "description": "500-line log dump with embedded stack trace",
        "system": "You are a log analysis assistant. Be concise.",
        "history": [
            {"role": "user", "content": "What errors happened in the last hour?"},
        ],
        "tool_result": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "logs_1",
                 "content": "\n".join(log_lines)}
            ],
        },
        "followup": "What was the error? One sentence.",
    })

    # ── Scenario 4: Multi-tool Accumulated Context ────────────────────────
    # Simulates multiple tool calls accumulating in context
    accumulated = []
    for i in range(8):
        accumulated.append({"role": "user", "content": f"Check component {i}"})
        accumulated.append({"role": "assistant", "content": [
            {"type": "text", "text": f"Checking component {i}..."}
        ]})
        accumulated.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"check_{i}",
             "content": json.dumps({
                 "component": f"comp_{i}",
                 "status": "healthy",
                 "metrics": {
                     "cpu": 45.2 + i,
                     "memory": 68.1 + i * 2,
                     "requests_per_sec": 1200 + i * 100,
                     "error_rate": 0.01 * i,
                     "p99_latency_ms": 120 + i * 15,
                 },
                 "logs": [f"2024-01-01T{12+i}:00:00Z INFO Component {i} healthy"] * 30,
                 "config": {f"setting_{j}": f"value_{j}" for j in range(15)},
                 "_meta": {"version": 1, "cached": True, "etag": None},
             }, indent=2)}
        ]})
    scenarios.append({
        "name": "accumulated_tool_context",
        "description": "8 sequential tool results accumulating in context",
        "system": "You are a system health monitor. Be concise.",
        "history": accumulated,
        "tool_result": None,  # already in history
        "followup": "Give me a one-line summary of overall system health.",
    })

    # ── Scenario 5: Base64 Image in Tool Result ───────────────────────────
    import base64
    fake_image = base64.b64encode(os.urandom(50_000)).decode()
    scenarios.append({
        "name": "base64_image_blob",
        "description": "Tool result containing large base64 image data",
        "system": "You are an image analysis assistant. Be concise.",
        "history": [
            {"role": "user", "content": "What's in this screenshot?"},
        ],
        "tool_result": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "screenshot_1",
                 "content": json.dumps({
                     "filename": "screenshot.png",
                     "width": 1920,
                     "height": 1080,
                     "format": "png",
                     "data": fake_image,
                     "ocr_text": "Dashboard showing 5 healthy services",
                     "metadata": {"captured_at": "2024-01-01T12:00:00Z", "device": None},
                 })}
            ],
        },
        "followup": "What does the screenshot show? One sentence based on the OCR text.",
    })

    return scenarios


# ─── LLM Calling ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LLMResult:
    response_text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: float
    error: str | None = None


def call_llm(messages: list[dict], model: str, label: str = "") -> LLMResult:
    """Call an LLM via OpenRouter and return usage stats."""
    model_info = MODELS[model]
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/skinnytools/benchmark",
        "X-Title": "skinnytools-benchmark",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.1,
    }

    start = time.monotonic()
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        latency = (time.monotonic() - start) * 1000

        if resp.status_code != 200:
            return LLMResult(
                response_text="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=latency,
                cost_usd=0.0,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()

        # Extract response
        choice = data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")

        # Extract usage
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Cost from model pricing
        cost = (prompt_tokens * model_info["input_cost_per_m"] / 1_000_000) + (
            completion_tokens * model_info["output_cost_per_m"] / 1_000_000
        )

        return LLMResult(
            response_text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency,
            cost_usd=cost,
        )

    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            response_text="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency,
            cost_usd=0.0,
            error=str(e),
        )


# ─── Benchmark Runner ────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    name: str
    description: str
    raw_input_chars: int
    filtered_input_chars: int
    char_compression: float
    skinnytools_filter_ms: float
    raw_result: LLMResult | None = None
    filtered_result: LLMResult | None = None


def _flatten_content(content: object) -> str:
    """Flatten Anthropic-style content blocks to plain text for OpenRouter."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    parts.append(f"[Tool Result]\n{block.get('content', '')}")
                elif block.get("type") == "tool_use":
                    parts.append(f"[Tool Call: {block.get('name', '')}]")
                elif block.get("type") == "thinking":
                    parts.append(f"[Thinking]\n{block.get('thinking', '')}")
                elif block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(json.dumps(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _filter_text(text: str) -> str:
    """Run text through skinnytools pipeline if large enough."""
    if len(text) > 1024:
        filtered, _ = process(text, PipelineConfig())
        return filtered
    return text


def build_messages(scenario: dict, filtered: bool = False) -> list[dict]:
    """Build OpenRouter-compatible messages, optionally filtering tool results."""
    messages = []

    # System message
    messages.append({"role": "system", "content": scenario["system"]})

    # History — flatten content blocks to plain text
    for msg in scenario["history"]:
        role = msg["role"]
        content = msg["content"]
        flat = _flatten_content(content)
        if filtered:
            flat = _filter_text(flat)
        # Map roles: tool_result content goes as "user" role
        if role not in ("system", "user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": flat})

    # Tool result (if separate)
    if scenario.get("tool_result"):
        tool_msg = scenario["tool_result"]
        flat = _flatten_content(tool_msg["content"])
        if filtered:
            flat = _filter_text(flat)
        messages.append({"role": "user", "content": flat})

    # Follow-up question
    messages.append({"role": "user", "content": scenario["followup"]})

    # Merge consecutive same-role messages (required by some providers)
    merged = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1] = {
                "role": msg["role"],
                "content": merged[-1]["content"] + "\n\n" + msg["content"],
            }
        else:
            merged.append(dict(msg))
    return merged


def measure_messages_size(messages: list[dict]) -> int:
    """Total character count of all message content."""
    return len(json.dumps(messages))


def run_benchmark():
    """Run the full benchmark suite across all models."""
    if not OPENROUTER_KEY:
        print("ERROR: OPENROUTER_API_KEY not set")
        return

    print("=" * 80)
    print("  skinnytools Benchmark")
    print("  Models: " + ", ".join(m["label"] for m in MODELS.values()))
    print("  Via OpenRouter")
    print("=" * 80)
    print()

    scenarios = build_scenarios()
    all_model_results: dict[str, list[ScenarioResult]] = {}

    for model_id, model_info in MODELS.items():
        label = model_info["label"]
        print()
        print("*" * 80)
        print(f"  MODEL: {label} ({model_id})")
        print("*" * 80)
        print()

        results: list[ScenarioResult] = []

        for i, scenario in enumerate(scenarios, 1):
            name = scenario["name"]
            print(f"  [{i}/{len(scenarios)}] {name}")
            print(f"    {scenario['description']}")

            # Build raw and filtered messages
            raw_messages = build_messages(scenario, filtered=False)

            filter_start = time.monotonic()
            filtered_messages = build_messages(scenario, filtered=True)
            filter_ms = (time.monotonic() - filter_start) * 1000

            raw_size = measure_messages_size(raw_messages)
            filtered_size = measure_messages_size(filtered_messages)
            compression = 1.0 - (filtered_size / raw_size) if raw_size > 0 else 0.0

            print(f"    Raw:      {format_size(raw_size)} chars ({estimate_tokens(json.dumps(raw_messages)):,} est. tokens)")
            print(f"    Filtered: {format_size(filtered_size)} chars ({estimate_tokens(json.dumps(filtered_messages)):,} est. tokens)")
            print(f"    Compression: {compression:.1%} in {filter_ms:.0f}ms")

            result = ScenarioResult(
                name=name,
                description=scenario["description"],
                raw_input_chars=raw_size,
                filtered_input_chars=filtered_size,
                char_compression=compression,
                skinnytools_filter_ms=filter_ms,
            )

            # Call LLM with raw
            print(f"    {label} (raw)...", end=" ", flush=True)
            raw_llm = call_llm(raw_messages, model_id, f"{name}_raw")
            if raw_llm.error:
                print(f"ERROR: {raw_llm.error[:80]}")
            else:
                print(f"{raw_llm.prompt_tokens:,} prompt tok, {raw_llm.latency_ms:.0f}ms, ${raw_llm.cost_usd:.4f}")
            result.raw_result = raw_llm

            # Call LLM with filtered
            print(f"    {label} (filtered)...", end=" ", flush=True)
            filtered_llm = call_llm(filtered_messages, model_id, f"{name}_filtered")
            if filtered_llm.error:
                print(f"ERROR: {filtered_llm.error[:80]}")
            else:
                print(f"{filtered_llm.prompt_tokens:,} prompt tok, {filtered_llm.latency_ms:.0f}ms, ${filtered_llm.cost_usd:.4f}")
            result.filtered_result = filtered_llm

            # Token savings
            if raw_llm.prompt_tokens > 0 and filtered_llm.prompt_tokens > 0:
                token_savings = 1.0 - (filtered_llm.prompt_tokens / raw_llm.prompt_tokens)
                latency_diff = 1.0 - (filtered_llm.latency_ms / raw_llm.latency_ms) if raw_llm.latency_ms > 0 else 0
                print(f"    Token savings: {token_savings:.1%} | Latency: {latency_diff:+.1%}")

            results.append(result)
            print()

        all_model_results[model_id] = results

    # ── Per-Model Summaries ───────────────────────────────────────────────
    grand_raw_tokens = 0
    grand_filt_tokens = 0
    grand_raw_cost = 0.0
    grand_filt_cost = 0.0
    all_output = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "models": {}}

    for model_id, results in all_model_results.items():
        label = MODELS[model_id]["label"]
        print()
        print("=" * 80)
        print(f"  RESULTS: {label}")
        print("=" * 80)
        print()
        print(f"{'Scenario':<30} {'Raw Tok':>10} {'Filt Tok':>10} {'Saved':>8} {'Raw ms':>8} {'Filt ms':>8} {'Speedup':>8}")
        print("-" * 88)

        total_raw_tokens = 0
        total_filt_tokens = 0
        total_raw_cost = 0.0
        total_filt_cost = 0.0
        total_raw_latency = 0.0
        total_filt_latency = 0.0
        valid_count = 0

        for r in results:
            raw = r.raw_result
            filt = r.filtered_result
            if raw and filt and not raw.error and not filt.error:
                savings = 1.0 - (filt.prompt_tokens / raw.prompt_tokens) if raw.prompt_tokens > 0 else 0
                speedup = raw.latency_ms / filt.latency_ms if filt.latency_ms > 0 else 0
                print(
                    f"{r.name:<30} {raw.prompt_tokens:>10,} {filt.prompt_tokens:>10,} "
                    f"{savings:>7.1%} {raw.latency_ms:>7.0f} {filt.latency_ms:>7.0f} "
                    f"{speedup:>7.1f}x"
                )
                total_raw_tokens += raw.prompt_tokens
                total_filt_tokens += filt.prompt_tokens
                total_raw_cost += raw.cost_usd
                total_filt_cost += filt.cost_usd
                total_raw_latency += raw.latency_ms
                total_filt_latency += filt.latency_ms
                valid_count += 1
            else:
                err = (raw.error if raw and raw.error else "") or (filt.error if filt and filt.error else "unknown")
                print(f"{r.name:<30} {'ERROR':>10} {err[:50]}")

        if valid_count > 0:
            print("-" * 88)
            total_savings = 1.0 - (total_filt_tokens / total_raw_tokens) if total_raw_tokens > 0 else 0
            total_speedup = total_raw_latency / total_filt_latency if total_filt_latency > 0 else 0
            print(
                f"{'TOTAL':<30} {total_raw_tokens:>10,} {total_filt_tokens:>10,} "
                f"{total_savings:>7.1%} {total_raw_latency:>7.0f} {total_filt_latency:>7.0f} "
                f"{total_speedup:>7.1f}x"
            )
            print()
            print(f"  Prompt tokens saved: {total_raw_tokens - total_filt_tokens:,}")
            print(f"  Cost without skinnytools:  ${total_raw_cost:.4f}")
            print(f"  Cost with skinnytools:     ${total_filt_cost:.4f}")
            if total_raw_cost > 0:
                print(f"  Cost savings:              ${total_raw_cost - total_filt_cost:.4f} ({1.0 - total_filt_cost/total_raw_cost:.1%})")

            grand_raw_tokens += total_raw_tokens
            grand_filt_tokens += total_filt_tokens
            grand_raw_cost += total_raw_cost
            grand_filt_cost += total_filt_cost

        # Response comparison
        print()
        print(f"  Response Quality ({label}):")
        for r in results:
            raw = r.raw_result
            filt = r.filtered_result
            if raw and filt and not raw.error and not filt.error:
                print(f"    [{r.name}]")
                print(f"      Raw:      {raw.response_text[:100]}")
                print(f"      Filtered: {filt.response_text[:100]}")

        all_output["models"][model_id] = {
            "label": label,
            "scenarios": [
                {
                    "name": r.name,
                    "raw_chars": r.raw_input_chars,
                    "filtered_chars": r.filtered_input_chars,
                    "char_compression": round(r.char_compression, 4),
                    "filter_ms": round(r.skinnytools_filter_ms, 1),
                    "raw_prompt_tokens": r.raw_result.prompt_tokens if r.raw_result else 0,
                    "filtered_prompt_tokens": r.filtered_result.prompt_tokens if r.filtered_result else 0,
                    "raw_latency_ms": round(r.raw_result.latency_ms, 0) if r.raw_result else 0,
                    "filtered_latency_ms": round(r.filtered_result.latency_ms, 0) if r.filtered_result else 0,
                    "raw_response": r.raw_result.response_text[:500] if r.raw_result else "",
                    "filtered_response": r.filtered_result.response_text[:500] if r.filtered_result else "",
                    "raw_error": r.raw_result.error if r.raw_result else None,
                    "filtered_error": r.filtered_result.error if r.filtered_result else None,
                }
                for r in results
            ],
            "totals": {
                "raw_prompt_tokens": total_raw_tokens,
                "filtered_prompt_tokens": total_filt_tokens,
                "token_savings_pct": round(total_savings * 100, 1) if valid_count > 0 else 0,
                "raw_cost_usd": round(total_raw_cost, 6),
                "filtered_cost_usd": round(total_filt_cost, 6),
            },
        }

    # ── Grand Total ───────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  GRAND TOTAL (ALL MODELS)")
    print("=" * 80)
    print(f"  Total prompt tokens (raw):      {grand_raw_tokens:>12,}")
    print(f"  Total prompt tokens (filtered): {grand_filt_tokens:>12,}")
    if grand_raw_tokens > 0:
        print(f"  Token savings:                  {1.0 - grand_filt_tokens/grand_raw_tokens:>11.1%}")
    print(f"  Total cost (raw):               ${grand_raw_cost:>11.4f}")
    print(f"  Total cost (filtered):          ${grand_filt_cost:>11.4f}")
    if grand_raw_cost > 0:
        print(f"  Cost savings:                   ${grand_raw_cost - grand_filt_cost:>11.4f} ({1.0 - grand_filt_cost/grand_raw_cost:.1%})")

    all_output["grand_totals"] = {
        "raw_prompt_tokens": grand_raw_tokens,
        "filtered_prompt_tokens": grand_filt_tokens,
        "raw_cost_usd": round(grand_raw_cost, 6),
        "filtered_cost_usd": round(grand_filt_cost, 6),
    }

    # Save results
    results_path = Path(__file__).parent / "results"
    results_path.mkdir(exist_ok=True)
    out_file = results_path / f"bench_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(all_output, indent=2))
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    run_benchmark()
