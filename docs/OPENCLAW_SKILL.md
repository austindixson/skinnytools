# OpenClaw Skill

skinnytools ships as an OpenClaw-compatible skill at `openclaw-skill/skinnytools-filter/`.

## Installation

### From this repo

```bash
# 1. Install skinnytools
cd skinnytools
python3 -m venv .venv && .venv/bin/pip install -e .

# 2. Copy the skill to your OpenClaw skills directory
cp -r openclaw-skill/skinnytools-filter ~/.openclaw/workspace/skills/
```

### Quick install

```bash
cd openclaw-skill/skinnytools-filter
./scripts/install.sh
```

## Skill Structure

```
skinnytools-filter/
├── _meta.json          # OpenClaw v1 schema metadata
├── SKILL.md            # Documentation and usage
└── scripts/
    ├── filter.py       # Main filter script
    ├── analyze.py      # Session bloat analyzer
    └── install.sh      # Installation script
```

## _meta.json

The skill metadata follows `openclaw.skill.v1` schema:

```json
{
  "schema": "openclaw.skill.v1",
  "name": "skinnytools-filter",
  "version": "0.1.0",
  "displayName": "SkinnyTools Context Filter | OpenClaw Skill",
  "platform": "openclaw",
  "tools": [
    "skinnytools_filter",
    "skinnytools_analyze",
    "skinnytools_wrap"
  ]
}
```

## Tools

### skinnytools_filter

Filter tool output through the compression pipeline.

```bash
echo "$RAW_TOOL_OUTPUT" | python3 scripts/filter.py --max-size 50000
```

Parameters:
- `content` (required): Raw tool output to filter (via stdin or `--input`)
- `max_size` (optional): Max output size, default 50000
- `disable` (optional): Filters to disable

### skinnytools_analyze

Diagnose bloat in session files.

```bash
python3 scripts/analyze.py /path/to/session.jsonl
```

Parameters:
- `file_path` (required): Session file to analyze

### skinnytools_wrap

Execute and filter in one shot.

```bash
python3 -c "
import subprocess, sys, os
sys.path.insert(0, 'path/to/skinnytools/src')
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig

result = subprocess.run(sys.argv[1:], capture_output=True, text=True)
filtered, _ = process(result.stdout, PipelineConfig())
print(filtered)
" -- your-command --args
```

## Integration with OpenClaw

### Post-tool-call hook

The most effective integration is a post-tool-call hook that filters every `toolResult` automatically:

```typescript
// hooks/openclaw/handler.ts
import { exec } from 'child_process';

const handler = async (event) => {
  if (event.type === 'tool' && event.action === 'result') {
    const content = event.context.toolResult?.content;
    if (content && content.length > 1024) {
      // Pipe through skinnytools
      const filtered = await new Promise((resolve, reject) => {
        const proc = exec('skinnytools filter --max-size 50000');
        let output = '';
        proc.stdout.on('data', (d) => output += d);
        proc.on('close', () => resolve(output));
        proc.stdin.write(content);
        proc.stdin.end();
      });
      event.context.toolResult.content = filtered;
    }
  }
};
```

### sessions_spawn filtering

When using OpenClaw's `sessions_spawn`, filter sub-agent context before it reports back:

```python
# Before returning sub-agent results to parent
from skinnytools.core.pipeline import process
from skinnytools.models.config import PipelineConfig

sub_agent_output = get_sub_agent_result()
filtered, stats = process(sub_agent_output, PipelineConfig())
return filtered  # send compressed result to parent
```

This prevents the recursive amplification that occurs when sub-agent sessions embed their full context in the parent's tool result.

## Why This Matters for OpenClaw

The problem that inspired skinnytools was documented publicly:

> "My bot is even more unresponsive this morning. My first message to him died from context overload. All I said was: 'the computer restarted, can you make sure all of our services are online?' The run died from a 1.5 million token prompt."

The root cause: OpenClaw feeds the model a polluted session transcript full of huge raw `toolResult` blobs, and some of those blobs are copies of the session itself. skinnytools breaks this recursive amplification at the source.
