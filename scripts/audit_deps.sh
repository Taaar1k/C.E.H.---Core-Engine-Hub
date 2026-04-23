#!/usr/bin/env bash
# audit_deps.sh — Dependency audit script for C.E.H.
# Usage: bash scripts/audit_deps.sh
# Exit codes: 0 = all clear, 1 = issues found

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ISSUES_FOUND=0

echo "=========================================="
echo "  C.E.H. Dependency Audit"
echo "=========================================="
echo ""

# 1. List all direct and transitive dependencies
echo "--- Direct and Transitive Dependencies ---"
if command -v uv &> /dev/null; then
    uv tree 2>/dev/null || echo "WARNING: uv tree failed. Is the environment synced?"
else
    echo "WARNING: 'uv' not found. Install uv from https://github.com/astral-sh/uv"
    echo "Falling back to pip freeze..."
    pip freeze 2>/dev/null || echo "ERROR: Neither 'uv' nor 'pip' available."
fi
echo ""

# 2. Check for forbidden packages
echo "--- Forbidden Package Check ---"
FORBIDDEN_PACKAGES="langchain|llama-index|crewai|autogen|fastapi|torch|transformers|accelerate|sentence-transformers"

if command -v uv &> /dev/null; then
    FORBIDDEN_FOUND=$(uv tree 2>/dev/null | grep -iE "$FORBIDDEN_PACKAGES" || true)
    if [ -n "$FORBIDDEN_FOUND" ]; then
        echo -e "${RED}ERROR: Forbidden packages detected in dependency tree:${NC}"
        echo "$FORBIDDEN_FOUND"
        ISSUES_FOUND=1
    else
        echo -e "${GREEN}OK: No forbidden packages found.${NC}"
    fi
else
    echo "WARNING: Skipping forbidden package check — 'uv' not available."
fi
echo ""

# 3. Report outdated versions
echo "--- Outdated Versions Check ---"
if command -v uv &> /dev/null; then
    # Check if any dependencies have updates available
    OUTDATED=$(uv pip list --outdated 2>/dev/null | grep -v "^Package" || true)
    if [ -n "$OUTDATED" ]; then
        echo -e "${YELLOW}WARNING: Outdated packages detected:${NC}"
        echo "$OUTDATED"
    else
        echo -e "${GREEN}OK: All packages are up to date.${NC}"
    fi
else
    echo "WARNING: Skipping outdated check — 'uv' not available."
    echo "Falling back to pip..."
    OUTDATED=$(pip list --outdated 2>/dev/null | grep -v "^Package" || true)
    if [ -n "$OUTDATED" ]; then
        echo -e "${YELLOW}WARNING: Outdated packages detected:${NC}"
        echo "$OUTDATED"
    else
        echo -e "${GREEN}OK: All packages are up to date.${NC}"
    fi
fi
echo ""

# 4. Verify Python version
echo "--- Python Version Check ---"
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -eq 3 ] && { [ "$MINOR" -eq 11 ] || [ "$MINOR" -eq 12 ]; }; then
    echo -e "${GREEN}OK: Python $PYTHON_VERSION (approved LTS version)${NC}"
else
    echo -e "${YELLOW}WARNING: Python $PYTHON_VERSION is not in the approved range (3.11 or 3.12)${NC}"
fi
echo ""

# 5. Verify uv.lock exists
echo "--- uv.lock Check ---"
if [ -f "uv.lock" ]; then
    echo -e "${GREEN}OK: uv.lock exists${NC}"
else
    echo -e "${RED}ERROR: uv.lock is missing. Run 'uv sync' to generate it.${NC}"
    ISSUES_FOUND=1
fi
echo ""

# Summary
echo "=========================================="
if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}AUDIT PASSED: No critical issues found.${NC}"
else
    echo -e "${RED}AUDIT FAILED: Issues detected. Review above.${NC}"
fi
echo "=========================================="

exit $ISSUES_FOUND
