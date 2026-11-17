# CLAUDE.md

## Development

```bash
uv sync
uv run tabledoc --help
uv run pytest
```

Docs (Blume, served at https://tabledoc.queria.io):

```bash
npm ci
npm run dev
npm run check   # blume build --strict && blume validate --strict
```

`docs/spec.md` is the specification; change it first, then the code. English is the source and `docs/ja/` mirrors every page in Japanese (plain です・ます, 「バージョン」 not 「版」). Change both in the same PR.

The JSON Schemas in `src/tabledoc/schemas` are served at https://queria-io.github.io/tabledoc/schemas/ and their URLs never change. Adding a key keeps the version; changing what a key means or removing one makes v2.

## Code style

- Python 3.10+: `X | Y` unions are fine; nothing newer
- Comments, docstrings, CLI messages and commit messages in English
- `tabledoc.json` is deterministic: the same input gives the same bytes

## Commits and releases

Conventional Commits. python-semantic-release (manual `Release` workflow) sets the version from them: `fix:` patch, `feat:` minor. Do not edit the version in pyproject.toml or CHANGELOG.md by hand.
