# Instructions for coding agents

Before changing code:

1. Read [docs/architecture.md](docs/architecture.md): the layers and what
   may import what.
2. Read the doc of the folder you are about to change. Every layer has
   one, named after its folder: `src/fantasy_nhl/analysis/analysis.md`,
   `web/web.md`, `tests/tests.md`, and so on.
3. For a task that spans layers, follow
   [docs/contributing.md](docs/contributing.md).

With the change:

- Update the documentation in the same change, following
  [docs/documentation.md](docs/documentation.md). In particular, a new,
  renamed or removed source file changes the Layout table of its folder's
  doc.
- Regenerate golden transcripts and the API schema only for an intended
  change, only the affected ones, and read the diff. See
  [tests/tests.md](tests/tests.md).

Before finishing, from the repository root:

```bash
.venv/bin/pytest -W error
.venv/bin/python -m pyflakes src/fantasy_nhl tests
npm --prefix web test        # after frontend or API changes
```

The tests never ask ESPN; do not run the apps against real leagues unless
asked to. Never print or log the contents of `secrets.yaml`.
