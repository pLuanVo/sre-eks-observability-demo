"""Tests for runbook listing and reading."""

import textwrap

import pytest


@pytest.fixture
def runbook_dir(tmp_path, monkeypatch):
    """Create a temp directory with sample runbooks and point config at it."""
    runbooks = {
        "high-error-rate.md": textwrap.dedent("""\
            # High Error Rate Runbook

            AUTO-REMEDIATION: ELIGIBLE

            ## Steps
            1. Check error logs
            2. Rollback if needed
        """),
        "high-latency.md": textwrap.dedent("""\
            # High Latency Runbook

            ## Steps
            1. Check resource usage
            2. Scale if needed
        """),
        "deployment-failure.md": textwrap.dedent("""\
            # Deployment Failure Runbook

            AUTO-REMEDIATION: ELIGIBLE

            ## Steps
            1. Check rollout status
            2. Auto-rollback
        """),
    }
    for name, content in runbooks.items():
        (tmp_path / name).write_text(content)

    monkeypatch.setattr("config.RUNBOOK_DIR", str(tmp_path))
    return tmp_path


class TestReadRunbook:
    """Test runbook read and list via the registered MCP tool."""

    def test_list_all(self, runbook_dir):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="", list_all=True)

        assert "Available runbooks:" in result
        assert "high-error-rate" in result
        assert "high-latency" in result
        assert "deployment-failure" in result

    def test_list_default_no_name(self, runbook_dir):
        """Calling with no name and list_all=False still lists (fallback)."""
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="", list_all=False)

        assert "Available runbooks:" in result

    def test_read_specific_runbook(self, runbook_dir):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="high-error-rate")

        assert "High Error Rate Runbook" in result
        assert "AUTO-REMEDIATION: ELIGIBLE" in result

    def test_read_nonexistent_runbook(self, runbook_dir):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="does-not-exist")

        assert "not found" in result

    def test_list_sorted_alphabetically(self, runbook_dir):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="", list_all=True)

        lines = [l.strip() for l in result.strip().split("\n") if l.strip().startswith("- ")]
        names = [l.lstrip("- ") for l in lines]
        assert names == sorted(names)

    def test_list_empty_directory(self, tmp_path, monkeypatch):
        """Empty runbook directory returns 'No runbooks found'."""
        monkeypatch.setattr("config.RUNBOOK_DIR", str(tmp_path))

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="", list_all=True)

        assert "No runbooks found" in result

    def test_list_nonexistent_directory(self, monkeypatch):
        """Nonexistent runbook directory returns an error message."""
        monkeypatch.setattr("config.RUNBOOK_DIR", "/nonexistent/path")

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn
        result = tool_fn(name="", list_all=True)

        assert "Error listing runbooks" in result

    def test_runbook_content_has_auto_remediation(self, runbook_dir):
        """Verify we can detect AUTO-REMEDIATION marker in runbook content."""
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.runbook import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["read_runbook"].fn

        eligible = tool_fn(name="high-error-rate")
        assert "AUTO-REMEDIATION: ELIGIBLE" in eligible

        not_eligible = tool_fn(name="high-latency")
        assert "AUTO-REMEDIATION: ELIGIBLE" not in not_eligible
