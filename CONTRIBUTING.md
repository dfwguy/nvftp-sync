# Contributing

`main` must be protected. Changes go through a feature branch, a successful
pipeline, and a human-approved merge request. The integration bot may create
projects, branches, and merge requests; it must never approve or merge them.

Run before publication:

```bash
.venv/bin/ruff check src tests
.venv/bin/pytest -q
.venv/bin/python -m compileall -q src
```

Do not commit Slack tokens, GitLab tokens, NVFTP private keys, customer code,
downloaded artifacts, runtime databases, or logs.

