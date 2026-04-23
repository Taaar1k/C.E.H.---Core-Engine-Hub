# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (TASK-033: Config Expansion)

- **TASK-034**: `CleanChatDisplay` class for clean chat output with spinner, hideable tool calls and reasoning ([`src/c_e_h/ui/clean_display.py`](src/c_e_h/ui/clean_display.py))
- **TASK-035**: `scan_for_models()` function to auto-discover `.gguf` files with metadata ([`src/c_e_h/model_scanner.py`](src/c_e_h/model_scanner.py))
- **TASK-036**: `ProfileManager` class with full CRUD for Easy/Advanced configuration profiles ([`src/c_e_h/profile_manager.py`](src/c_e_h/profile_manager.py))
- **TASK-037**: `InteractiveLauncher` — 5-step guided flow for model selection, profile management, and agent launch ([`src/c_e_h/ui/launcher.py`](src/c_e_h/ui/launcher.py))
- `AgentConfig.models_directory` field — default scan directory for `.gguf` files
- `AgentConfig.default_profile` field — default profile name to load from `profiles.yaml`
- `DOCS/CONFIG/PROFILES.md` — profile format, Easy/Advanced parameter tables, examples, CLI flags
- `DOCS/UI/LAUNCHER.md` — interactive flow, keyboard shortcuts, non-TTY fallback behavior

### Changed (TASK-033: Config Expansion)

- `agent.md` parser (`Agent._parse_config`) now handles `models_directory` and `default_profile` fields
- `profiles.yaml` schema validated against Pydantic `EasyProfile` and `AdvancedProfile` models
- `profiles.yaml` created with `0600` permissions (owner read/write only)

### Added (Initial)

- Initial project scaffolding with C.E.H. (Core Engine Hub) framework
- Core agent engine with single-shot and multi-step task loops ([`src/c_e_h/agent.py`](src/c_e_h/agent.py))
- Three-tier memory system: persistent (agent.md), short-term (SQLite), long-term (FAISS vector store) ([`src/c_e_h/memory.py`](src/c_e_h/memory.py))
- Tool registry with Pydantic schema validation and sandboxed execution ([`src/c_e_h/tools.py`](src/c_e_h/tools.py))
- llama.cpp integration layer for GGUF model loading and inference ([`src/c_e_h/llama_backend.py`](src/c_e_h/llama_backend.py))
- CLI interface using Typer with commands: `run`, `interactive`, `doctor`, `config`, `model`, `session` ([`src/c_e_h/cli.py`](src/c_e_h/cli.py))
- Graceful degradation permission system (autonomous → approval mode after errors)
- Built-in tools: `read_file`, `write_file`, `execute_command`, `web_search`, `list_directory`, `create_directory`, `delete_file`, `import_module`
- Security layers: path validation, command pattern blocking, environment sanitization, module import whitelist
- GPU acceleration support: Metal (Apple Silicon), CUDA (NVIDIA), Vulkan (AMD)
- Context compaction strategies: `snip` (trim oldest) and `microcompact` (LLM summarize)
- Dependency policy document (<30 direct dependencies, no AI frameworks)
- Security policy document with threat model and incident response
- Project state tracking in `MEMORY/` directory
- CI/CD GitHub Actions workflow for cross-platform testing
- Hardware expectation guide for model selection

### Changed

- N/A (initial release)

### Deprecated

- N/A (initial release)

### Removed

- N/A (initial release)

### Fixed

- N/A (initial release)

### Security

- Implemented defense-in-depth security model with 4 layers
- Path traversal protection for all file operations
- Dangerous command pattern detection (`rm -rf`, `mkfs`, `dd if=`, etc.)
- Sandboxed subprocess execution (`shell=False`, 30s timeout)
- Module import whitelist (standard library + pydantic, rich only)
- Prompt injection protection via role separation and system prompt hardening

### Lessons Learned

**What worked:**
- Sequential scaling approach (single-agent first) keeps initial complexity manageable
- Minimal dependency strategy (<30 packages) reduces attack surface and maintenance burden
- Graceful degradation permission system provides good security without UX friction
- SQLite for state management enables atomic transactions and persistence

**What failed:**
- N/A (initial release, no production feedback yet)

**What to watch:**
- Context compaction needs real-world testing with long sessions
- Module import whitelist may need expansion as plugin system develops
- GPU backend detection should be tested on more hardware configurations
