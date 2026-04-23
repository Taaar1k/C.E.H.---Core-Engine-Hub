"""Tests for the C.E.H. profile manager module.

Covers:
- ``EasyProfile`` and ``AdvancedProfile`` Pydantic model validation
- ``ProfileManager`` CRUD operations (create, read, update, delete, clone, list)
- Default profile creation on first use
- YAML format (multi-document with ``---`` separators)
- Invalid profile rejection (Pydantic validation errors)
- ``ProfileCompleter`` TAB completion
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from c_e_h.profile_manager import (
    DEFAULT_PROFILE_NAME,
    AdvancedProfile,
    EasyProfile,
    ProfileCompleter,
    ProfileManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pm(tmp_path: Path) -> ProfileManager:
    """Create a ``ProfileManager`` pointing at a temporary YAML file.

    Returns:
        ``ProfileManager`` instance with ``profiles_path`` set to
        ``tmp_path / "profiles.yaml"``.
    """
    profiles_path = tmp_path / "profiles.yaml"
    return ProfileManager(profiles_path=profiles_path)


@pytest.fixture()
def easy_profile_data() -> dict:
    """Standard EasyProfile parameters for Pydantic model tests (with name)."""
    return {
        "name": "test-easy",
        "model": "/path/to/model.gguf",
        "n_gpu_layers": -1,
        "threads": 8,
        "ctx_size": 8192,
        "flash_attn": "auto",
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "n_cpu_moe_draft": 0,
    }


@pytest.fixture()
def advanced_profile_data(easy_profile_data: dict) -> dict:
    """Standard AdvancedProfile parameters (with name from easy_profile_data)."""
    data = dict(easy_profile_data)
    data.update(
        {
            "lora": "/path/to/lora.gguf",
            "temperature": 0.7,
            "top_k": 40,
            "top_p": 0.95,
            "server": True,
            "port": 8080,
        }
    )
    return data


@pytest.fixture()
def easy_profile_no_name() -> dict:
    """EasyProfile parameters without name — for ProfileManager.create() calls."""
    return {
        "model": "/path/to/model.gguf",
        "n_gpu_layers": -1,
        "threads": 8,
        "ctx_size": 8192,
        "flash_attn": "auto",
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "n_cpu_moe_draft": 0,
    }


# ---------------------------------------------------------------------------
# AC-2: EasyProfile Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestEasyProfile:
    """Tests for ``EasyProfile`` Pydantic model."""

    def test_create_easy_profile_valid(self, easy_profile_data: dict) -> None:
        """EasyProfile validates and serializes correctly."""
        profile = EasyProfile(**easy_profile_data)
        assert profile.name == "test-easy"
        assert profile.model == "/path/to/model.gguf"
        assert profile.n_gpu_layers == -1
        assert profile.threads == 8
        assert profile.ctx_size == 8192
        assert profile.flash_attn == "auto"
        assert profile.cache_type_k == "q8_0"
        assert profile.cache_type_v == "q8_0"
        assert profile.n_cpu_moe_draft == 0

    def test_easy_profile_defaults(self) -> None:
        """EasyProfile uses correct default values."""
        profile = EasyProfile(name="minimal", model="/model.gguf")
        assert profile.n_gpu_layers == -1
        assert profile.threads is None
        assert profile.ctx_size == 8192
        assert profile.flash_attn == "auto"
        assert profile.cache_type_k == "q8_0"
        assert profile.cache_type_v == "q8_0"
        assert profile.n_cpu_moe_draft == 0

    def test_easy_profile_flash_attn_validation(self) -> None:
        """EasyProfile rejects invalid flash_attn values."""
        with pytest.raises(ValidationError, match="flash_attn"):
            EasyProfile(name="bad", model="/model.gguf", flash_attn="invalid")

    def test_easy_profile_to_dict(self, easy_profile_data: dict) -> None:
        """EasyProfile.to_dict() returns correct dictionary."""
        profile = EasyProfile(**easy_profile_data)
        d = profile.to_dict()
        assert d["name"] == "test-easy"
        assert d["model"] == "/path/to/model.gguf"
        assert "n_gpu_layers" in d


# ---------------------------------------------------------------------------
# AC-3: AdvancedProfile Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestAdvancedProfile:
    """Tests for ``AdvancedProfile`` Pydantic model."""

    def test_create_advanced_profile_valid(
        self, advanced_profile_data: dict
    ) -> None:
        """AdvancedProfile validates and serializes correctly."""
        profile = AdvancedProfile(**advanced_profile_data)
        assert profile.name == "test-easy"
        assert profile.lora == "/path/to/lora.gguf"
        assert profile.temperature == 0.7
        assert profile.top_k == 40
        assert profile.top_p == 0.95
        assert profile.server is True
        assert profile.port == 8080

    def test_advanced_profile_inherits_easy(self, easy_profile_data: dict) -> None:
        """AdvancedProfile inherits all EasyProfile fields."""
        profile = AdvancedProfile(**easy_profile_data)
        assert profile.ctx_size == 8192
        assert profile.flash_attn == "auto"
        assert profile.cache_type_k == "q8_0"

    def test_advanced_profile_optional_fields(self) -> None:
        """AdvancedProfile optional fields default to None."""
        profile = AdvancedProfile(name="minimal", model="/model.gguf")
        assert profile.lora is None
        assert profile.temperature is None
        assert profile.server is None
        assert profile.port is None

    def test_advanced_profile_to_dict(self, advanced_profile_data: dict) -> None:
        """AdvancedProfile.to_dict() returns correct dictionary."""
        profile = AdvancedProfile(**advanced_profile_data)
        d = profile.to_dict()
        assert d["name"] == "test-easy"
        assert d["lora"] == "/path/to/lora.gguf"
        assert d["server"] is True


# ---------------------------------------------------------------------------
# AC-4: Profile CRUD Operations Tests
# ---------------------------------------------------------------------------


class TestProfileManagerCreate:
    """Tests for ``ProfileManager.create()``."""

    def test_create_easy_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """EasyProfile validated and saved."""
        pm.create("test-easy", "easy", **easy_profile_no_name)
        saved = pm.read("test-easy")
        assert saved["name"] == "test-easy"
        assert saved["model"] == "/path/to/model.gguf"
        assert saved["ctx_size"] == 8192

    def test_create_advanced_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """AdvancedProfile validated and saved."""
        params = dict(easy_profile_no_name)
        params.update(
            {
                "lora": "/path/to/lora.gguf",
                "temperature": 0.7,
                "top_k": 40,
                "top_p": 0.95,
                "server": True,
                "port": 8080,
            }
        )
        pm.create("test-adv", "advanced", **params)
        saved = pm.read("test-adv")
        assert saved["name"] == "test-adv"
        assert saved["lora"] == "/path/to/lora.gguf"
        assert saved["temperature"] == 0.7

    def test_create_duplicate_rejected(self, pm: ProfileManager) -> None:
        """Creating a profile with duplicate name raises ValueError."""
        pm.create("dup", "easy", model="/model.gguf")
        with pytest.raises(ValueError, match="already exists"):
            pm.create("dup", "easy", model="/other.gguf")


class TestProfileManagerRead:
    """Tests for ``ProfileManager.read()``."""

    def test_read_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """Profile loaded correctly from YAML."""
        pm.create("read-test", "easy", **easy_profile_no_name)
        profile = pm.read("read-test")
        assert profile["name"] == "read-test"
        assert profile["model"] == "/path/to/model.gguf"
        assert profile["threads"] == 8

    def test_read_nonexistent_raises(self, pm: ProfileManager) -> None:
        """Reading a nonexistent profile raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            pm.read("nonexistent")


class TestProfileManagerUpdate:
    """Tests for ``ProfileManager.update()``."""

    def test_update_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """Fields updated in-place."""
        pm.create("update-test", "easy", **easy_profile_no_name)
        pm.update("update-test", ctx_size=16384, threads=16)
        profile = pm.read("update-test")
        assert profile["ctx_size"] == 16384
        assert profile["threads"] == 16
        # Other fields unchanged
        assert profile["model"] == "/path/to/model.gguf"

    def test_update_nonexistent_raises(self, pm: ProfileManager) -> None:
        """Updating a nonexistent profile raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            pm.update("nonexistent", ctx_size=100)


class TestProfileManagerDelete:
    """Tests for ``ProfileManager.delete()``."""

    def test_delete_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """Profile removed from YAML."""
        pm.create("del-test", "easy", **easy_profile_no_name)
        assert "del-test" in pm.list()
        pm.delete("del-test")
        assert "del-test" not in pm.list()
        with pytest.raises(ValueError, match="not found"):
            pm.read("del-test")

    def test_delete_nonexistent_raises(self, pm: ProfileManager) -> None:
        """Deleting a nonexistent profile raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            pm.delete("nonexistent")


class TestProfileManagerList:
    """Tests for ``ProfileManager.list()``."""

    def test_list_profiles(self, pm: ProfileManager) -> None:
        """Returns all profile names."""
        pm.create("a", "easy", model="/a.gguf")
        pm.create("b", "easy", model="/b.gguf")
        pm.create("c", "easy", model="/c.gguf")
        names = pm.list()
        # default profile + a, b, c
        assert sorted(names) == ["a", "b", "c", "default"]

    def test_list_empty(self, pm: ProfileManager) -> None:
        """Returns empty list when no profiles created (only default)."""
        # Default profile is created on init
        names = pm.list()
        assert DEFAULT_PROFILE_NAME in names


class TestProfileManagerClone:
    """Tests for ``ProfileManager.clone()``."""

    def test_clone_profile(
        self, pm: ProfileManager, easy_profile_no_name: dict
    ) -> None:
        """New profile created with same params."""
        pm.create("source", "easy", **easy_profile_no_name)
        pm.clone("source", "cloned")
        source = pm.read("source")
        cloned = pm.read("cloned")
        assert cloned["name"] == "cloned"
        assert cloned["model"] == source["model"]
        assert cloned["ctx_size"] == source["ctx_size"]
        # Names differ
        assert source["name"] != cloned["name"]

    def test_clone_nonexistent_source_raises(self, pm: ProfileManager) -> None:
        """Cloning a nonexistent source raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            pm.clone("nonexistent", "cloned")

    def test_clone_duplicate_name_raises(self, pm: ProfileManager) -> None:
        """Cloning to an existing name raises ValueError."""
        pm.create("a", "easy", model="/a.gguf")
        pm.create("b", "easy", model="/b.gguf")
        with pytest.raises(ValueError, match="already exists"):
            pm.clone("a", "b")


# ---------------------------------------------------------------------------
# AC-5: TAB Completion Tests
# ---------------------------------------------------------------------------


class TestProfileCompleter:
    """Tests for ``ProfileCompleter`` TAB completion."""

    def test_complete_partial(self) -> None:
        """TAB completion of partial profile names."""
        completer = ProfileCompleter(["alpha", "beta", "gamma"])
        assert completer.complete("al") == ["alpha"]
        assert completer.complete("be") == ["beta"]
        assert completer.complete("g") == ["gamma"]

    def test_complete_empty(self) -> None:
        """Empty input returns all profiles."""
        completer = ProfileCompleter(["alpha", "beta"])
        assert completer.complete("") == ["alpha", "beta"]

    def test_complete_no_match(self) -> None:
        """No match returns empty list."""
        completer = ProfileCompleter(["alpha", "beta"])
        assert completer.complete("xyz") == []

    def test_get_next(self) -> None:
        """Arrow key navigation cycles through profiles."""
        completer = ProfileCompleter(["a", "b", "c"])
        assert completer.get_next() == "a"
        assert completer.get_next() == "b"
        assert completer.get_next() == "c"
        assert completer.get_next() == "a"  # wraps around

    def test_reset(self) -> None:
        """Reset resets navigation index."""
        completer = ProfileCompleter(["a", "b", "c"])
        completer.get_next()  # advance to "b"
        completer.reset()
        assert completer.get_next() == "a"

    def test_get_completer(self, pm: ProfileManager) -> None:
        """ProfileManager.get_completer() returns ProfileCompleter."""
        pm.create("x", "easy", model="/x.gguf")
        completer = pm.get_completer()
        assert isinstance(completer, ProfileCompleter)
        assert "x" in completer.complete("")


# ---------------------------------------------------------------------------
# AC-6: Additional Tests
# ---------------------------------------------------------------------------


class TestDefaultProfile:
    """Tests for default profile creation."""

    def test_default_profile_created(
        self, tmp_path: Path
    ) -> None:
        """profiles.yaml created on first use."""
        profiles_path = tmp_path / "profiles.yaml"
        assert not profiles_path.exists()
        pm = ProfileManager(profiles_path=profiles_path)
        assert profiles_path.exists()
        names = pm.list()
        assert DEFAULT_PROFILE_NAME in names

    def test_default_profile_content(self, tmp_path: Path) -> None:
        """Default profile has correct content."""
        profiles_path = tmp_path / "profiles.yaml"
        pm = ProfileManager(profiles_path=profiles_path)
        default = pm.read(DEFAULT_PROFILE_NAME)
        assert default["name"] == DEFAULT_PROFILE_NAME
        assert default["n_gpu_layers"] == -1
        assert default["ctx_size"] == 8192


class TestYamlFormat:
    """Tests for YAML file format."""

    def test_yaml_format(self, pm: ProfileManager) -> None:
        """Multi-document YAML with ``---`` separators."""
        pm.create("p1", "easy", model="/p1.gguf")
        pm.create("p2", "easy", model="/p2.gguf")

        content = pm.profiles_path.read_text(encoding="utf-8")
        # Check for document separators
        assert "---" in content

        # Verify it parses as multi-document YAML
        docs = list(yaml.safe_load_all(content))
        docs = [d for d in docs if d is not None]
        # default + p1 + p2 = 3 documents
        assert len(docs) == 3
        names = [d["name"] for d in docs]
        assert "default" in names
        assert "p1" in names
        assert "p2" in names


class TestInvalidProfile:
    """Tests for invalid profile rejection."""

    def test_invalid_profile_rejected(self) -> None:
        """Pydantic validation error raised for invalid data."""
        with pytest.raises(ValidationError):
            EasyProfile(name="bad", model="/model.gguf", flash_attn="invalid")

    def test_missing_required_fields_rejected(self) -> None:
        """Missing required fields raises ValidationError."""
        with pytest.raises(ValidationError, match="name"):
            EasyProfile(model="/model.gguf")

        with pytest.raises(ValidationError, match="model"):
            EasyProfile(name="no-model")


class TestProfileCompleterEdgeCases:
    """Edge cases for ProfileCompleter."""

    def test_empty_profiles(self) -> None:
        """Completer with no profiles handles gracefully."""
        completer = ProfileCompleter([])
        assert completer.complete("") == []
        assert completer.get_next() == ""

    def test_case_sensitive_completion(self) -> None:
        """Completion is case-sensitive."""
        completer = ProfileCompleter(["Alpha", "beta"])
        assert completer.complete("A") == ["Alpha"]
        assert completer.complete("a") == []
