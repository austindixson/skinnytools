# Filter Reference

Detailed documentation for each filter in the skinnytools pipeline.

## 1. Recursive Filter

**File**: `src/skinnytools/filters/recursive.py`
**Purpose**: Detect and strip content that has been recursively embedded inside tool results.

### The Problem

When an agent's `exec` tool runs a command that dumps session state, the output contains the entire conversation history — including previous tool results. Those previous tool results may themselves contain earlier session dumps. This creates exponential growth:

```
Turn 1: session = 10KB
Turn 5: session = 50KB, tool result contains 50KB session dump
Turn 6: session = 100KB (50KB + 50KB dump)
Turn 10: session = 1.5MB (recursive copies compound)
```

### How It Works

**Strategy 1: JSON Tree Walking**
If the input is valid JSON, the filter parses it and walks the tree. For every string value longer than `min_match_size` (default 1KB), it checks against 5 regex patterns. If a pattern matches, the string is replaced with a summary marker.

**Strategy 2: Raw Regex**
If the input isn't valid JSON (or if tree walking finds nothing), the filter applies regex patterns directly on the raw text. Matches are replaced from end to start to preserve positions.

### Patterns

| Pattern | Regex Signal | Min Size | Replacement |
|---------|-------------|----------|-------------|
| `escaped_conversation` | `\"role\":\"assistant\"` with escaped quotes | 1KB | `[STRIPPED:escaped_conversation, 5.0K chars]` |
| `session_array` | `"messages":[ ... ]` containing role-based turns | 2KB | `[STRIPPED:session_array, 235.5K chars]` |
| `nested_tool_result` | `"toolResult":{ ... }` inside tool output | 512B | `[STRIPPED:nested_tool_result, 12.0K chars]` |
| `thinking_block` | `"type":"thinking"` or `<thinking>` tags | 500B | `[STRIPPED:thinking_block, 3.2K chars]` |
| `base64_blob` | 500+ chars of `[A-Za-z0-9+/=]` | 500B | `[STRIPPED:base64_blob, 66.7K chars]` |

### Safety

- Content that already contains `[STRIPPED:` markers is not re-processed
- Patterns require minimum match sizes to avoid false positives
- The filter never removes content that doesn't match a known pattern

### Configuration

| Option | Default | Effect |
|--------|---------|--------|
| `min_match_size` | 1024 | Minimum characters for a pattern match to count |

---

## 2. Content-Aware Filter

**File**: `src/skinnytools/filters/content_aware.py`
**Purpose**: Apply type-specific compression based on detected content type.

### Content Type Detection

The detector (`core/detector.py`) classifies content using heuristics:

| Type | Detection Method |
|------|-----------------|
| `JSON_OBJECT` | Parses as `{...}` |
| `JSON_ARRAY` | Parses as `[...]` |
| `LOG_LINES` | 30%+ of lines match `YYYY-MM-DDTHH:MM` |
| `STACK_TRACE` | Contains `Traceback` or `at ` frame patterns |
| `HTML` | Contains `<html>`, `<div>`, `<body>`, etc. |
| `BASE64` | Line of 200+ chars matching `[A-Za-z0-9+/=]` |
| `CSV` | First line matches `word,word,word` pattern |
| `PLAIN_TEXT` | None of the above |

### Type-Specific Handlers

**Logs** (`LOG_LINES`):
- Keep first N/2 and last N/2 lines (N = `max_log_lines`, default 50)
- Detect repeated patterns in the omitted middle section
- Output: head + `[... 450 log lines omitted ...]` + `[repeated: 42x Connection retry]` + tail

**Stack Traces** (`STACK_TRACE`):
- Keep first 3 lines (header + first frame)
- Keep last 3 lines (last frame + error message)
- Output: header + `[... 25 frames omitted ...]` + error

**HTML** (`HTML`):
- Strip `<script>` and `<style>` blocks entirely
- Strip all remaining tags
- Collapse whitespace
- Output: just the text content

**Base64** (`BASE64`):
- Replace base64 blobs (200+ chars) with `[base64 data, 66700 chars]`

**JSON, CSV, PLAIN_TEXT**: Pass through unchanged (handled by other filters).

### Configuration

| Option | Default | Effect |
|--------|---------|--------|
| `max_log_lines` | 50 | Total log lines to keep (half head, half tail) |

---

## 3. JSON Compactor Filter

**File**: `src/skinnytools/filters/json_compactor.py`
**Purpose**: Minify JSON by removing noise that wastes tokens without adding information.

### What It Strips

1. **Null values**: `"field": null` → removed
2. **Empty strings**: `"field": ""` → removed
3. **Empty arrays**: `"field": []` → removed
4. **Empty objects**: `"field": {}` → removed
5. **Metadata keys**: `_links`, `_meta`, `_embedded`, `xmlns`, `$schema` → removed
6. **Whitespace**: `indent=2` → `separators=(",",":")` (compact JSON)

### Example

Before (543 chars):
```json
{
  "id": 42,
  "name": "resource",
  "description": null,
  "tags": [],
  "metadata": {},
  "_links": {"self": "/api/resources/42"},
  "_meta": {"version": 1},
  "nested": {
    "value": "data",
    "empty": null,
    "list": []
  }
}
```

After (35 chars):
```json
{"id":42,"name":"resource","nested":{"value":"data"}}
```

### Non-JSON Content

If the input doesn't parse as JSON, the filter passes it through unchanged with 0% compression.

### Configuration

| Option | Default | Effect |
|--------|---------|--------|
| `strip_metadata_keys` | `_links`, `_meta`, `_embedded`, `xmlns`, `$schema` | Keys to strip from JSON objects |

---

## 4. Truncator Filter

**File**: `src/skinnytools/filters/truncator.py`
**Purpose**: Enforce a hard size limit while preserving structure.

### Truncation Strategies

**JSON Arrays**: Keep first 3 items + last 1 item, with a count marker.
```json
[item0, item1, item2, "[...47 more items...]", item49]
```

**JSON Objects**: Keep all keys, truncate values over 1KB.
```json
{"key1": "normal value", "key2": "[array, 200 items]", "key3": "{object, 15 keys}"}
```

**Plain Text**: Keep first 80% + last 10% of max_size, with a middle marker.
```
HEAD content here...

[... truncated 90,000 chars ...]

...TAIL content here
```

A footer is always appended:
```
[Truncated: 100.0K → 50.0K chars]
```

### Configuration

| Option | Default | Effect |
|--------|---------|--------|
| `max_size` | 50000 | Maximum output size in characters |

---

## 5. File Redirect Filter

**File**: `src/skinnytools/filters/file_redirect.py`
**Purpose**: Last resort for content that's still too large after all other filters.

### Behavior

If content exceeds `redirect_threshold` (default 100KB), the filter:

1. Writes full content to `~/.cache/skinnytools/redirects/skinnytools_XXXXX.txt`
2. Replaces content with a pointer + 500-char preview:

```
[Full output saved to /Users/ghost/.cache/skinnytools/redirects/skinnytools_a1b2c3.txt (245.0K chars)]
Preview: {"data":[{"id":1,"name":"first_item","status":"active"...
```

### Cleanup

On each invocation, the filter cleans up redirect files older than 1 hour. This prevents disk accumulation from long-running agents.

### Configuration

| Option | Default | Effect |
|--------|---------|--------|
| `redirect_threshold` | 100000 | Size threshold for file redirect |

---

## Disabling Filters

Any filter can be disabled via CLI or config:

```bash
# Disable via CLI
skinnytools filter --disable json_compactor --disable file_redirect

# Disable via config (~/.config/skinnytools/config.json)
{
  "pipeline": {
    "enabled_filters": ["recursive", "content_aware", "truncator"]
  }
}
```

## Adding Custom Filters

Implement the `Filter` protocol and register in `filters/registry.py`:

```python
from skinnytools.filters.base import Filter
from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult

class MyFilter:
    @property
    def name(self) -> str:
        return "my_filter"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        # Your compression logic here
        result = content  # modify as needed
        return FilterResult(
            content=result,
            original_size=len(content),
            filtered_size=len(result),
            filter_name=self.name,
        )
```

Then add to `_REGISTRY` in `filters/registry.py`.
