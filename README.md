# skinnytools

Stop your agent from choking on its own context.

```
161,545 chars in  →  87 chars out  →  99.9% compression  →  28ms
```

skinnytools compresses tool results before they enter an agent's context window. It catches the recursive amplification bug that kills long-running agent sessions — where a tool result contains a copy of the session itself, and the context explodes from 100K to 1.5M tokens in a single turn.

## Install

```bash
pip install skinnytools
```

Or from source:

```bash
git clone https://github.com/RuneweaverStudios/skinnytools.git
cd skinnytools
pip install -e .
```

That's it. No config files needed, no API keys, no setup wizard. It works out of the box with sane defaults.

## Usage

### Pipe any tool output through it

```bash
# Filter output from any command
curl -s https://api.example.com/resources | skinnytools filter

# Filter a file
cat bloated_session.json | skinnytools filter

# See what it did
skinnytools stats
```

### Wrap a command (execute + filter in one shot)

```bash
# Instead of: result=$(my-tool --query "status")
# Do:         result=$(skinnytools wrap my-tool --query "status")

skinnytools wrap kubectl get pods -o json
skinnytools wrap docker logs my-container --tail 1000
skinnytools wrap psql -c "SELECT * FROM large_table"
```

### Diagnose a bloated session

```bash
# Find out WHY your agent is running out of context
skinnytools analyze /path/to/session.jsonl
```

Output:
```
File: session.jsonl
Total size: 84.8M chars

Tool results found: 4,746
Total tool result chars: 35.9M

Top 10 largest tool results:
  1. Entry 9413: 1.2M (1.4%)
  2. Entry 9472: 560.0K (0.7%)

Recursive content detection:
  escaped_conversation: 12 matches, 4.5M chars
  session_array: 3 matches, 2.1M chars

Estimated compression potential: 7.5M chars (8.8% of total)
```

### Use as a Python library

```python
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig

raw = get_tool_result()
filtered, stats = process(raw, PipelineConfig())
# filtered is ready to go into your context
```

### Use as a post-tool-call hook in your agent

```python
from skinnytools.core.pipeline import process
from skinnytools.core.budget import BudgetTracker
from skinnytools.models.config import PipelineConfig

budget = BudgetTracker(total_budget=500_000)

def on_tool_result(content: str) -> str:
    """Call this on every tool result before it enters context."""
    global budget
    filtered, stats = process(content, PipelineConfig(), budget)
    budget = budget.with_consumption(len(filtered))
    return filtered
```

### Pair with dietmcp

[dietmcp](https://github.com/RuneweaverStudios/dietmcp) compresses tool *schemas* (93% reduction). skinnytools compresses tool *results* (75% reduction). Together they compress both sides:

```bash
skinnytools wrap dietmcp exec context7 query-docs \
  --args '{"libraryId": "/express/express", "query": "middleware"}'
```

## What It Actually Does

A 5-stage filter pipeline runs on every tool result:

| Stage | What it does | Why |
|-------|-------------|-----|
| 1. Recursive | Strips session JSON embedded inside tool results | This is where 90%+ of bloat lives |
| 2. Content-aware | Compresses logs, HTML, stack traces, base64 by type | A 500-line log becomes 50 lines |
| 3. JSON compactor | Strips nulls, empties, metadata keys, whitespace | `{"x": null, "_meta": {}}` → `{}` |
| 4. Truncator | Enforces max size, preserving JSON structure | Arrays keep first 3 + last 1 items |
| 5. File redirect | Writes anything still >100KB to a temp file | Returns a pointer + 500-char preview |

Each filter is independently disableable:

```bash
skinnytools filter --disable file_redirect --disable json_compactor
```

## Benchmarks

Real API calls against MiniMax M2.5 and Claude Opus via OpenRouter. Five scenarios simulating production agent workloads:

### Per-Scenario Results (both models combined)

| Scenario | Raw Tokens | Filtered | Saved |
|----------|-----------|----------|-------|
| Recursive session dump (the tweet bug) | 46,864 | 37,908 | 19% |
| Bloated API response (200 items, nulls) | 160,709 | 33,526 | **79%** |
| Log dump with stack traces (500 lines) | 21,919 | 309 | **99%** |
| Accumulated multi-tool context (8 calls) | 15,755 | 15,755 | 0% |
| Base64 image blob (50KB binary) | 102,012 | 273 | **99.7%** |
| **Total** | **347,259** | **87,771** | **74.7%** |

**Cost**: $2.89 → $0.72 = **$2.17 saved (75%)**

### Agent Loop Benchmark

Simulates the real problem — a ReAct loop checking 8 services with tool calls accumulating in context:

| Metric | Raw | skinnytools |
|--------|-----|-------------|
| Total tokens (all turns) | 47,591 | 20,327 |
| **Session token savings** | | **57.3%** |

Response quality is preserved. Both models produce identical answers with filtered input.

### Dev Notes: Benchmark Methodology

The per-scenario benchmark sends flattened tool results as user messages through OpenRouter's chat completions API. It does not use native tool calling — the test measures context compression, not tool invocation. This matches how the problem manifests: bloat comes from `toolResult` content already in conversation history.

The agent loop benchmark uses actual OpenAI-format tool calling (`tools` parameter, `tool_choice: auto`, `role: tool` results). The model makes real `check_service`, `exec_command`, `read_file`, and `get_session_report` tool calls. Simulated tool handlers return realistic results including the recursive case where `get_session_report` embeds the full conversation history.

Full methodology: [docs/BENCHMARKS.md](docs/BENCHMARKS.md)

## Configuration

Works with zero config. Optionally customize:

```bash
# Write a config file (optional)
skinnytools config init

# See current settings
skinnytools config show
```

Config lives at `~/.config/skinnytools/config.json`:

```json
{
  "pipeline": {
    "enabled_filters": ["recursive", "content_aware", "json_compactor", "truncator", "file_redirect"],
    "filter_config": {
      "max_size": 50000,
      "redirect_threshold": 100000,
      "min_match_size": 1024,
      "strip_metadata_keys": ["_links", "_meta", "_embedded", "xmlns", "$schema"],
      "max_log_lines": 50
    },
    "token_budget": 500000
  }
}
```

Or override per-call:

```bash
skinnytools filter --max-size 30000 --budget 300000
```

### Progressive Compression

skinnytools tracks token budget across calls. As context fills up, it compresses harder:

| Budget Used | Compression |
|-------------|------------|
| < 50% | Normal (50KB max) |
| 50-75% | 25% tighter (37.5KB) |
| 75-90% | 50% tighter (25KB) |
| > 90% | 75% tighter (12.5KB) |

This keeps long sessions alive instead of letting them die.

## Install as a Skill

### Claude Code Skill

```bash
# Clone directly into your skills directory
git clone https://github.com/RuneweaverStudios/skinnytools-skill.git \
  ~/.claude/skills/skinnytools
```

Then use `/skinnytools` or let it trigger automatically when Claude detects tool output bloat.

### OpenClaw Skill

```bash
# Clone into OpenClaw skills directory
git clone https://github.com/RuneweaverStudios/skinnytools.git /tmp/skinnytools
cp -r /tmp/skinnytools/openclaw-skill/skinnytools-filter \
  ~/.openclaw/workspace/skills/skinnytools-filter
```

Auto-activates via `nativeSkills: "auto"` — OpenClaw discovers it from `_meta.json`.

## Architecture

```
src/skinnytools/
├── main.py              # CLI entry (click group)
├── cli/                 # Commands: filter, wrap, analyze, stats, config
├── core/
│   ├── pipeline.py      # Orchestrates the 5-stage filter chain
│   ├── patterns.py      # Regex catalog for recursive detection
│   ├── detector.py      # Content-type detection (JSON/logs/HTML/etc)
│   └── budget.py        # Progressive compression controller
├── filters/             # Each filter implements Filter protocol
│   ├── recursive.py     # THE important one — strips recursive session data
│   ├── content_aware.py # Type-specific compression
│   ├── json_compactor.py
│   ├── truncator.py
│   └── file_redirect.py
├── models/              # Frozen pydantic models (no mutation anywhere)
├── utils/               # Token estimation, JSON helpers
└── config/              # Defaults, config loading
```

### Dev Notes: Design Decisions

**Why a pipeline, not a single compressor?** Different types of bloat need different strategies. Recursive embedding needs regex detection. JSON noise needs structural manipulation. Logs need line-level compression. A single function can't do all of these well. The pipeline lets each filter focus on one thing and be independently tested/disabled.

**Why immutable models?** Following dietmcp's pattern. Frozen pydantic models prevent hidden side effects. Every filter receives input and returns a new `FilterResult` — no in-place mutation. This makes the pipeline safe to run concurrently from multiple agent processes.

**Why not stream?** The `filter` command reads all stdin before processing. This is simpler and handles 99% of cases. A future version could add streaming for truly massive inputs, but in practice tool results that are already in a session file are finite strings.

**Why 50KB default?** Empirically, tool results under 50KB rarely cause context problems. Above 50KB, they start eating meaningful chunks of a 200K token budget. The 50KB default balances information preservation with context savings.

## Development

```bash
# Setup
git clone https://github.com/RuneweaverStudios/skinnytools.git
cd skinnytools
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Tests (58 passing)
.venv/bin/python -m pytest tests/ -v

# Coverage
.venv/bin/python -m pytest tests/ --cov=skinnytools

# Benchmarks (needs OPENROUTER_API_KEY in .env)
.venv/bin/python benchmarks/bench_real.py        # per-scenario
.venv/bin/python benchmarks/bench_agent_loop.py   # agent loop
```

### Project Structure

```
skinnytools/
├── src/skinnytools/          # Library + CLI
├── tests/                    # 58 tests (unit + integration)
├── benchmarks/               # Real API benchmarks
│   ├── bench_real.py         # Per-scenario (MiniMax + Opus)
│   └── bench_agent_loop.py   # ReAct loop simulation
├── docs/                     # Architecture, filters, benchmarks
├── openclaw-skill/           # OpenClaw skill package
└── claude-skill/             # Claude Code skill (SKILL.md)
```

## Relation to dietmcp

| | dietmcp | skinnytools |
|--|---------|-------------|
| Compresses | Tool schemas (definitions) | Tool results (output) |
| When | Before tools are sent to model | After tool execution |
| How | Compact type signatures | 5-stage filter pipeline |
| Savings | 93% schema tokens | 75% result tokens |
| Combined | Both sides of the tool interface compressed |

## License

MIT
