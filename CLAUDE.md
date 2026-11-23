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

The JSON Schemas in `src/tabledoc/schemas` are served at https://tabledoc.queria.io/schemas/ and their URLs never change. Adding a key keeps the version. Until v1 is fixed, its keys may still be renamed or removed in place; after that, changing what a key means or removing one makes v2.

## Code style

- Python 3.10+: `X | Y` unions are fine; nothing newer
- Comments, docstrings, CLI messages and commit messages in English
- Reading is deterministic: the same files give the same records, keys in the same order

## Commits and releases

Conventional Commits. python-semantic-release (the `Release` workflow, run on every push to main) sets the version from them and releases when there is a `feat:` or `fix:`: `fix:` patch, `feat:` minor. Do not edit the version in pyproject.toml or CHANGELOG.md by hand.
