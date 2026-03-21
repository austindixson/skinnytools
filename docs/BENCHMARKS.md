# Benchmark Results

## Methodology

### Test Scenarios

Five scenarios simulate realistic agent workloads. Each scenario represents a different type of tool result bloat observed in production:

| # | Scenario | Description | Raw Size |
|---|----------|-------------|----------|
| 1 | `recursive_session_dump` | An `exec` tool returns session JSON containing the full conversation history, including prior tool results and assistant thinking blocks. This is the exact bug from the tweet that inspired skinnytools. | 76.6K chars |
| 2 | `bloated_api_response` | A REST API returns 200 items with null fields, empty arrays, metadata keys (`_links`, `_meta`, `_embedded`), and deep nesting. Typical of enterprise APIs. | 275.3K chars |
| 3 | `log_dump_with_traces` | 500 log lines including a 25-frame Python stack trace. Common output from `tail -500 /var/log/app.log`. | 28.8K chars |
| 4 | `accumulated_tool_context` | 8 sequential tool calls, each returning component health data with metrics, logs, config, and metadata. Simulates accumulated context in a multi-step workflow. | 21.4K chars |
| 5 | `base64_image_blob` | A screenshot tool returns a JSON object containing a 50KB base64-encoded PNG alongside OCR text and metadata. | 67.1K chars |

### Models Tested

| Model | Provider | Input Cost | Output Cost |
|-------|----------|-----------|-------------|
| MiniMax M2.5 | OpenRouter | $0.40/M tokens | $1.10/M tokens |
| Claude Opus | OpenRouter | $15.00/M tokens | $75.00/M tokens |

### How the Benchmark Works

For each scenario, the benchmark:

1. **Builds raw messages** — Flattens Anthropic-style content blocks into plain text for the OpenRouter chat completions API, then merges consecutive same-role messages.
2. **Builds filtered messages** — Same as above, but runs each tool result through `skinnytools.core.pipeline.process()` with default `PipelineConfig` before building messages.
3. **Calls the LLM twice** — Once with raw messages, once with filtered. Records prompt tokens, completion tokens, latency, and cost from the OpenRouter response.
4. **Compares** — Token savings, latency difference, cost savings, and response quality.

The benchmark uses `temperature=0.1` and `max_tokens=500` for reproducibility.

### Tool Calling Methodology

The benchmark does **not** use native tool calling (function calling) because the test scenarios measure context compression, not tool invocation. The scenarios present tool results as text content within user messages — the same way they'd appear in a conversation transcript after tool execution.

This matches how the problem manifests in practice: the bloat comes from `toolResult` content already in the conversation history, not from the tool call mechanism itself. The models see the tool output as text and respond to it.

The OpenRouter API is called via `POST /api/v1/chat/completions` with standard `messages` array (system + user + assistant roles). No `tools` or `tool_choice` parameters are sent. This ensures token counts reflect the actual content being processed, with no overhead from tool schema definitions.

## Results — March 20, 2026

### Grand Total

| Metric | Without skinnytools | With skinnytools | Savings |
|--------|-------------------|-----------------|---------|
| Prompt tokens | 347,259 | 87,771 | **74.7%** |
| API cost | $2.89 | $0.72 | **$2.17 saved (75.2%)** |

### MiniMax M2.5

| Scenario | Raw Tokens | Filtered Tokens | Saved | Raw Latency | Filtered Latency | Speedup |
|----------|-----------|----------------|-------|-------------|-----------------|---------|
| recursive_session_dump | 23,120 | 18,647 | 19.3% | 7,151ms | 6,552ms | 1.1x |
| bloated_api_response | 74,610 | 15,566 | **79.1%** | 27,184ms | 2,887ms | **9.4x** |
| log_dump_with_traces | 10,660 | 152 | **98.6%** | 8,154ms | 6,974ms | 1.2x |
| accumulated_tool_context | 7,493 | 7,493 | 0.0% | 9,401ms | 3,871ms | 2.4x |
| base64_image_blob | 44,099 | 136 | **99.7%** | 3,912ms | 3,391ms | 1.2x |
| **Total** | **159,982** | **41,994** | **73.8%** | **55,801ms** | **23,676ms** | **2.4x** |

Cost: $0.0649 → $0.0176 (**72.9% savings**)

### Claude Opus

| Scenario | Raw Tokens | Filtered Tokens | Saved | Raw Latency | Filtered Latency | Speedup |
|----------|-----------|----------------|-------|-------------|-----------------|---------|
| recursive_session_dump | 23,744 | 19,261 | 18.9% | 7,284ms | 6,547ms | 1.1x |
| bloated_api_response | 86,099 | 17,960 | **79.1%** | 9,207ms | 6,682ms | 1.4x |
| log_dump_with_traces | 11,259 | 157 | **98.6%** | 6,166ms | 8,397ms | 0.7x |
| accumulated_tool_context | 8,262 | 8,262 | 0.0% | 6,237ms | 9,931ms | 0.6x |
| base64_image_blob | 57,913 | 137 | **99.8%** | 6,427ms | 4,195ms | 1.5x |
| **Total** | **187,277** | **45,777** | **75.6%** | **35,321ms** | **35,751ms** | **1.0x** |

Cost: $2.82 → $0.70 (**75.2% savings**)

### Response Quality Comparison

Both models produce equivalent answers. Examples:

**Scenario 1: "Are all services online?"**
| | Response |
|-|----------|
| Raw (MiniMax) | "Yes, all 20 services (svc_0 through svc_19) are online and running." |
| Filtered (MiniMax) | "Yes, all 20 services (svc_0 through svc_19) are running. No services are down." |
| Raw (Opus) | "Yes. All services (svc_0 through svc_19) are running. None are down." |
| Filtered (Opus) | "Yes. All services (svc_0 through svc_19) are running." |

**Scenario 2: "How many resources, and name the first 3?"**
| | Response |
|-|----------|
| Raw (MiniMax) | "Total: 5,000. First 3: resource_0, resource_1, resource_2" |
| Filtered (MiniMax) | "Total: 5,000. First 3: resource_0, resource_1, resource_2" |

**Scenario 5: "What does the screenshot show?"**
| | Response |
|-|----------|
| Raw (both) | "Dashboard showing 5 healthy services" |
| Filtered (both) | "Dashboard showing 5 healthy services" |

### Known Trade-Off: Log Truncation

The log scenario (98.6% compression) truncates aggressively enough that the stack trace detail is lost. The model sees a warning but not the actual error. This is tunable:

```bash
# Keep more log context
skinnytools filter --max-size 10000

# Or disable content-aware compression for logs
skinnytools filter --disable content_aware
```

### Per-Filter Contribution

skinnytools pipeline stats from the recursive_session_dump scenario:

```
Input:        76,621 chars
Output:       52,635 chars
Saved:        23,986 chars (31.3%)

Per-filter breakdown:
  recursive            23,900 chars saved (31.2%) [5ms]
  content_aware        (no change) [0ms]
  json_compactor           86 chars saved (0.1%) [1ms]
  truncator            (no change) [0ms]
  file_redirect        (no change) [0ms]
```

For the base64_image_blob scenario:

```
Input:        67,138 chars
Output:           505 chars
Saved:        66,633 chars (99.2%)

Per-filter breakdown:
  recursive            66,500 chars saved (99.1%) [4ms]
  json_compactor          133 chars saved (20.8%) [0ms]
  truncator            (no change) [0ms]
  file_redirect        (no change) [0ms]
```

## 40-Call Agent Session Benchmark

This is the definitive benchmark. 40 tool calls with a fixed schedule, simulating a real infrastructure check. Real token counts measured at 10 checkpoints via MiniMax M2.5 on OpenRouter.

### Setup

The agent manages 8 services after a restart. The tool call schedule is deterministic (no model variance):

| Phase | Calls | Tools |
|-------|-------|-------|
| 1. Service checks | #1-8 | `check_service` x8 |
| 2. Config reads | #9-12 | `read_file` x4 |
| 3. Session report #1 | #13 | `get_session_report` (recursive) |
| 4. Log tailing | #14-21 | `tail_logs` x8 |
| 5. Diagnostics | #22-29 | `exec_command` x8 |
| 6. Session report #2 | #30 | `get_session_report` (recursive) |
| 7. Dependency checks | #31-34 | `check_dependency` x4 |
| 8. Final checks | #35-38 | `exec_command` x3 + `read_file` x1 |
| 9. Session report #3 | #39 | `get_session_report` (recursive) |
| 10. Final report | #40 | `get_session_report` (recursive + artifacts) |

Both runs use the exact same tool calls and results. The only difference: the skinnytools run filters each result through the pipeline before appending to context.

### Results

| | Raw | skinnytools | Savings |
|--|-----|-------------|---------|
| **Final context** | 1.3M chars | 94.1K chars | **92.8%** |
| **Final prompt tokens** | 327,255 | 31,145 | **90.5%** |
| **Session cost** | $0.19 | $0.08 | **58.9%** |

### Token Growth (real API measurements at checkpoints)

| Checkpoint | Raw Tokens | Filtered Tokens | Token Savings |
|-----------|-----------|----------------|---------------|
| Call #1 | 899 | 697 | 22.5% |
| Call #5 | 4,219 | 3,209 | 23.9% |
| Call #10 | 7,080 | 5,464 | 22.8% |
| Call #13 (1st report) | 16,838 | 14,800 | 12.1% |
| Call #20 | 36,679 | 24,908 | 32.1% |
| Call #25 | 40,833 | 27,681 | 32.2% |
| Call #30 (2nd report) | 89,936 | 29,743 | **66.9%** |
| Call #35 | 90,569 | 30,376 | **66.5%** |
| Call #39 (3rd report) | 196,453 | 30,793 | **84.3%** |
| Call #40 (4th report) | 327,255 | 31,145 | **90.5%** |

### The Recursive Bombs

Each session report embeds the full conversation — including all previous session reports. They grow exponentially:

| Call # | Raw Result Size | Filtered Size | Compression |
|--------|----------------|---------------|-------------|
| #13 (1st report) | 25.6K | 24.9K | 2.9% (still small, not much to strip) |
| #30 (2nd report) | 125.4K | 297 bytes | **99.8%** (contains 125K of recursive history) |
| #39 (3rd report) | 275.0K | 297 bytes | **99.9%** (contains 275K of recursive history) |
| #40 (4th report) | 593.2K | 1.1K | **99.8%** (contains 593K of recursive history) |

### Context Growth Acceleration

```
Raw  (calls 1-20):   +111.6K     ← linear growth, normal tool results accumulating
Raw  (calls 21-40):  +1.2M       ← EXPONENTIAL — recursive amplification kicks in

Filt (calls 1-20):   +77.3K      ← similar to raw (small results pass through)
Filt (calls 21-40):  +14.6K      ← FLAT — recursive content stripped
```

Raw context growth is **82x larger** in the second half. This is the recursive amplification bug in action — each session report contains a copy of all previous session reports.

Without skinnytools, this session would hit a 1M token context limit at call #39. With skinnytools, it stays at 31K tokens through all 40 calls.

### Dev Notes

This benchmark uses a deterministic tool schedule (no LLM-driven tool selection) to eliminate model behavior variance between runs. Both the raw and filtered runs execute the exact same 40 tool calls in the same order, producing the same simulated results. The only variable is whether skinnytools filters the results before they enter context.

Token counts are measured by making real API calls to MiniMax M2.5 via OpenRouter at 10 checkpoints. The checkpoint calls use `max_tokens=10` (minimal completion) to minimize cost — we only care about the `prompt_tokens` count, which reflects how many tokens the model would receive if this were a real agent turn.

The first session report (#13) shows only 2.9% compression because the conversation is still small (25K) and most of the content is legitimate tool results, not recursive copies. By report #30, the conversation contains 125K of recursive history and skinnytools strips it to 297 bytes. This matches the real-world pattern: the recursive amplification problem only becomes catastrophic after many tool calls.

## Running the Benchmarks

```bash
# Set your OpenRouter API key
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# 40-call agent session (10 real API calls for token measurement)
.venv/bin/python benchmarks/bench_40_calls.py

# Per-scenario benchmark (MiniMax M2.5 + Claude Opus, 20 API calls)
.venv/bin/python benchmarks/bench_real.py

# Agent loop with LLM-driven tool selection (10-20 API calls)
.venv/bin/python benchmarks/bench_agent_loop.py

# Results saved to benchmarks/results/
```
