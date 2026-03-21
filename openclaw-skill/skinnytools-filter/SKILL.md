# SkinnyTools Context Filter

Drop-in tool result compression for OpenClaw agents. Install it and forget about it — it auto-activates and filters every tool result before it enters your agent's context.

## Install

```bash
# One command. Done.
git clone https://github.com/RuneweaverStudios/skinnytools.git /tmp/skinnytools \
  && cp -r /tmp/skinnytools/openclaw-skill/skinnytools-filter ~/.openclaw/workspace/skills/ \
  && cd ~/.openclaw/workspace/skills/skinnytools-filter && ./scripts/install.sh
```

OpenClaw discovers it automatically via `nativeSkills: "auto"` from the `_meta.json`. No config needed.

## What Happens After Install

Every tool result over 1KB gets filtered through a 5-stage pipeline before entering context:

1. **Recursive stripping** — Catches the killer bug where `exec` returns session JSON containing the full conversation (including previous tool results). This single filter prevents the 1.5M token explosion.
2. **Content-aware compression** — Logs get collapsed, HTML gets tag-stripped, stack traces keep the error + first/last frames, base64 blobs become `[base64 data, 66.7K chars]`.
3. **JSON compaction** — Null values, empty arrays, empty objects, metadata keys (`_links`, `_meta`) all get stripped. Whitespace collapsed.
4. **Smart truncation** — If still over 50KB, arrays keep first 3 + last 1 items. Objects keep all keys but truncate large values.
5. **File redirect** — Anything still over 100KB gets written to a temp file. Your agent gets a pointer + preview.

## The Problem This Solves

Your agent makes tool calls. Each result goes into context. Some results contain copies of the session itself — `exec` dumps, session reports, debug output. This creates recursive amplification:

```
Turn 1:  context = 10KB
Turn 5:  context = 50KB  (tool results accumulating)
Turn 6:  exec returns session dump containing 50KB of context
Turn 7:  context = 150KB (50KB + 50KB dump + new content)
Turn 10: context = 1.5MB (recursive copies compound)
Turn 11: DEAD — prompt too long
```

With skinnytools, that session dump gets compressed to a summary marker and context stays flat.

## Manual Usage

You can also call the tools directly:

```bash
# Filter specific content
echo "$BIG_OUTPUT" | python3 ~/.openclaw/workspace/skills/skinnytools-filter/scripts/filter.py

# Analyze a session file
python3 ~/.openclaw/workspace/skills/skinnytools-filter/scripts/analyze.py session.jsonl

# With options
echo "$OUTPUT" | python3 scripts/filter.py --max-size 30000 --verbose
```

## Benchmarks

Tested on MiniMax M2.5 and Claude Opus across 5 realistic scenarios:

- **74.7% prompt token reduction** (347K → 88K tokens)
- **75.2% cost savings** ($2.89 → $0.72)
- **99.7% compression** on base64 blobs
- **98.6% compression** on log dumps
- Response quality preserved — models give identical answers

Agent loop benchmark (8 services + session report): **57.3% total session token savings**.

## Configuration

Works with zero config. To customize, edit `~/.config/skinnytools/config.json`:

```json
{
  "pipeline": {
    "filter_config": {
      "max_size": 50000,
      "max_log_lines": 50
    }
  }
}
```

## Uninstall

```bash
rm -rf ~/.openclaw/workspace/skills/skinnytools-filter
```
