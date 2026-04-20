# TASK-006: Long-term Stability & Dependency Management

## Metadata
- **Task ID**: TASK-006
- **Title**: Long-term Stability & Dependency Management
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: TASK-001 (Project Initialization)

## Description
Implement dependency pinning, version management, and stability infrastructure. This includes `uv.lock` management, dependency audit procedures, and documentation of the dependency strategy.

## Acceptance Criteria
1. **Dependency Pinning**: All dependencies pinned to specific versions in `pyproject.toml`
2. **uv.lock**: Generated and committed for deterministic builds
3. **Dependency Audit Script**: Script to check for outdated packages and security vulnerabilities
4. **Update Policy Documentation**: Documented policy for dependency updates (quarterly, patch/minor only)
5. **Python Version Lock**: Project locked to Python 3.11 or 3.12 (LTS)
6. **CI Pipeline**: Automated dependency audit in CI (monthly schedule)
7. **No Forbidden Dependencies**: Verify no LangChain, LlamaIndex, CrewAI, Autogen, FastAPI, or Torch

## DoD (Definition of Done)
- [ ] `pyproject.toml` has all dependencies with version constraints as specified
- [ ] `uv.lock` exists and is committed to version control
- [ ] `scripts/audit_deps.sh` script exists and runs successfully:
  - Lists all direct and transitive dependencies
  - Checks for forbidden packages
  - Reports outdated versions
- [ ] `DEPENDENCY_POLICY.md` created with update schedule and approval process
- [ ] GitHub Actions workflow includes dependency audit step (monthly schedule)
- [ ] `python --version` check in CI ensures Python 3.11 or 3.12
- [ ] No forbidden packages in dependency tree
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Dependency audit script should use `uv tree` for dependency listing
- Forbidden packages check:
  ```bash
  uv tree | grep -iE "langchain|llama-index|crewai|autogen|fastapi|torch" && exit 1
  ```
- Update policy:
  - Update dependencies quarterly (first Tuesday of Jan, Apr, Jul, Oct)
  - Only patch/minor updates, no major version bumps without PM approval
  - Always regenerate `uv.lock` and run full test suite after update
  - Document changes in `CHANGELOG.md`
- Python version lock in `pyproject.toml`:
  ```toml
  requires-python = ">=3.11,<3.13"
  ```
- CI schedule: monthly on 1st of each month at 00:00 UTC
