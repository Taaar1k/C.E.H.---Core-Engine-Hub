"""Model scanner — auto-discover .gguf files on disk.

Provides ``scan_for_models()`` to walk a directory tree and collect
metadata about every ``.gguf`` file found.  Also includes a helper
for human-readable byte sizes used in the CLI table display.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Metadata about a discovered GGUF model file.

    Attributes:
        path: Absolute ``Path`` to the model file.
        name: Basename of the model file (e.g. ``"llama-3-8b.Q4_K_M.gguf"``).
        size_bytes: File size in bytes.
        modified: Last-modified timestamp (UTC).
        relative_path: Path relative to the scan root (set after scan).
    """

    path: Path
    name: str
    size_bytes: int
    modified: datetime
    relative_path: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Derive ``relative_path`` from ``path`` when set."""
        if not self.relative_path and hasattr(self, "_scan_root"):
            self.relative_path = str(self.path.relative_to(self._scan_root))


def scan_for_models(
    directory: str,
    recursive: bool = True,
) -> list[ModelInfo]:
    """Scan *directory* for ``.gguf`` model files.

    Args:
        directory: Root directory to scan.
        recursive: If ``True`` (default), descend into subdirectories.
            If ``False``, only the top-level directory is scanned.

    Returns:
        A list of ``ModelInfo`` objects sorted by ``modified``
        descending (newest first).  Permission errors are logged
        and skipped — they never raise.

    Raises:
        FileNotFoundError: If *directory* does not exist.
    """
    root = Path(directory).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Scan directory does not exist: {directory}")
    if not root.is_dir():
        raise NotADirectoryError(f"Scan path is not a directory: {directory}")

    results: list[ModelInfo] = []

    if recursive:
        iter_func = root.rglob("*")
    else:
        iter_func = root.glob("*")

    for entry in iter_func:
        # Path.is_file() already follows symlinks by default (Python 3.11+)
        if entry.is_file() and entry.suffix.lower() == ".gguf":
            try:
                stat = entry.stat()
                info = ModelInfo(
                    path=entry,
                    name=entry.name,
                    size_bytes=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                )
                # Store scan root for relative_path derivation
                object.__setattr__(info, "_scan_root", root)
                info.relative_path = str(entry.relative_to(root))
                results.append(info)
            except PermissionError:
                logger.warning(
                    "Permission denied, skipping: %s", entry
                )
            except OSError as exc:
                logger.warning(
                    "OS error accessing file, skipping: %s — %s", entry, exc
                )

    # Sort by modified descending (newest first)
    results.sort(key=lambda m: m.modified, reverse=True)
    return results


def human_readable_size(size_bytes: int) -> str:
    """Convert a byte count to a human-readable string.

    Examples:
        >>> human_readable_size(0)
        '0 B'
        >>> human_readable_size(1023)
        '1023 B'
        >>> human_readable_size(1024)
        '1.0 KB'
        >>> human_readable_size(1_048_576)
        '1.0 MB'
        >>> human_readable_size(1_073_741_824)
        '1.0 GB'
        >>> human_readable_size(1_610_612_736)
        '1.5 GB'

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable string with appropriate unit (B / KB / MB / GB / TB).
    """
    if size_bytes < 0:
        return f"-{human_readable_size(-size_bytes)}"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[unit_index]}"


def get_default_scan_dir(agent_md_path: str = "agent.md") -> str:
    """Determine the default model scan directory.

    Checks ``agent.md`` for a ``models_directory`` field.  If absent,
    falls back to ``models/`` relative to the project root (working
    directory).

    Args:
        agent_md_path: Path to the ``agent.md`` file.

    Returns:
        Default scan directory path (string).
    """
    default = "models/"
    try:
        import yaml
    except ImportError:
        return default

    agent_path = Path(agent_md_path)
    if agent_path.exists():
        with open(agent_path, "r") as f:
            data = yaml.safe_load(f)
        if data and isinstance(data, dict):
            models_dir = data.get("models_directory")
            if models_dir and isinstance(models_dir, str) and models_dir.strip():
                return models_dir.strip()
    return default
