# Contributing

[简体中文](CONTRIBUTING.md) · **English**

Thank you for helping improve AI Stock Pool.

## Before you submit

1. Do not commit secrets, account information, portfolio screenshots, paid research, or restricted data.
2. Stock mappings must preserve evidence levels. Thematic relevance must not be described as a confirmed supplier or customer relationship.
3. A failed data fetch must never replace valid snapshots with empty CSV files.
4. New features should account for the runtime differences between Vercel and Cloudflare.

## Local checks

```bash
npm install
npm run check
node --check app.js
python3 -m py_compile server.py policy_engine.py discovery_engine.py
```

If the system Python cannot write to the user cache directory, set `PYTHONPYCACHEPREFIX` to a temporary directory and retry.

## Pull requests

- Explain the problem, the change, and the user impact.
- List the checks you ran and any known limitations.
- For data refreshes, include the generation date, signal count, paper count, candidate count, and fetch warnings.
- For UI work, do not turn a research mapping into a definitive investment statement.

