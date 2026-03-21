---
name: skinnytools
description: "Compress tool results to prevent context window explosion. Use this skill whenever tool output is large (>10KB), when an agent session is dying from context overload, when exec/shell tools return session dumps or huge JSON, when log output is flooding context, or when you need to reduce token costs on any tool result. Also use proactively before appending any tool result to conversation history in agent loops. Activate for any context budget management, tool output filtering, recursive content detection, or session bloat diagnosis."
---

# skinnytools

Compress tool results before they enter context. Prevents the recursive amplification bug where tool output contains copies of the session itself.

## Quick Usage

### Filter tool output (pipe mode)

```bash
# Filter any large output before using it
echo "$TOOL_OUTPUT" | skinnytools filter

# With size limit
echo "$TOOL_OUTPUT" | skinnytools filter --max-size 30000

# See compression stats
echo "$TOOL_OUTPUT" | skinnytools filter --verbose
```

### Wrap a command

```bash
# Execute + filter in one shot
skinnytools wrap kubectl get pods -o json
skinnytools wrap docker logs my-container --tail 1000
skinnytools wrap curl -s https://api.example.com/data
```

### Diagnose bloated sessions

```bash
# Find out WHY a session is too large
skinnytools analyze /path/to/session.jsonl
```

### Python library

```python
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig

filtered, stats = process(raw_tool_output, PipelineConfig())
```

## What It Does

5-stage filter pipeline:

1. **Recursive** — Strips session JSON embedded inside tool results (escaped conversations, nested toolResult blobs, thinking blocks). This is where 90%+ of bloat lives.
2. **Content-aware** — Compresses logs (collapse repeated lines), HTML (strip tags), stack traces (keep error + first/last frame), base64 (replace with size indicator).
3. **JSON compactor** — Strips nulls, empties, metadata keys (`_links`, `_meta`, `_embedded`), collapses whitespace.
4. **Truncator** — Enforces max size (default 50KB) with structure-preserving truncation. Arrays keep first 3 + last 1 items. Objects keep all keys but truncate large values.
5. **File redirect** — Anything still >100KB gets written to a temp file, replaced with a pointer + 500-char preview.

## When to Use

Apply skinnytools filtering on tool results that are:
- Over 10KB (likely contains noise)
- JSON with lots of null/empty fields (API responses)
- Log output (repeated lines, timestamps)
- Any exec/shell output that might contain session data
- Accumulating in a multi-turn agent loop

Do NOT filter:
- Small outputs (<1KB) — they pass through unchanged anyway
- Binary files being written to disk (not context)
- Outputs the user explicitly asked to see in full

## Installation

```bash
pip install skinnytools
```

Or from source:
```bash
git clone https://github.com/RuneweaverStudios/skinnytools.git
cd skinnytools && pip install -e .
```

## Configuration

Works with zero config. Override per-call:

```bash
skinnytools filter --max-size 30000 --budget 300000 --disable file_redirect
```

## Benchmarks

Tested on MiniMax M2.5 and Claude Opus: **74.7% token savings**, **75.2% cost savings**, response quality preserved.
