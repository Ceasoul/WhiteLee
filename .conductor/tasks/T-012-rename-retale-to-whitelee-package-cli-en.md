---
id: T-012
title: Rename ReTale to WhiteLee (package, CLI, env vars, docs)
status: done
priority: 1
depends: []
base: e8db250cac769541ebbb7555a300c82177dc2f2a
---

## Context

The project is being renamed from ReTale to **WhiteLee** (白+李 -> 李白, the
poet-swordsman; fitting for an engine that turns battles into literature)
before its first public release. Renames after publication break links and
installs; now is the only cheap moment. This is a mechanical but total
rename - anything the old name leaks through (imports, CLI, env vars,
output filenames) becomes permanent debt once published.

## Scope

You may touch every file in the repository. Use `git mv` for the package
directory so history is preserved. No new dependencies. No behavior changes
other than names.

## Requirements

1. **Package**: `git mv retale whitelee`; update ALL imports
   (`retale.` -> `whitelee.`) across source and tests.
2. **pyproject.toml**: project name `whitelee`; console script
   `whitelee = "whitelee.cli:main"`; keep version; keywords gain "whitelee".
3. **Environment variables**: rename the prefix `RETALE_` -> `WHITELEE_`
   everywhere (PROVIDER, MODEL, BASE_URL, API_KEY, REASONING_EFFORT).
   No backward-compat shim - the project is unpublished.
4. **CLI surface**: argparse prog name "whitelee"; all stderr log prefixes
   `[retale]` -> `[whitelee]`; default output filenames
   `retale_<game>_<id>` -> `whitelee_<game>_<id>`.
5. **Docs**: README.md / ROADMAP.md / CONTRIBUTING.md: replace the name in
   titles, commands, and paths only (a full README rewrite happens
   separately - do NOT restructure content).
6. **.gitignore**: update `retale_*.md` pattern to `whitelee_*.md`.
7. Repository-wide check: after the rename,
   `git grep -i retale` must return ZERO hits outside `.conductor/`
   (task/report history is archival and must NOT be rewritten).

## Acceptance criteria

- [ ] `pip install -e .` then `whitelee --help` works; `retale` command no
      longer exists.
- [ ] `python -m pytest tests/ -q` passes; `ruff check whitelee/` clean.
- [ ] `git grep -il retale -- ':!.conductor'` output is empty; report this
      command's output verbatim in the notes.
- [ ] `git log --follow whitelee/cli.py` shows pre-rename history
      (confirm in notes).
