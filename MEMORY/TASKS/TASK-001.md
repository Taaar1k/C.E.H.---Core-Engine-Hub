# TASK-001: Project Initialization & Scaffolding

## Metadata
- **Task ID**: TASK-001
- **Title**: Project Initialization & Scaffolding
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: None (first task)

## Description
Initialize the C.E.H. (Core Engine Hub) project with proper scaffolding, dependency management, and project structure. This task establishes the foundation for all subsequent development.

## Acceptance Criteria
1. Project directory structure created with all necessary folders
2. `pyproject.toml` configured with specified dependencies and Python 3.11+ requirement
3. `uv.lock` generated for deterministic dependency resolution
4. Virtual environment setup script provided
5. Initial `.gitignore` configured for Python/ML projects
6. README.md with project overview, installation, and usage instructions
7. Initial `agent.md` template created in project root
8. CI configuration (GitHub Actions) for basic linting and testing

## DoD (Definition of Done)
- [ ] All files created and verified in place
- [ ] `pyproject.toml` contains all required dependencies:
  - `llama-cpp-python>=0.2.0,<0.4.0`
  - `pydantic>=2.5,<3.0`
  - `typer>=0.9,<1.0`
  - `rich>=13.7,<14.0`
  - `structlog>=23.0,<25.0`
  - Dev dependencies: `pytest>=7.0`, `ruff>=0.4`, `mypy>=1.8`
- [ ] `uv.lock` file exists and is committed
- [ ] Virtual environment can be created and activated successfully
- [ ] `python -c "import llama_cpp; import pydantic; import typer; import rich; import structlog"` runs without errors
- [ ] README.md contains project overview, installation steps, and basic usage
- [ ] `.gitignore` excludes Python cache, virtual environments, model files, and ML artifacts
- [ ] Initial `agent.md` template exists with placeholder sections
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Use `uv` for dependency management (not pip/poetry)
- Project structure should follow Python best practices:
  ```
  c-e-h/
  ├── pyproject.toml
  ├── uv.lock
  ├── README.md
  ├── .gitignore
  ├── agent.md
  ├── src/
  │   └── c_e_h/
  │       ├── __init__.py
  │       ├── cli.py
  │       ├── agent.py
  │       ├── memory.py
  │       ├── tools.py
  │       └── llama_backend.py
  ├── tests/
  │   ├── __init__.py
  │   └── test_cli.py
  ├── MEMORY/
  │   └── (existing memory files)
  └── scripts/
      └── setup.sh
  ```
- All source code in `src/c_e_h/` namespace
- Tests in `tests/` directory
- Keep initial implementation minimal — only scaffolding, no business logic
