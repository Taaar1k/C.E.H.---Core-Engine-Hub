"""Model Registry and Download Utility for C.E.H.

Provides model registration, metadata management, and secure download
with SHA256 verification, atomic writes, resume support, and retry logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_REGISTRY_PATH = Path.home() / ".ceh" / "models.json"
DEFAULT_MODEL_DIR = Path.home() / ".ceh" / "models"

# Download settings
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB
MAX_RETRIES = 5
BASE_BACKOFF = 1.0  # seconds


@dataclass
class ModelInfo:
    """Metadata for a registered model.

    Attributes:
        id: Unique model identifier (e.g. "llama-3.2-3b-instruct-q4_K_M").
        name: Human-readable model name.
        path: Local filesystem path to the model file.
        sha256: Expected SHA256 hex digest of the model file.
        size_bytes: File size in bytes.
        context_window: Context window size in tokens.
        quantization: Quantization scheme (e.g. "Q4_K_M").
        source: Download source URL or repository.
        license: Model license identifier.
        recommended: Whether this is the recommended model for this family.
    """

    id: str
    name: str
    path: str
    sha256: str
    size_bytes: int
    context_window: int
    quantization: str
    source: str
    license: str
    recommended: bool = False


class ModelRegistryError(Exception):
    """Base exception for model registry operations."""


class ModelNotFoundError(ModelRegistryError):
    """Raised when a requested model is not found in the registry."""


class DownloadError(ModelRegistryError):
    """Raised when a model download fails."""


class SHA256MismatchError(DownloadError):
    """Raised when the downloaded file's SHA256 does not match the expected hash."""


class ModelRegistry:
    """JSON-backed model registry.

    Manages model metadata stored in a JSON file (default: ``~/.ceh/models.json``).
    Supports adding, removing, listing, and querying models.

    Attributes:
        registry_path: Path to the JSON manifest file.
    """

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        """Initialize the registry.

        Args:
            registry_path: Path to the JSON manifest. Defaults to ``~/.ceh/models.json``.
        """
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        """Create the registry file and model directory if they don't exist."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._save({"models": []})
            logger.info("Created new model registry at %s", self.registry_path)

    def _load(self) -> Dict[str, Any]:
        """Load the registry from disk.

        Returns:
            Parsed JSON data.

        Raises:
            ModelRegistryError: If the registry file is invalid.
        """
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "models" not in data or not isinstance(data["models"], list):
                raise ModelRegistryError("Invalid registry format: missing 'models' list")
            return data
        except json.JSONDecodeError as exc:
            raise ModelRegistryError(f"Invalid JSON in registry: {exc}") from exc

    def _save(self, data: Dict[str, Any]) -> None:
        """Persist registry data to disk atomically.

        Args:
            data: Registry data to save.
        """
        tmp_path = self.registry_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(str(tmp_path), str(self.registry_path))

    def add_model(self, info: ModelInfo) -> None:
        """Add or update a model in the registry.

        Args:
            info: Model metadata to register.

        Raises:
            ModelRegistryError: If the model data is invalid.
        """
        if not info.id or not info.name or not info.sha256:
            raise ModelRegistryError("Model id, name, and sha256 are required")

        data = self._load()

        # Remove existing entry with same id (update in place)
        data["models"] = [m for m in data["models"] if m.get("id") != info.id]

        # If this model is recommended, unset other recommended flags for same family
        if info.recommended:
            # Simple heuristic: family is derived from name prefix
            family_prefix = info.name.split("-")[0] if "-" in info.name else info.name
            data["models"] = [
                m for m in data["models"] if m.get("name", "").startswith(family_prefix)
            ]

        data["models"].append(asdict(info))
        self._save(data)
        logger.info("Registered model: %s (%s)", info.name, info.id)

    def remove_model(self, model_id: str) -> bool:
        """Remove a model from the registry.

        Args:
            model_id: The model ID to remove.

        Returns:
            True if the model was removed, False if not found.
        """
        data = self._load()
        before = len(data["models"])
        data["models"] = [m for m in data["models"] if m.get("id") != model_id]
        after = len(data["models"])

        if before == after:
            return False

        self._save(data)
        logger.info("Removed model from registry: %s", model_id)
        return True

    def list_models(self) -> List[ModelInfo]:
        """List all registered models.

        Returns:
            List of ModelInfo objects.
        """
        data = self._load()
        return [ModelInfo(**m) for m in data["models"]]

    def get_model(self, model_id: str) -> ModelInfo:
        """Get a model by ID.

        Args:
            model_id: The model ID to look up.

        Returns:
            ModelInfo for the requested model.

        Raises:
            ModelNotFoundError: If the model is not found.
        """
        models = self.list_models()
        for m in models:
            if m.id == model_id:
                return m
        raise ModelNotFoundError(f"Model not found: {model_id}")

    def get_recommended(self) -> Optional[ModelInfo]:
        """Get the recommended model (if any).

        Returns the first model with ``recommended=True``, or ``None`` if no
        recommended model exists.  Falls back to the latest-added model when
        no explicit recommendation is set.

        Returns:
            The recommended ModelInfo, or None if no recommended model exists.
        """
        for m in self.list_models():
            if m.recommended:
                return m
        # Fallback: return the latest-added model (last in the list)
        models = self.list_models()
        return models[-1] if models else None

    def verify_model(self, model_id: str) -> bool:
        """Verify a model file's SHA256 checksum.

        Reads the model file at the registered path and compares its
        computed SHA256 hash against the stored hash.

        Args:
            model_id: The model ID to verify.

        Returns:
            True if the file exists and the SHA256 matches.

        Raises:
            ModelNotFoundError: If the model is not found in the registry.
        """
        info = self.get_model(model_id)
        model_path = Path(info.path)
        if not model_path.is_absolute():
            model_path = DEFAULT_MODEL_DIR / model_path

        if not model_path.exists():
            logger.warning("Model file not found for verification: %s", model_path)
            return False

        sha256_hash = hashlib.sha256()
        with open(model_path, "rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                sha256_hash.update(chunk)

        actual_sha256 = sha256_hash.hexdigest()
        matches = actual_sha256.lower() == info.sha256.lower()

        if matches:
            logger.info("SHA256 verification PASSED for model %s (%s)", info.name, model_id)
        else:
            logger.warning(
                "SHA256 verification FAILED for model %s (%s): expected %s, got %s",
                info.name,
                model_id,
                info.sha256,
                actual_sha256,
            )
        return matches


def download_model(
    url: str,
    destination: str,
    expected_sha256: str,
    registry_path: Optional[Path] = None,
    model_dir: Optional[Path] = None,
) -> str:
    """Download a model file with SHA256 verification.

    Features:
        - HTTPS-only enforcement
        - SHA256 checksum verification after download
        - Atomic rename (downloads to ``.tmp``, renames after verification)
        - Resume support via HTTP ``Range`` headers
        - Retry with exponential backoff (max 5 retries)
        - Cleans up ``.tmp`` on failure

    Args:
        url: HTTPS URL to download from.
        destination: Relative destination path (within model_dir).
        expected_sha256: Expected SHA256 hex digest of the file.
        registry_path: Optional registry path for resolving model IDs.
        model_dir: Optional model directory. Defaults to ``~/.ceh/models/``.

    Returns:
        Absolute path to the downloaded file.

    Raises:
        DownloadError: If the download fails or verification fails.
        SHA256MismatchError: If the file hash doesn't match.
    """
    model_dir = model_dir or DEFAULT_MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    # Resolve destination: if it looks like a model ID, look it up in registry
    if registry_path and not Path(destination).is_absolute():
        try:
            reg = ModelRegistry(registry_path)
            info = reg.get_model(destination)
            destination = info.path
        except ModelNotFoundError:
            pass  # Use destination as-is (relative path)

    abs_destination = Path(destination)
    if not abs_destination.is_absolute():
        abs_destination = model_dir / abs_destination

    tmp_path = abs_destination.with_suffix(abs_destination.suffix + ".tmp")

    def _cleanup() -> None:
        """Remove temporary file on failure."""
        if tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.info("Cleaned up temporary file: %s", tmp_path)
            except OSError as exc:
                logger.warning("Failed to clean up temp file %s: %s", tmp_path, exc)

    last_exception: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Check if we can resume (partial file exists)
            resume_bytes = 0
            if tmp_path.exists():
                resume_bytes = tmp_path.stat().st_size
                logger.info("Resuming download from byte %d", resume_bytes)

            # Build request
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "C.E.H. ModelDownloader/0.1.0")

            if resume_bytes > 0:
                req.add_header("Range", f"bytes={resume_bytes}-")

            # Enforce HTTPS
            if not url.startswith("https://"):
                raise DownloadError("Only HTTPS URLs are allowed")

            with urllib.request.urlopen(req, timeout=300) as response:
                # Handle 206 Partial Content (resume) or 200 OK (fresh download)
                status = response.status
                if status not in (200, 206):
                    raise DownloadError(f"Unexpected HTTP status: {status}")

                total_size = resume_bytes
                if status == 200:
                    content_length = response.getheader("Content-Length")
                    total_size = int(content_length) if content_length else 0
                elif status == 206 and resume_bytes > 0:
                    content_range = response.getheader("Content-Range")
                    if content_range:
                        total_size = int(content_range.split("/")[-1])

                logger.info(
                    "Downloading %s (total: %d bytes, resumed: %d bytes)",
                    url,
                    total_size,
                    resume_bytes,
                )

                # Download with SHA256 streaming
                sha256_hash = hashlib.sha256()

                # If resuming, hash the partial file first
                if resume_bytes > 0:
                    with open(tmp_path, "rb") as f:
                        sha256_hash.update(f.read())

                downloaded = resume_bytes

                # Open file for appending (resume) or writing (fresh)
                mode = "ab" if resume_bytes > 0 else "wb"
                with open(tmp_path, mode) as f:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256_hash.update(chunk)
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Progress logging for large downloads
                        if total_size > 0 and downloaded % (64 * 1024 * 1024) < CHUNK_SIZE:
                            pct = (downloaded / total_size) * 100
                            logger.info("Download progress: %.1f%% (%d/%d bytes)", pct, downloaded, total_size)

                # Verify SHA256
                actual_sha256 = sha256_hash.hexdigest()
                if actual_sha256.lower() != expected_sha256.lower():
                    _cleanup()
                    raise SHA256MismatchError(
                        f"SHA256 mismatch for {destination}: "
                        f"expected {expected_sha256}, got {actual_sha256}"
                    )

                # Atomic rename
                shutil.move(str(tmp_path), str(abs_destination))
                logger.info(
                    "Download complete: %s -> %s (%d bytes)",
                    url,
                    abs_destination,
                    downloaded,
                )
                return str(abs_destination)

        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last_exception = exc
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "Download attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                    attempt,
                    MAX_RETRIES,
                    url,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
            else:
                logger.error("Download failed after %d attempts: %s", MAX_RETRIES, exc)

        except SHA256MismatchError:
            # Don't retry hash mismatches — retrying won't help
            raise

    # All retries exhausted
    _cleanup()
    raise DownloadError(f"Download failed after {MAX_RETRIES} retries: {last_exception}")
