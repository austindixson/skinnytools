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

## Agent Loop Benchmark

The per-scenario benchmark measures compression on isolated inputs. The agent loop benchmark measures the compounding effect over a real ReAct tool-calling session.

### Setup

The model is asked to check 8 services after a restart. It makes real tool calls (`check_service`, `exec_command`, `read_file`, `get_session_report`) via OpenAI-format function calling. Simulated tool handlers return realistic results, including the recursive case where `get_session_report` embeds the full conversation history.

Two runs: one raw (no filtering), one with skinnytools filtering every tool result.

### Results (MiniMax M2.5)

| Metric | Raw | skinnytools |
|--------|-----|-------------|
| Turns completed | 10 | 3 |
| Tool calls made | 9 | 9 |
| Total tokens (all turns) | 47,591 | 20,327 |
| **Session token savings** | | **57.3%** |

### Dev Notes

The model chose different strategies in each run. Raw: checked services one-at-a-time (1 call/turn, 10 turns). Skinnytools: batched all 8 checks in turn 1, then session report, done in 3 turns. This is realistic — model behavior varies between runs.

The total-tokens-across-all-turns metric is what matters. The raw version re-sends the growing context 10 times; the skinnytools version only sends it 3 times. Fewer turns with the same work done = fewer total tokens billed.

The per-turn context comparison is misleading because batching 8 calls in one turn creates more per-turn content than doing them one at a time. The compounding effect — where recursive embedding causes exponential growth — would be more visible over hundreds of turns, as in the tweeter's 4,746-entry session.

## Running the Benchmarks

```bash
# Set your OpenRouter API key
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# Per-scenario benchmark (MiniMax M2.5 + Claude Opus)
.venv/bin/python benchmarks/bench_real.py

# Agent loop benchmark (MiniMax M2.5)
.venv/bin/python benchmarks/bench_agent_loop.py

# Results saved to benchmarks/results/
```

The per-scenario benchmark makes 20 API calls (5 scenarios x 2 raw/filtered x 2 models). The agent loop benchmark makes 10-20 calls depending on how many turns the model takes. Typical runtime: 2-5 minutes each.
