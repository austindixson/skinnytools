# skinnytools

Compression toolkit to reduce tool-result payload size before agent-context ingestion.

## Problem
Long-running agents can fail from recursive context amplification.

## Reproducibility
```bash
pip install skinnytools
python -m skinnytools --help
```

## Limits
Compression may remove low-priority detail; keep raw artifacts when needed.
