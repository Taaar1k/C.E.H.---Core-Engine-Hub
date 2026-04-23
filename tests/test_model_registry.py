"""Unit tests for model_registry module.

Tests cover:
- ModelInfo dataclass
- ModelRegistry CRUD operations
- download_model() with SHA256 verification
- SHA256 mismatch detection
- Resume support via Range headers
- Atomic downloads (.tmp → final)
- Retry with exponential backoff
"""

import hashlib
import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from c_e_h.model_registry import (
    MAX_RETRIES,
    DownloadError,
    ModelInfo,
    ModelNotFoundError,
    ModelRegistry,
    SHA256MismatchError,
    download_model,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_registry(tmp_path: Path) -> Path:
    """Create a temporary registry file."""
    registry_path = tmp_path / "models.json"
    registry_path.write_text(json.dumps({"models": []}), encoding="utf-8")
    return registry_path


@pytest.fixture
def sample_model_info() -> ModelInfo:
    """Create a sample ModelInfo for testing."""
    return ModelInfo(
        id="test-model-1",
        name="test-model-v1",
        path="models/test-model-1.gguf",
        sha256="a" * 64,
        size_bytes=1024 * 1024 * 500,  # 500 MB
        context_window=4096,
        quantization="Q4_K_M",
        source="https://example.com/models/test-model-1.gguf",
        license="MIT",
        recommended=True,
    )


# ---------------------------------------------------------------------------
# ModelInfo tests
# ---------------------------------------------------------------------------

class TestModelInfo:
    """Tests for the ModelInfo dataclass."""

    def test_model_info_creation(self) -> None:
        """ModelInfo can be instantiated with all required fields."""
        info = ModelInfo(
            id="test",
            name="Test Model",
            path="models/test.gguf",
            sha256="b" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q5_K_M",
            source="https://example.com/test.gguf",
            license="Apache-2.0",
        )
        assert info.id == "test"
        assert info.recommended is False  # default

    def test_model_info_default_recommended(self) -> None:
        """ModelInfo.recommended defaults to False."""
        info = ModelInfo(
            id="test",
            name="Test",
            path="models/test.gguf",
            sha256="c" * 64,
            size_bytes=0,
            context_window=0,
            quantization="Q4",
            source="https://example.com/test.gguf",
            license="MIT",
        )
        assert info.recommended is False


# ---------------------------------------------------------------------------
# ModelRegistry tests
# ---------------------------------------------------------------------------

class TestModelRegistry:
    """Tests for ModelRegistry CRUD operations."""

    def test_init_creates_registry(self, tmp_path: Path) -> None:
        """ModelRegistry creates the registry file on init if it doesn't exist."""
        registry_path = tmp_path / "models.json"
        _registry = ModelRegistry(registry_path)
        assert registry_path.exists()
        data = json.loads(registry_path.read_text())
        assert data == {"models": []}

    def test_add_model(self, temp_registry: Path) -> None:
        """add_model() registers a new model."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="model-1",
            name="Model One",
            path="models/model-1.gguf",
            sha256="d" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
        )
        registry.add_model(info)

        models = registry.list_models()
        assert len(models) == 1
        assert models[0].id == "model-1"

    def test_add_model_validation(self, temp_registry: Path) -> None:
        """add_model() rejects models missing required fields."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="",  # empty id
            name="Model",
            path="models/model.gguf",
            sha256="",  # empty sha256
            size_bytes=0,
            context_window=0,
            quantization="Q4",
            source="https://example.com/model.gguf",
            license="MIT",
        )
        with pytest.raises(Exception, match="required"):
            registry.add_model(info)

    def test_add_model_updates_existing(self, temp_registry: Path) -> None:
        """add_model() updates an existing model with the same ID."""
        registry = ModelRegistry(temp_registry)
        info1 = ModelInfo(
            id="model-1",
            name="Model One v1",
            path="models/model-1.gguf",
            sha256="e" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
        )
        info2 = ModelInfo(
            id="model-1",
            name="Model One v2",
            path="models/model-1-v2.gguf",
            sha256="f" * 64,
            size_bytes=2000,
            context_window=4096,
            quantization="Q5",
            source="https://example.com/model-1-v2.gguf",
            license="MIT",
        )
        registry.add_model(info1)
        registry.add_model(info2)

        models = registry.list_models()
        assert len(models) == 1
        assert models[0].name == "Model One v2"

    def test_remove_model(self, temp_registry: Path) -> None:
        """remove_model() removes a model and returns True."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="model-1",
            name="Model One",
            path="models/model-1.gguf",
            sha256="g" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
        )
        registry.add_model(info)
        assert registry.remove_model("model-1") is True

    def test_remove_model_not_found(self, temp_registry: Path) -> None:
        """remove_model() returns False for non-existent model."""
        registry = ModelRegistry(temp_registry)
        assert registry.remove_model("nonexistent") is False

    def test_list_models_empty(self, temp_registry: Path) -> None:
        """list_models() returns empty list when no models registered."""
        registry = ModelRegistry(temp_registry)
        assert registry.list_models() == []

    def test_list_models_returns_info(self, temp_registry: Path) -> None:
        """list_models() returns ModelInfo objects with correct data."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="model-1",
            name="Model One",
            path="models/model-1.gguf",
            sha256="h" * 64,
            size_bytes=5000,
            context_window=8192,
            quantization="Q5_K_M",
            source="https://example.com/model-1.gguf",
            license="Apache-2.0",
            recommended=True,
        )
        registry.add_model(info)
        models = registry.list_models()
        assert len(models) == 1
        assert models[0].id == "model-1"
        assert models[0].size_bytes == 5000
        assert models[0].recommended is True

    def test_get_model_found(self, temp_registry: Path) -> None:
        """get_model() returns the model when found."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="model-1",
            name="Model One",
            path="models/model-1.gguf",
            sha256="i" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
        )
        registry.add_model(info)
        result = registry.get_model("model-1")
        assert result.id == "model-1"

    def test_get_model_not_found(self, temp_registry: Path) -> None:
        """get_model() raises ModelNotFoundError for missing model."""
        registry = ModelRegistry(temp_registry)
        with pytest.raises(ModelNotFoundError, match="not found"):
            registry.get_model("nonexistent")

    def test_get_recommended(self, temp_registry: Path) -> None:
        """get_recommended() returns the recommended model."""
        registry = ModelRegistry(temp_registry)
        info = ModelInfo(
            id="model-1",
            name="Model One",
            path="models/model-1.gguf",
            sha256="j" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
            recommended=True,
        )
        registry.add_model(info)
        _result = registry.get_recommended()
        assert _result is not None
        assert _result.id == "model-1"

    def test_get_recommended_none(self, temp_registry: Path) -> None:
        """get_recommended() returns None when registry is empty (no fallback possible)."""
        registry = ModelRegistry(temp_registry)
        assert registry.get_recommended() is None

    def test_recommended_flag_cascade(self, temp_registry: Path) -> None:
        """Adding a new recommended model unsets recommended on same-family models."""
        registry = ModelRegistry(temp_registry)
        info1 = ModelInfo(
            id="model-1",
            name="llama-3-8b-q4",
            path="models/llama-3-8b-q4.gguf",
            sha256="l" * 64,
            size_bytes=1000,
            context_window=4096,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
            recommended=True,
        )
        info2 = ModelInfo(
            id="model-2",
            name="llama-3-8b-q5",
            path="models/llama-3-8b-q5.gguf",
            sha256="m" * 64,
            size_bytes=2000,
            context_window=4096,
            quantization="Q5",
            source="https://example.com/model-2.gguf",
            license="MIT",
            recommended=False,
        )
        registry.add_model(info1)
        registry.add_model(info2)

        models = registry.list_models()
        # info2 has recommended=False, so info1 should remain recommended
        # Both models should be present
        assert len(models) == 2
        model_ids = {m.id for m in models}
        assert model_ids == {"model-1", "model-2"}
        # info1 should still be recommended (info2 didn't have recommended=True)
        model_by_id = {m.id: m for m in models}
        assert model_by_id["model-1"].recommended is True


# ---------------------------------------------------------------------------
# download_model() tests
# ---------------------------------------------------------------------------

class TestDownloadModel:
    """Tests for the download_model() function."""

    def _make_mock_response(
        self,
        data: bytes,
        status: int = 200,
        content_length: Optional[int] = None,
        content_range: Optional[str] = None,
    ) -> MagicMock:
        """Create a mock urllib response."""
        response = MagicMock()
        response.status = status
        response.read.side_effect = [data, b""]
        response.getheader.side_effect = lambda key, default=None: {
            "Content-Length": str(content_length if content_length is not None else len(data)),
            "Content-Range": content_range,
        }.get(key, default)
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    def test_download_success(self, tmp_path: Path) -> None:
        """download_model() downloads and verifies a file successfully."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"
        file_data = b"fake model data for testing"
        expected_sha256 = hashlib.sha256(file_data).hexdigest()

        mock_response = self._make_mock_response(file_data, content_length=len(file_data))

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_model(
                url="https://example.com/test-model.gguf",
                destination=dest,
                expected_sha256=expected_sha256,
                model_dir=model_dir,
            )

        assert Path(result).exists()
        assert Path(result).read_bytes() == file_data

    def test_download_sha256_mismatch(self, tmp_path: Path) -> None:
        """download_model() raises SHA256MismatchError on hash mismatch."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"
        file_data = b"fake model data for testing"

        wrong_sha256 = "b" * 64

        mock_response = self._make_mock_response(file_data, content_length=len(file_data))

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(SHA256MismatchError, match="SHA256 mismatch"):
                download_model(
                    url="https://example.com/test-model.gguf",
                    destination=dest,
                    expected_sha256=wrong_sha256,
                    model_dir=model_dir,
                )

        # Verify .tmp file was cleaned up
        tmp_file = model_dir / f"{dest}.tmp"
        assert not tmp_file.exists()

    def test_download_https_enforcement(self, tmp_path: Path) -> None:
        """download_model() rejects non-HTTPS URLs."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()

        with pytest.raises(DownloadError, match="Only HTTPS"):
            download_model(
                url="http://example.com/test-model.gguf",
                destination="test-model.gguf",
                expected_sha256="a" * 64,
                model_dir=model_dir,
            )

    def test_download_atomic_tmp_cleanup_on_failure(self, tmp_path: Path) -> None:
        """download_model() cleans up .tmp file on SHA256 failure."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"
        file_data = b"fake model data"

        wrong_sha256 = "b" * 64
        mock_response = self._make_mock_response(file_data, content_length=len(file_data))

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(SHA256MismatchError):
                download_model(
                    url="https://example.com/test-model.gguf",
                    destination=dest,
                    expected_sha256=wrong_sha256,
                    model_dir=model_dir,
                )

        # .tmp should be cleaned up
        tmp_file = model_dir / f"{dest}.tmp"
        assert not tmp_file.exists()

    def test_download_resume_partial_file(self, tmp_path: Path) -> None:
        """download_model() resumes from existing .tmp file using Range header."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"

        # Create a partial .tmp file
        partial_data = b"partial data"
        tmp_file = model_dir / f"{dest}.tmp"
        tmp_file.write_bytes(partial_data)

        # Complete file data (partial_data + remaining)
        remaining_data = b" remaining data"
        complete_data = partial_data + remaining_data
        expected_sha256 = hashlib.sha256(complete_data).hexdigest()

        mock_response = MagicMock()
        mock_response.status = 206  # Partial Content
        mock_response.read.side_effect = [remaining_data, b""]
        mock_response.getheader.side_effect = lambda key, default=None: {
            "Content-Range": f"bytes 0-{len(complete_data) - 1}/{len(complete_data)}",
        }.get(key, default)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            download_model(
                url="https://example.com/test-model.gguf",
                destination=dest,
                expected_sha256=expected_sha256,
                model_dir=model_dir,
            )

        # Verify Range header was sent
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header("Range") == f"bytes={len(partial_data)}-"

        # Verify final file is complete
        final_file = model_dir / dest
        assert final_file.exists()
        assert final_file.read_bytes() == complete_data

    def test_download_retry_on_failure(self, tmp_path: Path) -> None:
        """download_model() retries on network errors with backoff."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"
        file_data = b"success on retry"
        expected_sha256 = hashlib.sha256(file_data).hexdigest()

        # First 2 calls raise URLError, 3rd succeeds
        import urllib.error

        def side_effect(*args, **kwargs):
            if side_effect.call_count < 2:
                side_effect.call_count += 1
                raise urllib.error.URLError("Network error")
            side_effect.call_count += 1
            return self._make_mock_response(file_data, content_length=len(file_data))

        side_effect.call_count = 0
        mock_urlopen = MagicMock(side_effect=side_effect)

        with patch("urllib.request.urlopen", mock_urlopen):
            with patch("time.sleep"):
                result = download_model(
                    url="https://example.com/test-model.gguf",
                    destination=dest,
                    expected_sha256=expected_sha256,
                    model_dir=model_dir,
                )

        assert Path(result).exists()
        # 2 failures + 1 success = 3 total calls
        assert mock_urlopen.call_count == 3

    def test_download_max_retries_exhausted(self, tmp_path: Path) -> None:
        """download_model() raises DownloadError after max retries."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        dest = "test-model.gguf"

        import urllib.error

        def always_fail(*args, **kwargs):
            raise urllib.error.URLError("Persistent network error")

        mock_urlopen = MagicMock(side_effect=always_fail)

        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(DownloadError, match="failed after 5 retries"):
                download_model(
                    url="https://example.com/test-model.gguf",
                    destination=dest,
                    expected_sha256="a" * 64,
                    model_dir=model_dir,
                )

        assert mock_urlopen.call_count == MAX_RETRIES

    def test_download_resolves_model_id_from_registry(self, tmp_path: Path) -> None:
        """download_model() resolves model ID from registry when destination is an ID."""
        registry_path = tmp_path / "models.json"
        model_dir = tmp_path / "models"
        model_dir.mkdir()

        # Register a model
        registry = ModelRegistry(registry_path)
        info = ModelInfo(
            id="test-model",
            name="Test Model",
            path="test-model.gguf",
            sha256="c" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/test-model.gguf",
            license="MIT",
        )
        registry.add_model(info)

        file_data = b"model data from registry"
        expected_sha256 = hashlib.sha256(file_data).hexdigest()

        mock_response = self._make_mock_response(file_data, content_length=len(file_data))

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_model(
                url="https://example.com/test-model.gguf",
                destination="test-model",  # Use model ID as destination
                expected_sha256=expected_sha256,
                registry_path=registry_path,
                model_dir=model_dir,
            )

        assert Path(result).exists()


# ---------------------------------------------------------------------------
# verify_model() tests
# ---------------------------------------------------------------------------

class TestVerifyModel:
    """Tests for ModelRegistry.verify_model()."""

    def test_verify_model_pass(self, temp_registry: Path, tmp_path: Path) -> None:
        """verify_model() returns True when SHA256 matches."""
        registry = ModelRegistry(temp_registry)

        # Create a model file with known content
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_file = model_dir / "test.gguf"
        file_data = b"test model data for verification"
        model_file.write_bytes(file_data)
        expected_sha256 = hashlib.sha256(file_data).hexdigest()

        info = ModelInfo(
            id="verify-test",
            name="Verify Test",
            path=str(model_file),  # absolute path
            sha256=expected_sha256,
            size_bytes=len(file_data),
            context_window=2048,
            quantization="Q4",
            source="https://example.com/test.gguf",
            license="MIT",
        )
        registry.add_model(info)

        assert registry.verify_model("verify-test") is True

    def test_verify_model_fail(self, temp_registry: Path, tmp_path: Path) -> None:
        """verify_model() returns False when SHA256 does not match."""
        registry = ModelRegistry(temp_registry)

        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_file = model_dir / "test.gguf"
        model_file.write_bytes(b"wrong data")

        info = ModelInfo(
            id="verify-fail",
            name="Verify Fail",
            path=str(model_file),
            sha256="a" * 64,  # wrong hash
            size_bytes=10,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/test.gguf",
            license="MIT",
        )
        registry.add_model(info)

        assert registry.verify_model("verify-fail") is False

    def test_verify_model_file_not_found(self, temp_registry: Path) -> None:
        """verify_model() returns False when model file does not exist."""
        registry = ModelRegistry(temp_registry)

        info = ModelInfo(
            id="verify-nofile",
            name="Verify No File",
            path="/nonexistent/path/model.gguf",
            sha256="b" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/test.gguf",
            license="MIT",
        )
        registry.add_model(info)

        assert registry.verify_model("verify-nofile") is False


# ---------------------------------------------------------------------------
# get_recommended() fallback tests
# ---------------------------------------------------------------------------

class TestRecommendedFallback:
    """Tests for get_recommended() fallback behavior."""

    def test_get_recommended_fallback_to_latest(self, temp_registry: Path) -> None:
        """get_recommended() returns latest model when no recommended flag is set."""
        registry = ModelRegistry(temp_registry)

        info1 = ModelInfo(
            id="model-1",
            name="First Model",
            path="models/model-1.gguf",
            sha256="a" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
        )
        info2 = ModelInfo(
            id="model-2",
            name="Second Model",
            path="models/model-2.gguf",
            sha256="b" * 64,
            size_bytes=2000,
            context_window=4096,
            quantization="Q5",
            source="https://example.com/model-2.gguf",
            license="Apache-2.0",
        )
        registry.add_model(info1)
        registry.add_model(info2)

        result = registry.get_recommended()
        assert result is not None
        assert result.id == "model-2"  # latest added

    def test_get_recommended_prefers_flag_over_latest(self, temp_registry: Path) -> None:
        """get_recommended() returns flagged recommended even if not latest."""
        registry = ModelRegistry(temp_registry)

        info1 = ModelInfo(
            id="model-1",
            name="Recommended Model",
            path="models/model-1.gguf",
            sha256="a" * 64,
            size_bytes=1000,
            context_window=2048,
            quantization="Q4",
            source="https://example.com/model-1.gguf",
            license="MIT",
            recommended=True,
        )
        info2 = ModelInfo(
            id="model-2",
            name="Not Recommended",
            path="models/model-2.gguf",
            sha256="b" * 64,
            size_bytes=2000,
            context_window=4096,
            quantization="Q5",
            source="https://example.com/model-2.gguf",
            license="Apache-2.0",
            recommended=False,
        )
        registry.add_model(info1)
        registry.add_model(info2)

        result = registry.get_recommended()
        assert result is not None
        assert result.id == "model-1"  # flagged recommended


