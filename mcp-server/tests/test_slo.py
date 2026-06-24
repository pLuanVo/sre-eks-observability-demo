"""Tests for SLO burn rate calculation logic."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_config(monkeypatch):
    monkeypatch.setenv("VM_URL", "http://vm-test:8429")


def _vm_response(value):
    """Build a fake VictoriaMetrics /api/v1/query response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [1719100000, str(value)]}],
        },
    }


def _empty_vm_response():
    return {"status": "success", "data": {"resultType": "vector", "result": []}}


class TestSloBurnRate:
    """Test the SLO burn rate calculation via the registered MCP tool."""

    @patch("tools.slo.requests.get")
    def test_burn_rate_ok(self, mock_get):
        """Low error rate -> burn rate < 1 -> status OK."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _vm_response(0.001)  # 0.1% error rate
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        # Access the registered tool function directly
        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "availability")

        assert "Status: OK" in result
        assert "payment-service" in result
        assert "99.9" in result  # ~99.9% availability
        mock_get.assert_called_once()

    @patch("tools.slo.requests.get")
    def test_burn_rate_critical(self, mock_get):
        """High error rate -> burn rate > 6 -> status CRITICAL."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _vm_response(0.05)  # 5% error rate
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "availability")

        assert "CRITICAL" in result
        # Burn rate = 0.05 / 0.005 = 10x
        assert "10.00x" in result

    @patch("tools.slo.requests.get")
    def test_burn_rate_warning(self, mock_get):
        """Moderate error rate -> 1 <= burn rate < 6 -> status WARNING."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _vm_response(0.01)  # 1% error rate
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "availability")

        assert "WARNING" in result
        # Burn rate = 0.01 / 0.005 = 2x
        assert "2.00x" in result

    @patch("tools.slo.requests.get")
    def test_no_data(self, mock_get):
        """Empty result set returns 'No data' message."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _empty_vm_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "availability")

        assert "No data" in result

    def test_unknown_slo_type(self):
        """Unknown SLO type returns an error message."""
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "invalid")

        assert "Unknown SLO type" in result

    @patch("tools.slo.requests.get")
    def test_latency_slo_type(self, mock_get):
        """Latency SLO type queries p99 histogram."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _vm_response(0.245)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "latency")

        assert "p99 latency" in result
        mock_get.assert_called_once()

    @patch("tools.slo.requests.get")
    def test_vm_connection_error(self, mock_get):
        """Network error returns graceful error message."""
        mock_get.side_effect = Exception("Connection refused")

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        from tools.slo import register
        register(mcp)

        tool_fn = mcp._tool_manager._tools["slo_burn_rate"].fn
        result = tool_fn("payment-service", "availability")

        assert "Error" in result
        assert "Connection refused" in result
