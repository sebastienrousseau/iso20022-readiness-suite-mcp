# Contributing to iso20022-readiness-suite-mcp

Thank you for your interest in contributing to iso20022-readiness-suite-mcp.
This guide covers the development workflow and standards.

`iso20022-readiness-suite-mcp` is the high-level orchestration Model Context
Protocol (MCP) server of the **ISO 20022 MCP Suite** — the readiness and
testing gateway that composes the foundational suite servers (iso20022-mcp,
camt053-mcp, pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
structured-address-fix-mcp) via the meta-client pattern. Most low-level
message logic lives in those foundational servers; this repository owns the
orchestration, readiness scoring, clearing-profile linting, and bank-response
simulation on top of them.

## Development Setup

### Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/#installation)
- Git with SSH commit signing configured
- (Optional) [`uv`](https://docs.astral.sh/uv/) — used by `make pip-compile`
  and, at runtime, to spawn the foundational sub-servers via `uvx`.

### Setup

```bash
# Clone and install
git clone git@github.com:sebastienrousseau/iso20022-readiness-suite-mcp.git
cd iso20022-readiness-suite-mcp
poetry install

# Verify
poetry run pytest tests/ -q
```

> **Note:** the orchestration tools `run_readiness_check` and
> `remediate_payload` reach the foundational sub-servers, which are spawned
> with `uvx` and must be resolvable at runtime. The test suite injects a fake
> sub-server invoker, so **you do not need the sub-servers installed to run
> the tests** — only to exercise those two tools end to end against real
> servers. `list_profiles` and `simulate_bank_response` are fully local.

### On macOS

```bash
brew install python@3.12 poetry
```

### On Linux (Debian/Ubuntu)

```bash
sudo apt install python3 python3-pip
pip install poetry
```

### On WSL

```bash
sudo apt install python3 python3-pip
pip install poetry
# Ensure ~/.local/bin is in PATH
```

## Workflow

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
3. **Make changes** — follow the coding standards below
4. **Run tests**:
   ```bash
   poetry run pytest tests/ -v
   ```
5. **Run linters**:
   ```bash
   poetry run ruff check iso20022_readiness_suite_mcp/
   poetry run mypy iso20022_readiness_suite_mcp/
   poetry run black --check iso20022_readiness_suite_mcp/ tests/
   ```
6. **Sign and commit**:
   ```bash
   git commit -S -m "feat: add my feature"
   ```
7. **Push** and open a pull request

## Commit Signing (Required)

All commits **must** be signed with SSH or GPG.

### SSH Signing

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519
git config --global commit.gpgsign true
```

### Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add a new orchestration tool
fix: return an error payload instead of raising on a sub-server failure
docs: update README with the MCP client config
test: cover the simulate_bank_response tool
refactor: simplify the profile engine
```

## Coding Standards

- **Line length:** 79 characters (enforced by Black + Ruff)
- **Type hints:** Required on all public functions (mypy strict)
- **Docstrings:** Required on all public classes and functions (interrogate
  at 100%)
- **Tests:** Every new tool or change must include tests
- **Error convention:** tools return an `{"error": ...}` payload rather than
  raising into the MCP client transport

## Testing

```bash
# Full suite (100% line + branch coverage gate)
poetry run pytest tests/ -v

# Single file
poetry run pytest tests/test_server.py -v
```

## Pull Request Checklist

- [ ] All tests pass (`poetry run pytest`)
- [ ] Linters pass (`ruff check`, `mypy`, `black --check`)
- [ ] Commits are signed
- [ ] PR title follows conventional commit format
- [ ] New features include tests and documentation

## License

By contributing, you agree that your contributions will be licensed under
the [Apache License 2.0](LICENSE).
