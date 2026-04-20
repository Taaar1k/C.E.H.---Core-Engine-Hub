# Dependency Policy — C.E.H. (Core Engine Hub)

## Principles

1. **Minimalism**: Max 30 direct dependencies
2. **Stability**: No AI "all-in-one" frameworks
3. **Determinism**: `uv.lock` committed to version control
4. **LTS**: Python 3.11 or 3.12 only

## Approved Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `llama-cpp-python` | `>=0.2.0,<0.4.0` | GGUF model inference |
| `pydantic` | `>=2.5,<3.0` | Schema validation |
| `typer` | `>=0.9,<1.0` | CLI interface |
| `rich` | `>=13.7,<14.0` | TUI output |
| `structlog` | `>=23.0,<25.0` | Structured logging |

## Dev Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `pytest` | `>=7.0` | Testing |
| `ruff` | `>=0.4` | Linting |
| `mypy` | `>=1.8` | Type checking |

## Forbidden Packages

The following packages are **categorically prohibited**:

- `langchain`, `langchain-core` — Unstable API, heavy dependencies
- `llama-index` — RAG-focused, breaks backward compatibility frequently
- `crewai`, `autogen` — Experimental, demo-oriented, cloud-dependent
- `transformers`, `torch` — 2-4 GB overhead, frequent breaking changes
- `fastapi`, `uvicorn` — Unnecessary for local CLI agent

## Update Schedule

| Event | Action |
|-------|--------|
| **Quarterly** (1st Tue of Jan/Apr/Jul/Oct) | Review and update dependencies |
| **Patch/Minor updates** | Auto-approve, update immediately |
| **Major version bumps** | Require PM approval + migration plan |

## Update Procedure

1. Run `uv sync --upgrade`
2. Regenerate `uv.lock`
3. Run full test suite: `uv run pytest tests/ -v`
4. Run linting: `uv run ruff check src/ tests/`
5. Run type checking: `uv run mypy src/`
6. Document changes in `CHANGELOG.md`
7. Commit with message: `chore: bump dependencies to vX.Y.Z`

## Audit Script

```bash
#!/bin/bash
# scripts/audit_deps.sh

echo "=== C.E.H. Dependency Audit ==="
echo ""

echo "Direct dependencies:"
uv tree --depth 1
echo ""

echo "Checking for forbidden packages..."
if uv tree | grep -iE "langchain|llama-index|crewai|autogen|fastapi|torch"; then
    echo "❌ FORBIDDEN PACKAGE DETECTED!"
    exit 1
fi
echo "✅ No forbidden packages"
echo ""

echo "Checking outdated packages..."
uv pip list --outdated 2>/dev/null || echo "(uv pip list --outdated not available, skipping)"
echo ""

echo "Python version:"
python --version
echo ""

echo "✅ Audit complete"
```

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-20 | 0.1.0 | Initial dependency policy |
