# Architecture

## Overview

skinnytools is a Python CLI tool that compresses tool results before they enter an LLM agent's context window. It sits between tool execution and context insertion, running a configurable pipeline of filters on every tool result.

## System Context

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Agent      │     │ skinnytools  │     │    LLM       │
│  Framework   │────▶│   Pipeline   │────▶│   Context    │
│ (OpenClaw,   │     │              │     │              │
│  ferroclaw)  │     │ 5 filters    │     │  (cleaned)   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │
       │ raw toolResult     │ compressed result
       │ (161K chars)       │ (87 chars)
```

## Relationship to dietmcp

skinnytools and dietmcp are complementary tools that compress opposite sides of the tool interface:

```
                    ┌─────────────┐
                    │    LLM      │
                    │   Context   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
         │ System  │  │  Chat   │  │  Tool   │
         │ Prompt  │  │ History │  │ Results │
         └────┬────┘  └─────────┘  └────┬────┘
              │                         │
         ┌────▼────┐              ┌─────▼─────┐
         │dietmcp  │              │skinnytools │
         │(schemas)│              │ (results)  │
         │ 93%     │              │  75%       │
         └─────────┘              └───────────┘
```

- **dietmcp**: Compresses tool *definitions* (JSON schemas → compact signatures). Reduces what the model needs to know about *available* tools.
- **skinnytools**: Compresses tool *outputs* (raw results → filtered content). Reduces what the model needs to process from *executed* tools.

## Pipeline Architecture

The filter pipeline is the core of skinnytools. Each filter implements the `Filter` protocol:

```python
class Filter(Protocol):
    @property
    def name(self) -> str: ...
    def apply(self, content: str, config: FilterConfig) -> FilterResult: ...
```

Filters are stateless. All state flows through the `FilterResult` return value. The pipeline orchestrator sequences filters and collects per-stage metrics.

### Filter Ordering

The order is critical. Each filter is positioned to maximize the impact of downstream filters:

```
1. RECURSIVE      ← Remove 90%+ of bloat first (session-in-session)
2. CONTENT_AWARE  ← Type-specific compression on remaining content
3. JSON_COMPACTOR ← Strip JSON noise (nulls, empties, metadata)
4. TRUNCATOR      ← Enforce hard size limit on whatever remains
5. FILE_REDIRECT  ← Last resort: write to temp file if still huge
```

Running recursive first means all downstream filters process reasonable-sized content instead of wasting cycles on data that will be deleted.

### Budget Tracker

The `BudgetTracker` is not a filter — it's a controller that sits outside the pipeline. It tracks cumulative token usage across multiple invocations and adjusts the `max_size` parameter passed to the truncator:

```
Budget Pressure    max_size Reduction
     <50%         No reduction
   50-75%         25% smaller
   75-90%         50% smaller
     >90%         75% smaller
```

This creates progressive compression: early tool results get generous budgets, late results get aggressively compressed to keep the session alive.

## Data Flow

```
raw content (str)
     │
     ▼
FilterResult {
  content: str           # the filtered text
  original_size: int     # input size
  filtered_size: int     # output size
  filter_name: str       # which filter produced this
  was_truncated: bool    # was content cut?
  was_redirected: bool   # was content written to file?
  redirect_path: str?    # path to redirect file
  metadata: dict         # filter-specific info
  compression_ratio: float  # computed property
}
     │
     ▼
CompressionStats {
  input_size: int
  output_size: int
  stages: [StageStats]   # per-filter metrics
  total_compression_ratio: float
}
```

All models are frozen pydantic objects. No mutation anywhere in the codebase.

## Module Dependency Graph

```
main.py
  └── cli/*
       └── core/pipeline.py
            ├── filters/registry.py
            │    └── filters/*.py (5 filters)
            │         └── core/patterns.py
            │         └── core/detector.py
            │         └── utils/text.py
            │         └── utils/json_utils.py
            ├── core/budget.py
            └── models/config.py
                 └── models/filter_result.py
                 └── models/stats.py
```

No circular dependencies. Each module has a single responsibility.

## Caching & State

skinnytools is designed to be stateless per-invocation. The only persistence is:

| Location | Purpose | Lifetime |
|----------|---------|----------|
| `~/.config/skinnytools/config.json` | User configuration | Permanent |
| `~/.cache/skinnytools/last_stats.json` | Last run stats | Overwritten each run |
| `~/.cache/skinnytools/redirects/` | Large output files | Auto-cleaned after 1 hour |

No database, no session tracking, no in-memory state between calls. This makes skinnytools safe to run concurrently from multiple agent processes.

## Error Handling

- **CLI layer**: Catches all exceptions, prints user-friendly messages to stderr
- **Filters**: Never raise — if a filter fails (e.g., JSON parse error), content passes through unchanged
- **File operations**: Atomic writes (write to temp file, then `os.replace()`)
- **Stdin**: Hard cap at 100MB to prevent OOM
- **Config**: Missing config file → use defaults silently (no error)
