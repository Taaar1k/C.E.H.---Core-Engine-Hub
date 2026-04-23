"""Tests for the C.E.H. CLI module."""

from typer.testing import CliRunner

from c_e_h.cli import app

runner = CliRunner()


def test_version() -> None:
    """Test that the version command prints the version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "C.E.H. v" in result.stdout


def test_run_help() -> None:
    """Test that the run command shows help."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.stdout


def test_interactive_help() -> None:
    """Test that the interactive command shows help."""
    result = runner.invoke(app, ["interactive", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.stdout
