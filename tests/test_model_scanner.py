"""Tests for the C.E.H. model scanner module.

Covers:
- ``scan_for_models()`` discovery, filtering, recursion, permissions
- ``ModelInfo`` dataclass fields
- ``human_readable_size()`` formatting
- Edge cases (empty directories, symlinks)
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from c_e_h.model_scanner import (
    ModelInfo,
    get_default_scan_dir,
    human_readable_size,
    scan_for_models,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def gguf_tree(tmp_path: Path) -> Path:
    """Create a temporary directory tree with .gguf and non-.gguf files.

    Structure::

        tmp_path/
        ├── model1.gguf
        ├── model2.gguf
        ├── readme.txt
        ├── sub/
        │   └── model3.gguf
        │   └── data.bin

    Returns:
        Path to the temporary root directory.
    """
    root = tmp_path / "models"
    root.mkdir()

    # Top-level .gguf files
    (root / "model1.gguf").write_bytes(b"fake gguf data 1")
    (root / "model2.gguf").write_bytes(b"fake gguf data 2")

    # Non-.gguf files
    (root / "readme.txt").write_text("readme")
    (root / "data.bin").write_bytes(b"binary data")

    # Subdirectory with .gguf
    sub = root / "sub"
    sub.mkdir()
    (sub / "model3.gguf").write_bytes(b"fake gguf data 3")
    (sub / "data.bin").write_bytes(b"more binary")

    return root


@pytest.fixture()
def empty_dir(tmp_path: Path) -> Path:
    """Create an empty temporary directory.

    Returns:
        Path to the empty directory.
    """
    d = tmp_path / "empty_models"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# AC-1: scan_for_models tests
# ---------------------------------------------------------------------------

class TestScanForModels:
    """Tests for ``scan_for_models()``."""

    def test_scan_finds_gguf_files(self, gguf_tree: Path) -> None:
        """AC-1: Discovers .gguf files in directory."""
        results = scan_for_models(str(gguf_tree), recursive=False)
        names = {r.name for r in results}
        assert "model1.gguf" in names
        assert "model2.gguf" in names
        assert len(results) == 2

    def test_scan_excludes_non_gguf(self, gguf_tree: Path) -> None:
        """AC-1: Ignores non-.gguf files."""
        results = scan_for_models(str(gguf_tree), recursive=True)
        names = {r.name for r in results}
        assert "readme.txt" not in names
        assert "data.bin" not in names
        # Only .gguf files should be present
        for r in results:
            assert r.name.endswith(".gguf")

    def test_scan_recursive(self, gguf_tree: Path) -> None:
        """AC-1: Finds files in subdirectories."""
        results = scan_for_models(str(gguf_tree), recursive=True)
        names = {r.name for r in results}
        assert "model1.gguf" in names
        assert "model2.gguf" in names
        assert "model3.gguf" in names
        assert len(results) == 3

    def test_scan_non_recursive(self, gguf_tree: Path) -> None:
        """AC-1: Only top-level files when recursive=False."""
        results = scan_for_models(str(gguf_tree), recursive=False)
        names = {r.name for r in results}
        assert "model1.gguf" in names
        assert "model2.gguf" in names
        assert "model3.gguf" not in names  # in sub/
        assert len(results) == 2

    def test_scan_nonexistent_directory(self) -> None:
        """AC-1: Raises FileNotFoundError for non-existent directory."""
        with pytest.raises(FileNotFoundError, match="Scan directory does not exist"):
            scan_for_models("/nonexistent/path/xyz")

    def test_scan_path_is_file(self, gguf_tree: Path) -> None:
        """AC-1: Raises NotADirectoryError when path is a file."""
        file_path = gguf_tree / "model1.gguf"
        with pytest.raises(NotADirectoryError, match="Scan path is not a directory"):
            scan_for_models(str(file_path))

    def test_empty_directory(self, empty_dir: Path) -> None:
        """AC-6: Returns empty list for empty directory."""
        results = scan_for_models(str(empty_dir))
        assert results == []
        assert isinstance(results, list)

    def test_permission_error_handled(self, tmp_path: Path) -> None:
        """AC-1: Skipped directory logged, not raised."""
        # Create a directory with no read permissions
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        (restricted / "secret.gguf").write_bytes(b"secret")

        # Make directory unreadable
        os.chmod(restricted, 0o000)

        try:
            # Scan parent — should log warning but NOT raise
            results = scan_for_models(str(tmp_path), recursive=True)
            # The restricted directory should be skipped
            # (results may or may not contain other files)
            assert isinstance(results, list)
            # No secret.gguf should be discoverable
            names = {r.name for r in results}
            assert "secret.gguf" not in names
        finally:
            # Restore permissions for cleanup
            os.chmod(restricted, 0o755)

    def test_models_sorted_by_modified_descending(self, tmp_path: Path) -> None:
        """AC-3: Rows sorted by modified descending (newest first)."""
        root = tmp_path / "sorted"
        root.mkdir()

        # Create files with different modification times
        file1 = root / "old.gguf"
        file2 = root / "new.gguf"

        file1.write_bytes(b"old")
        file2.write_bytes(b"new")

        # Set explicit modification times
        old_time = datetime(2024, 1, 1).timestamp()
        new_time = datetime(2026, 1, 1).timestamp()

        os.utime(file1, (old_time, old_time))
        os.utime(file2, (new_time, new_time))

        results = scan_for_models(str(root), recursive=False)
        assert len(results) == 2
        # Newest first
        assert results[0].name == "new.gguf"
        assert results[1].name == "old.gguf"

    def test_symlinks_followed(self, tmp_path: Path) -> None:
        """AC-1: Symlinks are followed (not skipped)."""
        root = tmp_path / "real"
        root.mkdir()
        link_root = tmp_path / "links"
        link_root.mkdir()

        # Create real .gguf file
        real_file = root / "real.gguf"
        real_file.write_bytes(b"real model")

        # Create symlink to it
        link_file = link_root / "linked.gguf"
        link_file.symlink_to(real_file)

        results = scan_for_models(str(link_root), recursive=False)
        names = {r.name for r in results}
        assert "linked.gguf" in names


# ---------------------------------------------------------------------------
# AC-1: ModelInfo dataclass tests
# ---------------------------------------------------------------------------

class TestModelInfo:
    """Tests for ``ModelInfo`` dataclass."""

    def test_model_info_fields(self, gguf_tree: Path) -> None:
        """AC-1: Path, name, size, modified all set correctly."""
        results = scan_for_models(str(gguf_tree), recursive=False)
        assert len(results) >= 1

        info = results[0]
        assert isinstance(info, ModelInfo)
        assert isinstance(info.path, Path)
        assert info.path.exists()
        assert isinstance(info.name, str)
        assert info.name.endswith(".gguf")
        assert isinstance(info.size_bytes, int)
        assert info.size_bytes > 0
        assert isinstance(info.modified, datetime)
        # relative_path should be set
        assert isinstance(info.relative_path, str)
        assert info.relative_path.endswith(".gguf")

    def test_model_info_relative_path(self, gguf_tree: Path) -> None:
        """AC-1: relative_path is correct for top-level and nested files."""
        results = scan_for_models(str(gguf_tree), recursive=True)

        top_level = [r for r in results if "/" not in r.relative_path]
        nested = [r for r in results if "/" in r.relative_path]

        assert len(top_level) >= 2  # model1.gguf, model2.gguf
        assert len(nested) >= 1     # sub/model3.gguf

        # Check nested path contains subdirectory
        for n in nested:
            assert n.relative_path.startswith("sub" + os.sep)


# ---------------------------------------------------------------------------
# AC-3: human_readable_size tests
# ---------------------------------------------------------------------------

class TestHumanReadableSize:
    """Tests for ``human_readable_size()``."""

    def test_human_readable_size(self) -> None:
        """AC-3: 1_073_741_824 → '1.0 GB'."""
        assert human_readable_size(1_073_741_824) == "1.0 GB"

    def test_zero_bytes(self) -> None:
        """0 bytes → '0 B'."""
        assert human_readable_size(0) == "0 B"

    def test_bytes_unit(self) -> None:
        """Values < 1024 show as bytes."""
        assert human_readable_size(512) == "512 B"
        assert human_readable_size(1023) == "1023 B"

    def test_kilobytes(self) -> None:
        """1024 bytes → '1.0 KB'."""
        assert human_readable_size(1024) == "1.0 KB"
        assert human_readable_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        """1_048_576 bytes → '1.0 MB'."""
        assert human_readable_size(1_048_576) == "1.0 MB"
        assert human_readable_size(5_242_880) == "5.0 MB"

    def test_gigabytes(self) -> None:
        """Larger values → GB, TB."""
        assert human_readable_size(1_610_612_736) == "1.5 GB"
        assert human_readable_size(1_099_511_627_776) == "1.0 TB"

    def test_negative_size(self) -> None:
        """Negative values handled."""
        result = human_readable_size(-1024)
        assert result.startswith("-")
        assert "KB" in result


# ---------------------------------------------------------------------------
# AC-5: get_default_scan_dir tests
# ---------------------------------------------------------------------------

class TestGetDefaultScanDir:
    """Tests for ``get_default_scan_dir()``."""

    def test_default_when_no_agent_md(self, tmp_path: Path) -> None:
        """Default is 'models/' when no agent.md exists."""
        result = get_default_scan_dir(str(tmp_path / "nonexistent.md"))
        assert result == "models/"

    def test_models_directory_from_agent_md(self, tmp_path: Path) -> None:
        """AC-5: models_directory field in agent.md used as default."""
        import yaml
        agent_md = tmp_path / "agent.md"
        data = {
            "name": "Test-Agent",
            "models_directory": "/custom/models/path",
            "model": {"path": "/custom/models/path/model.gguf"},
        }
        with open(agent_md, "w") as f:
            yaml.dump(data, f)

        result = get_default_scan_dir(str(agent_md))
        assert result == "/custom/models/path"

    def test_fallback_when_models_directory_absent(self, tmp_path: Path) -> None:
        """Fallback to 'models/' when models_directory absent."""
        import yaml
        agent_md = tmp_path / "agent.md"
        data = {
            "name": "Test-Agent",
            "model": {"path": "./models/model.gguf"},
        }
        with open(agent_md, "w") as f:
            yaml.dump(data, f)

        result = get_default_scan_dir(str(agent_md))
        assert result == "models/"
