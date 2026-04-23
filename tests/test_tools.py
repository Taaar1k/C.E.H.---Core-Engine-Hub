"""Tests for the C.E.H. Tools module.

Covers:
  - ToolRegistry: register(), get(), list(), enable/disable
  - PermissionManager: autonomous/approval modes, error tracking, mode switching
  - Pydantic-based tool schema validation
  - Sandboxed subprocess execution (shell=False, restricted env)
  - Built-in tools: read_file, write_file, execute_command, web_search
  - ToolExecutor: end-to-end execution with validation and permission checks
  - MCPAdapter: register, list, call, sync_to_registry
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from c_e_h.tools import (
    ExecuteCommandSchema,
    MCPAdapter,
    MCPToolCall,
    PermissionManager,
    PermissionState,
    ReadFileSchema,
    ToolExecutor,
    ToolRegistry,
    WebSearchSchema,
    WriteFileSchema,
    _build_restricted_env,
    execute_command,
    read_file,
    registry,
    sandbox_execute,
    validate_tool_input,
    web_search,
    write_file,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def fresh_registry():
    """Return a fresh ToolRegistry (not the global one)."""
    return ToolRegistry()


@pytest.fixture()
def fresh_permission_manager():
    """Return a PermissionManager with default settings."""
    return PermissionManager()


@pytest.fixture()
def temp_file(tmp_path: Path):
    """Create a temporary file with known content."""
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    return f


@pytest.fixture()
def temp_dir(tmp_path: Path):
    """Return a temporary directory path."""
    return tmp_path


# ===========================================================================
# ToolRegistry Tests
# ===========================================================================


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_decorator(self, fresh_registry):
        """Test that register decorator stores tool."""

        @fresh_registry.register(name="test_tool", description="A test tool")
        def my_tool(x: int) -> int:
            return x * 2

        tool = fresh_registry.get("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert callable(tool.func)

    def test_register_with_schema(self, fresh_registry):
        """Test registration with Pydantic schema."""

        @fresh_registry.register(
            name="schema_tool",
            description="Tool with schema",
            input_schema=ReadFileSchema,
        )
        def schema_tool_func(**kwargs):
            return ""

        tool = fresh_registry.get("schema_tool")
        assert tool is not None
        assert tool.input_schema == ReadFileSchema

    def test_get_returns_none_for_unknown(self, fresh_registry):
        """Test that get returns None for unknown tool."""
        assert fresh_registry.get("nonexistent") is None

    def test_list_tools(self, fresh_registry):
        """Test list_tools returns enabled tool names."""
        @fresh_registry.register(name="tool_a")
        def func_a():
            pass

        @fresh_registry.register(name="tool_b")
        def func_b():
            pass

        @fresh_registry.register(name="tool_c")
        def func_c():
            pass

        fresh_registry.disable_tool("tool_b")
        names = fresh_registry.list_tools()

        assert "tool_a" in names
        assert "tool_c" in names
        assert "tool_b" not in names

    def test_list_all_tools(self, fresh_registry):
        """Test list_all_tools returns all tool names including disabled."""
        @fresh_registry.register(name="tool_a")
        def func_a():
            pass

        @fresh_registry.register(name="tool_b")
        def func_b():
            pass

        fresh_registry.disable_tool("tool_b")

        all_names = fresh_registry.list_all_tools()
        assert "tool_a" in all_names
        assert "tool_b" in all_names

    def test_enable_disable(self, fresh_registry):
        """Test enable and disable methods."""
        @fresh_registry.register(name="toggle_tool")
        def toggle_func():
            pass

        assert fresh_registry.get("toggle_tool").enabled is True
        fresh_registry.disable_tool("toggle_tool")
        assert fresh_registry.get("toggle_tool").enabled is False
        fresh_registry.enable_tool("toggle_tool")
        assert fresh_registry.get("toggle_tool").enabled is True

    def test_disable_unknown_returns_false(self, fresh_registry):
        """Test disabling unknown tool returns False."""
        assert fresh_registry.disable_tool("unknown") is False

    def test_enable_unknown_returns_false(self, fresh_registry):
        """Test enabling unknown tool returns False."""
        assert fresh_registry.enable_tool("unknown") is False


# ===========================================================================
# PermissionManager Tests
# ===========================================================================


class TestPermissionManager:
    """Tests for PermissionManager class."""

    def test_initial_state_autonomous(self):
        """Test initial state is autonomous."""
        pm = PermissionManager()
        assert pm.state == PermissionState.AUTONOMOUS
        assert pm.is_autonomous is True
        assert pm.error_count == 0
        assert pm.success_count == 0

    def test_initial_state_approval(self):
        """Test initial state can be approval."""
        pm = PermissionManager(initial_state=PermissionState.APPROVAL)
        assert pm.state == PermissionState.APPROVAL
        assert pm.is_autonomous is False

    def test_requires_approval(self, fresh_permission_manager):
        """Test requires_approval returns correct value."""
        assert fresh_permission_manager.requires_approval() is False

        fresh_permission_manager._state = PermissionState.APPROVAL
        assert fresh_permission_manager.requires_approval() is True

    def test_record_success_in_autonomous(self, fresh_permission_manager):
        """Test recording success in autonomous mode."""
        fresh_permission_manager.record_success()
        assert fresh_permission_manager.success_count == 1
        assert fresh_permission_manager.error_count == 0
        assert fresh_permission_manager.state == PermissionState.AUTONOMOUS

    def test_record_error_in_autonomous(self, fresh_permission_manager):
        """Test recording error in autonomous mode does NOT switch yet."""
        fresh_permission_manager.record_error()
        assert fresh_permission_manager.error_count == 1
        assert fresh_permission_manager.state == PermissionState.AUTONOMOUS

    def test_mode_switch_autonomous_to_approval(self):
        """Test mode switches from autonomous to approval after threshold."""
        pm = PermissionManager(max_auto_errors=3)
        assert pm.state == PermissionState.AUTONOMOUS

        pm.record_error()
        assert pm.state == PermissionState.AUTONOMOUS
        assert pm.error_count == 1

        pm.record_error()
        assert pm.state == PermissionState.AUTONOMOUS
        assert pm.error_count == 2

        pm.record_error()
        assert pm.state == PermissionState.APPROVAL
        assert pm.error_count == 3

    def test_mode_switch_approval_to_autonomous(self):
        """Test mode switches from approval to autonomous after success_reset."""
        pm = PermissionManager(
            initial_state=PermissionState.APPROVAL,
            success_reset=3,
        )
        assert pm.state == PermissionState.APPROVAL

        pm.record_success()
        assert pm.state == PermissionState.APPROVAL
        assert pm.success_count == 1

        pm.record_success()
        assert pm.state == PermissionState.APPROVAL
        assert pm.success_count == 2

        pm.record_success()
        assert pm.state == PermissionState.AUTONOMOUS
        assert pm.success_count == 0

    def test_error_resets_success_counter(self):
        """Test that error resets the success counter."""
        pm = PermissionManager(
            initial_state=PermissionState.APPROVAL,
            success_reset=3,
        )

        pm.record_success()
        pm.record_success()
        assert pm.success_count == 2

        pm.record_error()
        assert pm.success_count == 0
        assert pm.error_count == 1

    def test_success_resets_error_counter(self):
        """Test that success resets the error counter."""
        pm = PermissionManager(max_auto_errors=5)

        pm.record_error()
        pm.record_error()
        assert pm.error_count == 2

        pm.record_success()
        assert pm.error_count == 0

    def test_request_approval(self, fresh_permission_manager):
        """Test request_approval logs and returns True."""
        result = fresh_permission_manager.request_approval("test_tool", {"x": 1})
        assert result is True

    def test_reset(self):
        """Test reset returns to autonomous with zeroed counters."""
        pm = PermissionManager(initial_state=PermissionState.APPROVAL)
        pm._error_count = 5
        pm._success_count = 3

        pm.reset()

        assert pm.state == PermissionState.AUTONOMOUS
        assert pm.error_count == 0
        assert pm.success_count == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        pm = PermissionManager(max_auto_errors=5, success_reset=10)
        pm.record_error()
        pm.record_error()

        data = pm.to_dict()
        assert data["state"] == "autonomous"
        assert data["error_count"] == 2
        assert data["success_count"] == 0
        assert data["max_auto_errors"] == 5
        assert data["success_reset"] == 10

    def test_from_dict(self):
        """Test restoration from dictionary."""
        data = {
            "state": "approval",
            "error_count": 2,
            "success_count": 1,
            "max_auto_errors": 4,
            "success_reset": 8,
        }
        pm = PermissionManager.from_dict(data)

        assert pm.state == PermissionState.APPROVAL
        assert pm.error_count == 2
        assert pm.success_count == 1
        assert pm.max_auto_errors == 4
        assert pm.success_reset == 8

    def test_custom_thresholds(self):
        """Test custom max_auto_errors and success_reset values."""
        pm = PermissionManager(
            max_auto_errors=2,
            success_reset=2,
            initial_state=PermissionState.AUTONOMOUS,
        )

        pm.record_error()
        pm.record_error()
        assert pm.state == PermissionState.APPROVAL

        pm.record_success()
        pm.record_success()
        assert pm.state == PermissionState.AUTONOMOUS


# ===========================================================================
# Tool Schema Validation Tests
# ===========================================================================


class TestToolValidation:
    """Tests for Pydantic-based tool schema validation."""

    def test_valid_read_file_args(self):
        """Test valid read_file arguments pass validation."""
        args = {"path": "/tmp/test.txt", "max_lines": 50}
        result = validate_tool_input(ReadFileSchema, args)
        assert result["path"] == "/tmp/test.txt"
        assert result["max_lines"] == 50

    def test_valid_write_file_args(self):
        """Test valid write_file arguments pass validation."""
        args = {"path": "/tmp/test.txt", "content": "hello", "append": True}
        result = validate_tool_input(WriteFileSchema, args)
        assert result["path"] == "/tmp/test.txt"
        assert result["content"] == "hello"
        assert result["append"] is True

    def test_valid_execute_command_args(self):
        """Test valid execute_command arguments pass validation."""
        args = {"command": "ls -la", "timeout": 10}
        result = validate_tool_input(ExecuteCommandSchema, args)
        assert result["command"] == "ls -la"
        assert result["timeout"] == 10

    def test_valid_web_search_args(self):
        """Test valid web_search arguments pass validation."""
        args = {"query": "test query", "max_results": 3}
        result = validate_tool_input(WebSearchSchema, args)
        assert result["query"] == "test query"
        assert result["max_results"] == 3

    def test_missing_required_field_raises(self):
        """Test missing required field raises ValueError."""
        args = {"max_lines": 50}  # missing 'path'
        with pytest.raises(ValueError, match="Tool validation failed"):
            validate_tool_input(ReadFileSchema, args)

    def test_invalid_type_raises(self):
        """Test invalid type raises ValueError."""
        args = {"path": "", "max_lines": 50}  # empty path
        with pytest.raises(ValueError, match="Tool validation failed"):
            validate_tool_input(ReadFileSchema, args)

    def test_max_lines_too_low_raises(self):
        """Test max_lines below minimum raises ValueError."""
        args = {"path": "/tmp/test.txt", "max_lines": 0}
        with pytest.raises(ValueError, match="Tool validation failed"):
            validate_tool_input(ReadFileSchema, args)

    def test_default_values_applied(self):
        """Test that default values are applied correctly."""
        args = {"path": "/tmp/test.txt"}
        result = validate_tool_input(ReadFileSchema, args)
        assert result["max_lines"] == 100

    def test_append_defaults_to_false(self):
        """Test append defaults to False."""
        args = {"path": "/tmp/test.txt", "content": "hello"}
        result = validate_tool_input(WriteFileSchema, args)
        assert result["append"] is False


# ===========================================================================
# Sandboxed Execution Tests
# ===========================================================================


class TestSandboxExecution:
    """Tests for sandboxed subprocess execution."""

    def test_execute_simple_command(self):
        """Test executing a simple command."""
        result = sandbox_execute(["echo", "hello"])
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]
        assert result["timed_out"] is False

    def test_execute_string_command(self):
        """Test executing a string command (parsed by shlex)."""
        result = sandbox_execute("echo test")
        assert result["returncode"] == 0
        assert "test" in result["stdout"]

    def test_execute_command_with_stderr(self):
        """Test command that produces stderr."""
        result = sandbox_execute(["bash", "-c", "echo error >&2; exit 1"])
        assert result["returncode"] == 1
        assert "error" in result["stderr"]

    def test_execute_command_timeout(self):
        """Test command timeout."""
        result = sandbox_execute(["sleep", "10"], timeout=1)
        assert result["timed_out"] is True
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"]

    def test_execute_command_not_found(self):
        """Test command not found."""
        result = sandbox_execute(["nonexistent_command_xyz"])
        assert result["returncode"] == 127
        assert "not found" in result["stderr"]

    def test_restricted_env(self):
        """Test that restricted environment excludes dangerous vars."""
        env = _build_restricted_env()
        assert "PYTHONPATH" not in env
        assert "LD_PRELOAD" not in env
        assert "LD_LIBRARY_PATH" not in env

    def test_restricted_env_allows_safe_vars(self):
        """Test that safe environment variables are preserved."""
        env = _build_restricted_env()
        assert "PATH" in env
        assert "HOME" in env

    def test_dangerous_command_blocked(self):
        """Test that dangerous commands are blocked."""
        result = sandbox_execute(["rm", "-rf", "/"])
        assert result["returncode"] == 1
        assert "blocked" in result["stderr"].lower() or "blocked" in result["stderr"]

    def test_shell_false_enforced(self):
        """Test that shell=False is enforced (no shell injection)."""
        # This should NOT execute the echo part; it should fail
        result = sandbox_execute(["echo", "; rm -rf /"])
        # The semicolon should be treated as part of the argument, not a shell operator
        assert "; rm -rf /" in result["stdout"] or result["returncode"] != 0

    def test_work_dir(self, temp_dir):
        """Test executing command in specific working directory."""
        result = sandbox_execute(["pwd"], work_dir=str(temp_dir))
        assert result["returncode"] == 0
        assert str(temp_dir) in result["stdout"]

    def test_invalid_command_string(self):
        """Test invalid shlex parsing."""
        result = sandbox_execute("unclosed 'quote")
        assert result["returncode"] == 1
        assert "parse error" in result["stderr"]


# ===========================================================================
# Built-in Tool Tests
# ===========================================================================


class TestBuiltInTools:
    """Tests for built-in tools: read_file, write_file, execute_command, web_search."""

    def test_read_file_success(self, temp_file):
        """Test reading a file successfully."""
        content = read_file(path=str(temp_file), max_lines=10)
        assert "line1" in content
        assert "line5" in content

    def test_read_file_truncation(self, temp_file):
        """Test that read_file truncates at max_lines."""
        content = read_file(path=str(temp_file), max_lines=2)
        assert "line1" in content
        assert "line2" in content
        assert "truncated" in content

    def test_read_file_not_found(self):
        """Test read_file raises FileNotFoundError for missing file."""
        # Use a path within /tmp so it passes the path check but doesn't exist
        with pytest.raises(FileNotFoundError):
            read_file(path="/tmp/this_file_does_not_exist_xyz.txt")

    def test_read_file_permission_error(self, tmp_path):
        """Test read_file handles permission errors."""
        f = tmp_path / "noperm.txt"
        f.write_text("secret")
        f.chmod(0o000)
        try:
            with pytest.raises((PermissionError, ValueError)):
                read_file(path=str(f))
        finally:
            f.chmod(0o644)  # Restore for cleanup

    def test_write_file_new(self, temp_dir):
        """Test writing to a new file."""
        result = write_file(
            path=str(temp_dir / "new.txt"),
            content="hello world",
        )
        assert "Successfully wrote" in result
        assert (temp_dir / "new.txt").exists()
        assert (temp_dir / "new.txt").read_text() == "hello world"

    def test_write_file_overwrite(self, temp_file):
        """Test writing overwrites existing file."""
        write_file(path=str(temp_file), content="new content")
        content = temp_file.read_text()
        assert content == "new content"
        assert "line1" not in content

    def test_write_file_append(self, temp_file):
        """Test appending to existing file."""
        write_file(path=str(temp_file), content="\nline6", append=True)
        content = temp_file.read_text()
        assert "line5" in content
        assert "line6" in content

    def test_write_file_creates_dirs(self, temp_dir):
        """Test write_file creates parent directories."""
        result = write_file(
            path=str(temp_dir / "sub" / "dir" / "file.txt"),
            content="deep",
        )
        assert "Successfully wrote" in result
        assert (temp_dir / "sub" / "dir" / "file.txt").exists()

    def test_execute_command_success(self):
        """Test execute_command returns formatted output."""
        result = execute_command("echo hello")
        assert "Return code: 0" in result
        assert "hello" in result

    def test_execute_command_failure(self):
        """Test execute_command handles failures."""
        # Use 'grep' with a pattern that won't match (returns exit code 1)
        result = execute_command("grep -q 'zzznonexistent' /dev/null")
        assert "Return code:" in result

    def test_execute_command_timeout(self):
        """Test execute_command with timeout."""
        # Use 'find' with a deep directory search that will timeout
        result = execute_command("find / -name 'xxxx' 2>/dev/null", timeout=1)
        assert "TIMEOUT" in result or "Return code:" in result

    def test_web_search_not_configured(self):
        """Test web_search returns 'not configured'."""
        result = web_search(query="test query")
        assert "not configured" in result.lower()
        assert "network" in result.lower()

    def test_web_search_max_results(self):
        """Test web_search respects max_results parameter."""
        result = web_search(query="test", max_results=10)
        assert "not configured" in result.lower()

    def test_read_file_path_traversal_parent(self, tmp_path):
        """Test read_file rejects path traversal via parent directories."""
        from c_e_h.security import PathTraversalError
        with pytest.raises(PathTraversalError):
            read_file(path="/etc/passwd")

    def test_read_file_path_traversal_absolute(self, tmp_path):
        """Test read_file rejects absolute paths outside workspace."""
        from c_e_h.security import PathTraversalError
        with pytest.raises(PathTraversalError):
            read_file(path="/root/.ssh/id_rsa")

    def test_write_file_path_traversal_parent(self, tmp_path):
        """Test write_file rejects path traversal via parent directories."""
        from c_e_h.security import PathTraversalError
        with pytest.raises(PathTraversalError):
            write_file(path="/etc/evil.txt", content="malicious")

    def test_write_file_path_traversal_absolute(self, tmp_path):
        """Test write_file rejects absolute paths outside workspace."""
        from c_e_h.security import PathTraversalError
        with pytest.raises(PathTraversalError):
            write_file(path="/root/.ssh/evil.txt", content="malicious")

    def test_read_file_valid_relative_path(self, tmp_path):
        """Test read_file accepts valid relative paths within workspace."""
        test_file = tmp_path / "valid.txt"
        test_file.write_text("valid content")
        # Change to tmp_path so relative paths resolve within workspace
        old_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            content = read_file(path="valid.txt")
            assert "valid content" in content
        finally:
            os.chdir(old_cwd)


# ===========================================================================
# ToolExecutor Tests
# ===========================================================================


class TestToolExecutor:
    """Tests for ToolExecutor class."""

    def test_execute_success(self, fresh_registry, fresh_permission_manager):
        """Test successful tool execution."""
        _executor = ToolExecutor(
            tool_registry=fresh_registry,
            permission_manager=fresh_permission_manager,
        )

        # Use a simpler approach: register with no schema validation
        fresh_registry2 = ToolRegistry()
        pm2 = PermissionManager()
        executor2 = ToolExecutor(tool_registry=fresh_registry2, permission_manager=pm2)

        @fresh_registry2.register(name="add", description="Add two numbers")
        def add_tool(a: int, b: int) -> int:
            return a + b

        result = executor2.execute("add", {"a": 3, "b": 4})
        assert result["success"] is True
        assert "7" in result["output"]

    def test_execute_tool_not_found(self, fresh_registry, fresh_permission_manager):
        """Test execution of non-existent tool."""
        executor = ToolExecutor(
            tool_registry=fresh_registry,
            permission_manager=fresh_permission_manager,
        )
        result = executor.execute("nonexistent", {})
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_execute_tool_disabled(self, fresh_registry, fresh_permission_manager):
        """Test execution of disabled tool."""
        @fresh_registry.register(name="disabled_tool")
        def disabled_func():
            return "should not run"

        fresh_registry.disable_tool("disabled_tool")

        executor = ToolExecutor(
            tool_registry=fresh_registry,
            permission_manager=fresh_permission_manager,
        )
        result = executor.execute("disabled_tool", {})
        assert result["success"] is False
        assert "disabled" in result["error"]

    def test_execute_validation_error_records_error(
        self, fresh_registry, fresh_permission_manager
    ):
        """Test that validation error records an error in permission manager."""
        @fresh_registry.register(
            name="validated_tool",
            input_schema=ReadFileSchema,
        )
        def validated_tool_func(**kwargs):
            return ""

        executor = ToolExecutor(
            tool_registry=fresh_registry,
            permission_manager=fresh_permission_manager,
        )

        # Missing required 'path' field
        result = executor.execute("validated_tool", {"max_lines": 10})
        assert result["success"] is False
        assert fresh_permission_manager.error_count == 1

    def test_execute_success_records_success(
        self, fresh_registry, fresh_permission_manager
    ):
        """Test that successful execution records success."""
        fresh_registry2 = ToolRegistry()
        pm2 = PermissionManager()
        executor2 = ToolExecutor(tool_registry=fresh_registry2, permission_manager=pm2)

        @fresh_registry2.register(name="success_tool")
        def success_func():
            return "ok"

        result = executor2.execute("success_tool", {})
        assert result["success"] is True
        assert pm2.success_count == 1

    def test_execute_approval_mode_denied(
        self, fresh_registry, fresh_permission_manager
    ):
        """Test execution denied in approval mode when user denies."""
        fresh_permission_manager._state = PermissionState.APPROVAL

        # Mock request_approval to return False
        fresh_permission_manager.request_approval = MagicMock(return_value=False)

        executor = ToolExecutor(
            tool_registry=fresh_registry,
            permission_manager=fresh_permission_manager,
        )

        result = executor.execute("any_tool", {})
        assert result["success"] is False
        assert "denied" in result["output"].lower()


# ===========================================================================
# MCP Adapter Tests
# ===========================================================================


class TestMCPAdapter:
    """Tests for MCPAdapter class."""

    def test_register_mcp_tool(self, fresh_registry):
        """Test registering an MCP tool."""
        adapter = MCPAdapter(tool_registry=fresh_registry)

        def my_handler(x: int) -> int:
            return x + 1

        adapter.register_mcp_tool(
            name="increment",
            description="Increment a number",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=my_handler,
        )

        tools = adapter.list_mcp_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "increment"

    def test_call_mcp_tool(self, fresh_registry):
        """Test calling an MCP tool."""
        adapter = MCPAdapter(tool_registry=fresh_registry)

        def add_handler(a: int, b: int) -> int:
            return a + b

        adapter.register_mcp_tool(
            name="add",
            description="Add two numbers",
            input_schema={"type": "object"},
            handler=add_handler,
        )

        call = MCPToolCall(id="1", name="add", arguments={"a": 2, "b": 3})
        result = adapter.call_mcp_tool(call)

        assert result["id"] == "1"
        assert result["error"] is None
        assert "5" in result["content"][0]["text"]

    def test_call_unknown_mcp_tool(self, fresh_registry):
        """Test calling an unknown MCP tool."""
        adapter = MCPAdapter(tool_registry=fresh_registry)
        call = MCPToolCall(id="2", name="unknown_tool", arguments={})
        result = adapter.call_mcp_tool(call)

        assert result["id"] == "2"
        assert "Unknown" in result["error"]

    def test_list_mcp_tools_empty(self, fresh_registry):
        """Test listing MCP tools when none registered."""
        adapter = MCPAdapter(tool_registry=fresh_registry)
        assert adapter.list_mcp_tools() == []

    def test_sync_to_registry(self, fresh_registry):
        """Test syncing MCP tools to registry."""
        adapter = MCPAdapter(tool_registry=fresh_registry)

        def handler():
            return "synced"

        adapter.register_mcp_tool(
            name="synced_tool",
            description="A synced tool",
            input_schema={},
            handler=handler,
        )

        count = adapter.sync_to_registry()
        assert count == 1
        assert fresh_registry.get("synced_tool") is not None

    def test_sync_duplicate_not_added(self, fresh_registry):
        """Test that duplicate tools are not re-added."""
        @fresh_registry.register(name="existing_tool")
        def existing_func():
            return "existing"

        adapter = MCPAdapter(tool_registry=fresh_registry)
        adapter.register_mcp_tool(
            name="existing_tool",
            description="Same name",
            input_schema={},
            handler=existing_func,
        )

        count = adapter.sync_to_registry()
        assert count == 0  # Should not add duplicate


# ===========================================================================
# Global Registry Tests
# ===========================================================================


class TestGlobalRegistry:
    """Tests for the global registry instance."""

    def test_global_registry_has_builtins(self):
        """Test that global registry contains built-in tools."""
        assert "read_file" in registry.list_all_tools()
        assert "write_file" in registry.list_all_tools()
        assert "execute_command" in registry.list_all_tools()
        assert "web_search" in registry.list_all_tools()

    def test_global_registry_tools_enabled(self):
        """Test that built-in tools are enabled by default."""
        assert registry.get("read_file").enabled is True
        assert registry.get("write_file").enabled is True
        assert registry.get("execute_command").enabled is True
        assert registry.get("web_search").enabled is True
