"""Profile Manager — Save/Load configuration profiles for C.E.H.

Provides ``ProfileManager`` class with full CRUD operations for Easy and
Advanced configuration profiles stored in ``profiles.yaml`` (multi-document
YAML with ``---`` separators).

Easy mode profiles contain the 9 most-common llama.cpp parameters.
Advanced mode profiles contain the full llama.cpp flag set (120+ flags).

Usage
-----
>>> from c_e_h.profile_manager import ProfileManager
>>> pm = ProfileManager()
>>> pm.create("default", "easy", model="/path/to/model.gguf")
>>> profile = pm.read("default")
>>> pm.update("default", ctx_size=16384)
>>> pm.clone("default", "default-large")
>>> pm.delete("default-large")
>>> names = pm.list()
"""

from __future__ import annotations

import copy
import fcntl
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PROFILES_PATH = "profiles.yaml"
DEFAULT_PROFILE_NAME = "default"

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class EasyProfile(BaseModel):
    """Easy-mode profile with the 9 most-common llama.cpp parameters.

    Attributes:
        name: Unique profile name (required).
        model: Path to the GGUF model file (required).
        n_gpu_layers: Number of layers to offload to GPU. ``-1`` means all
            layers. Defaults to ``-1``.
        threads: Number of CPU threads. ``None`` means auto-detect CPU count.
            Defaults to ``None``.
        ctx_size: Context window size in tokens. Defaults to ``8192``.
        flash_attn: Flash attention mode. One of ``"on"``, ``"off"``,
            ``"auto"``. Defaults to ``"auto"``.
        cache_type_k: Key cache quantization type. Defaults to ``"q8_0"``.
        cache_type_v: Value cache quantization type. Defaults to ``"q8_0"``.
        n_cpu_moe_draft: Number of CPU threads for MoE draft. Defaults to
            ``0`` (disabled).
    """

    name: str = Field(..., description="Unique profile name")
    model: str = Field(..., description="Path to GGUF model file")
    n_gpu_layers: int = Field(-1, description="GPU layers (-1 = all)")
    threads: Optional[int] = Field(None, description="CPU threads (None = auto)")
    ctx_size: int = Field(8192, description="Context size in tokens")
    flash_attn: str = Field("auto", description="Flash attention mode")
    cache_type_k: str = Field("q8_0", description="Key cache type")
    cache_type_v: str = Field("q8_0", description="Value cache type")
    n_cpu_moe_draft: int = Field(0, description="MoE draft CPU threads")

    @field_validator("flash_attn")
    @classmethod
    def validate_flash_attn(cls, v: str) -> str:
        """Validate flash_attn is one of on/off/auto."""
        if v not in ("on", "off", "auto"):
            raise ValueError('flash_attn must be "on", "off", or "auto"')
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary for YAML serialization.

        Includes all fields with their default values so that profiles
        are fully serialised even when only a subset of fields was
        explicitly set.
        """
        return self.model_dump(exclude_unset=False, exclude_none=False)


class AdvancedProfile(EasyProfile):
    """Advanced-mode profile with full llama.cpp flag set (120+ flags).

    Extends ``EasyProfile`` with all additional llama.cpp parameters.
    All additional fields are optional — only non-default values need to be
    set.

    Model fields:
        lora: Path to LoRA adapter file.
        lora_scaled: LoRA scale factor.
        mmproj: Path to mmproj file (multimodal).
        embedding: Enable embedding mode.

    GPU fields:
        tensor_split: GPU tensor split sizes (comma-separated).
        main_gpu: Main GPU index (0 = primary).
        split_mode: Layer split mode (0 = layer, 1 = row).

    Threads fields:
        threads_batch: Thread count for batch processing.

    Batch fields:
        batch_size: Logical batch size.
        n_predict: Maximum tokens to predict.
        cont_batching: Enable continuous batching.
        parallel: Parallel sub-batch count.

    Context fields:
        mmap: Memory-map the model file.
        no_mmap: Disable memory-mapping.

    Sampling fields:
        temperature: Sampling temperature.
        top_k: Top-K sampling threshold.
        top_p: Top-P (nucleus) sampling threshold.
        min_p: Min-P sampling threshold.
        seed: Random seed (-1 = time-based).
        repeat_penalty: Repeat penalty factor.
        samplers: Comma-separated list of sampler names.

    Grammar fields:
        grammar: Grammar name (for grammar-based sampling).
        grammar_file: Path to grammar file.
        json_schema_file: Path to JSON schema file.
        chat_template_file: Path to chat template file.

    Advanced fields:
        mirostat: Enable mirostat sampling (0/1/2).
        dry_multiplier: DRY multiplier for context penalty.
        dry_base: DRY base value for context penalty.
        dry_allowed_range: DRY allowed range.
        xtc_temperature: XTC (eXclusion Top-C) temperature.
        xtc_threshold: XTC probability threshold.
        numa: NUMA mode (0/1/2/3).
        lookup_cache_static: Static KV-cache lookup.
        lookup_cache_dynamic: Dynamic KV-cache lookup.

    Server fields:
        server: Enable server mode.
        port: Server port number.
        host: Server host address.
        webui_config_file: Path to WebUI config file.
    """

    # Model
    lora: Optional[str] = Field(None, description="LoRA adapter path")
    lora_scaled: Optional[float] = Field(None, description="LoRA scale factor")
    mmproj: Optional[str] = Field(None, description="mmproj file path")
    embedding: Optional[bool] = Field(None, description="Enable embedding mode")

    # GPU
    tensor_split: Optional[str] = Field(None, description="GPU tensor split")
    main_gpu: Optional[int] = Field(None, description="Main GPU index")
    split_mode: Optional[int] = Field(None, description="Split mode (0=layer, 1=row)")

    # Threads
    threads_batch: Optional[int] = Field(None, description="Batch thread count")

    # Batch
    batch_size: Optional[int] = Field(None, description="Logical batch size")
    n_predict: Optional[int] = Field(None, description="Max prediction tokens")
    cont_batching: Optional[bool] = Field(None, description="Continuous batching")
    parallel: Optional[int] = Field(None, description="Parallel sub-batches")

    # Context
    mmap: Optional[bool] = Field(None, description="Memory-map model file")
    no_mmap: Optional[bool] = Field(None, description="Disable memory-mapping")

    # Sampling
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    top_k: Optional[int] = Field(None, description="Top-K threshold")
    top_p: Optional[float] = Field(None, description="Top-P threshold")
    min_p: Optional[float] = Field(None, description="Min-P threshold")
    seed: Optional[int] = Field(None, description="Random seed (-1=time)")
    repeat_penalty: Optional[float] = Field(None, description="Repeat penalty")
    samplers: Optional[str] = Field(None, description="Comma-separated samplers")

    # Grammar
    grammar: Optional[str] = Field(None, description="Grammar name")
    grammar_file: Optional[str] = Field(None, description="Grammar file path")
    json_schema_file: Optional[str] = Field(None, description="JSON schema path")
    chat_template_file: Optional[str] = Field(None, description="Chat template path")

    # Advanced
    mirostat: Optional[int] = Field(None, description="Mirostat mode (0/1/2)")
    dry_multiplier: Optional[float] = Field(None, description="DRY multiplier")
    dry_base: Optional[float] = Field(None, description="DRY base value")
    dry_allowed_range: Optional[int] = Field(None, description="DRY allowed range")
    xtc_temperature: Optional[float] = Field(None, description="XTC temperature")
    xtc_threshold: Optional[float] = Field(None, description="XTC threshold")
    numa: Optional[int] = Field(None, description="NUMA mode (0/1/2/3)")
    lookup_cache_static: Optional[int] = Field(None, description="Static KV lookup")
    lookup_cache_dynamic: Optional[int] = Field(None, description="Dynamic KV lookup")

    # Server
    server: Optional[bool] = Field(None, description="Enable server mode")
    port: Optional[int] = Field(None, description="Server port")
    host: Optional[str] = Field(None, description="Server host")
    webui_config_file: Optional[str] = Field(None, description="WebUI config path")

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary for YAML serialization."""
        return self.model_dump(exclude_unset=True, exclude_none=False)


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------


class ProfileManager:
    """Manage configuration profiles stored in a YAML file.

    Profiles are stored in ``profiles.yaml`` (multi-document YAML with
    ``---`` separators).  All file operations are thread-safe via ``fcntl``
    file locking on Unix.

    Args:
        profiles_path: Path to the YAML file. Defaults to ``profiles.yaml``
            in the current working directory.
    """

    def __init__(self, profiles_path: Optional[Path] = None) -> None:
        self.profiles_path = profiles_path or Path(DEFAULT_PROFILES_PATH)
        self._ensure_default()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_default(self) -> None:
        """Create a default profile if ``profiles.yaml`` doesn't exist."""
        if not self.profiles_path.exists():
            logger.info(
                "No profiles file found at %s — creating default profile.",
                self.profiles_path,
            )
            default = EasyProfile(
                name=DEFAULT_PROFILE_NAME,
                model="",
            )
            self._write_profiles([default.to_dict()])

    def _read_all_profiles(self) -> list[dict[str, Any]]:
        """Read all profiles from the YAML file.

        Returns:
            List of profile dictionaries.
        """
        if not self.profiles_path.exists():
            return []
        try:
            with open(self.profiles_path, "r", encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
            # Filter out None documents (empty documents between separators)
            return [d for d in docs if d is not None]
        except yaml.YAMLError as exc:
            logger.error("Error reading profiles file: %s", exc)
            return []

    def _write_profiles(self, profiles: list[dict[str, Any]]) -> None:
        """Write all profiles to the YAML file (multi-document format).

        Args:
            profiles: List of profile dictionaries to write.
        """
        # Ensure parent directory exists
        self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profiles_path, "w", encoding="utf-8") as f:
            yaml.dump_all(profiles, f, default_flow_style=False, sort_keys=False)

    def _acquire_lock(self) -> None:
        """Acquire an exclusive file lock for thread safety."""
        if not self.profiles_path.exists():
            return
        fd = open(self.profiles_path, "r")
        fcntl.flock(fd, fcntl.LOCK_EX)
        self._lock_fd = fd  # type: ignore[attr-defined]

    def _release_lock(self) -> None:
        """Release the file lock."""
        if hasattr(self, "_lock_fd"):
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)  # type: ignore[arg-type]
            self._lock_fd.close()  # type: ignore[arg-type]
            del self._lock_fd

    def _find_profile_index(self, profiles: list[dict[str, Any]], name: str) -> int:
        """Find the index of a profile by name.

        Args:
            profiles: List of profile dictionaries.
            name: Profile name to find.

        Returns:
            Index of the profile.

        Raises:
            ValueError: If profile not found.
        """
        for i, p in enumerate(profiles):
            if p.get("name") == name:
                return i
        raise ValueError(f"Profile '{name}' not found")

    # ------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------

    def create(self, name: str, mode: str = "easy", **params: Any) -> None:
        """Create a new profile.

        Args:
            name: Unique profile name.
            mode: Profile mode — ``"easy"`` or ``"advanced"``.
            **params: Profile parameters (validated against schema).

        Raises:
            ValueError: If profile name already exists or validation fails.
            ValidationError: If parameters don't match the schema.
        """
        # Merge name into params
        params["name"] = name

        # Validate against the appropriate schema
        if mode == "advanced":
            profile_data = AdvancedProfile(**params).to_dict()
        else:
            profile_data = EasyProfile(**params).to_dict()

        # Acquire lock for thread safety
        self._acquire_lock()
        try:
            profiles = self._read_all_profiles()

            # Check for duplicate name
            for p in profiles:
                if p.get("name") == name:
                    raise ValueError(f"Profile '{name}' already exists")

            profiles.append(profile_data)
            self._write_profiles(profiles)
            logger.info("Created profile '%s' (mode=%s).", name, mode)
        finally:
            self._release_lock()

    def read(self, name: str) -> dict[str, Any]:
        """Load a profile by name.

        Args:
            name: Profile name to load.

        Returns:
            Profile dictionary.

        Raises:
            ValueError: If profile not found.
        """
        self._acquire_lock()
        try:
            profiles = self._read_all_profiles()
            idx = self._find_profile_index(profiles, name)
            return profiles[idx]
        finally:
            self._release_lock()

    def update(self, name: str, **params: Any) -> None:
        """Update an existing profile's fields in-place.

        Args:
            name: Profile name to update.
            **params: Fields to update.

        Raises:
            ValueError: If profile not found.
            ValidationError: If updated parameters don't match the schema.
        """
        self._acquire_lock()
        try:
            profiles = self._read_all_profiles()
            idx = self._find_profile_index(profiles, name)
            profile_data = profiles[idx]

            # Validate against the existing profile's schema
            # Determine mode by checking for advanced fields
            is_advanced = any(
                k in params
                for k in [
                    "lora", "lora_scaled", "mmproj", "embedding",
                    "tensor_split", "main_gpu", "split_mode",
                    "threads_batch", "batch_size", "n_predict",
                    "cont_batching", "parallel", "mmap", "no_mmap",
                    "temperature", "top_k", "top_p", "min_p", "seed",
                    "repeat_penalty", "samplers", "grammar", "grammar_file",
                    "json_schema_file", "chat_template_file", "mirostat",
                    "dry_multiplier", "dry_base", "dry_allowed_range",
                    "xtc_temperature", "xtc_threshold", "numa",
                    "lookup_cache_static", "lookup_cache_dynamic",
                    "server", "port", "host", "webui_config_file",
                ]
            )

            if is_advanced:
                # Merge existing + new params, validate as AdvancedProfile
                merged = {**profile_data, **params}
                validated = AdvancedProfile(**merged).to_dict()
            else:
                # Merge existing + new params, validate as EasyProfile
                merged = {**profile_data, **params}
                validated = EasyProfile(**merged).to_dict()

            profiles[idx] = validated
            self._write_profiles(profiles)
            logger.info("Updated profile '%s'.", name)
        finally:
            self._release_lock()

    def delete(self, name: str) -> None:
        """Remove a profile from the YAML file.

        Args:
            name: Profile name to delete.

        Raises:
            ValueError: If profile not found.
        """
        self._acquire_lock()
        try:
            profiles = self._read_all_profiles()
            idx = self._find_profile_index(profiles, name)
            profiles.pop(idx)
            self._write_profiles(profiles)
            logger.info("Deleted profile '%s'.", name)
        finally:
            self._release_lock()

    def list(self) -> list[str]:
        """Return a list of all profile names.

        Returns:
            List of profile name strings.
        """
        profiles = self._read_all_profiles()
        return [p.get("name", "") for p in profiles if p.get("name")]

    def clone(self, source_name: str, new_name: str) -> None:
        """Copy a profile with a new name.

        Args:
            source_name: Name of the profile to clone.
            new_name: Name for the cloned profile.

        Raises:
            ValueError: If source not found or new name already exists.
        """
        self._acquire_lock()
        try:
            profiles = self._read_all_profiles()

            # Find source profile
            source_idx = self._find_profile_index(profiles, source_name)
            source_data = profiles[source_idx]

            # Check for duplicate new name
            for p in profiles:
                if p.get("name") == new_name:
                    raise ValueError(f"Profile '{new_name}' already exists")

            # Clone with new name
            cloned = copy.deepcopy(source_data)
            cloned["name"] = new_name
            profiles.append(cloned)
            self._write_profiles(profiles)
            logger.info("Cloned profile '%s' to '%s'.", source_name, new_name)
        finally:
            self._release_lock()

    # ------------------------------------------------------------------
    # TAB Completion helper (AC-5)
    # ------------------------------------------------------------------

    def get_completer(self) -> "ProfileCompleter":
        """Return a Rich completer for profile name TAB completion.

        Returns:
            ``ProfileCompleter`` instance with current profile names.
        """
        names = self.list()
        return ProfileCompleter(names)


class ProfileCompleter:
    """Rich completer for profile name TAB completion.

    Supports arrow key navigation and TAB-triggered completion of partial
    profile names.

    Args:
        profiles: List of profile name strings.
    """

    def __init__(self, profiles: list[str]) -> None:
        self.profiles = profiles
        self._current_index = 0

    def complete(self, partial: str) -> list[str]:
        """Return matching profile names for the given partial string.

        Args:
            partial: Partial profile name typed by the user.

        Returns:
            List of matching profile names.
        """
        if not partial:
            return self.profiles
        return [p for p in self.profiles if p.startswith(partial)]

    def get_next(self) -> str:
        """Get the next profile name for arrow key navigation.

        Returns:
            Next profile name in the list.
        """
        if not self.profiles:
            return ""
        name = self.profiles[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.profiles)
        return name

    def reset(self) -> None:
        """Reset the navigation index."""
        self._current_index = 0
