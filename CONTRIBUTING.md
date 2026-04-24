# Contributing

Thanks for helping improve Karaya Autopost.

## Development Setup

This project is intentionally small and uses only the Python standard library at runtime.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Contribution Guidelines

- Keep the generator dependency-free unless a dependency clearly improves the project.
- Add or update tests when changing parsing, rendering, config loading, or export behavior.
- Keep source text files in a simple one-entry-per-line format.
- Do not commit generated CSV or JSON exports.
- Do not commit local environment files, credentials, API tokens, or private keys.

## Pull Request Checklist

- Tests pass with `python -m pytest -v`.
- README examples still match the current CLI and config fields.
- New public content has clear source/provenance and can be redistributed.
