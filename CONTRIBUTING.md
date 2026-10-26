# Contributing to Wordlister

Keep changes small, testable, documented, and safe for authorized security workflows.

## Setup

```bash
git clone https://github.com/Teteration/Wordlister.git
cd Wordlister
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Workflow

1. Create a short-lived branch from `main`.
2. Add or update a behavioral test before changing extraction or HTTP behavior.
3. Implement the smallest complete change.
4. Run the quality checks below.
5. Update README, CHANGELOG, or an ADR when behavior or architecture changes.
6. Open a focused pull request using the repository template.

Use conventional commit prefixes where practical: `feat`, `fix`, `refactor`, `test`, `docs`, and `chore`.

## Quality checks

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

## Design rules

- Keep extraction functions pure unless I/O is their explicit responsibility.
- Keep HTTP, CLI, and orchestration concerns in their owning modules.
- Do not hide target failures with broad silent exception handling.
- Preserve deterministic output regardless of worker completion order.
- Filter sensitive values before tokenization when context is available.
- Add an abstraction only when it removes current duplication or represents a stable boundary.
- Do not add crawling or secondary asset downloads as an incidental change.

## Tests

- Unit tests must not depend on public internet access.
- Use injected fake fetchers and sessions for HTTP behavior.
- Cover success, boundary, and failure paths.
- Security fixes require a regression test.

## Security reports

Do not open a public issue for a suspected vulnerability. Follow [SECURITY.md](SECURITY.md).