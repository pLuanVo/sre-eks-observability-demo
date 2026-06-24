"""Runbook reader tool."""

import os
import config


def register(mcp):
    @mcp.tool()
    def read_runbook(name: str = "", list_all: bool = False) -> str:
        """Read an SRE runbook or list all available runbooks.

        Args:
            name: Runbook name without .md extension (e.g. 'high-error-rate')
            list_all: If True, list all available runbooks
        """
        runbook_dir = config.RUNBOOK_DIR

        if list_all or not name:
            try:
                files = [f.replace(".md", "") for f in os.listdir(runbook_dir) if f.endswith(".md")]
                if not files:
                    return "No runbooks found."
                return "Available runbooks:\n" + "\n".join(f"  - {f}" for f in sorted(files))
            except Exception as e:
                return f"Error listing runbooks: {e}"

        path = os.path.join(runbook_dir, f"{name}.md")
        try:
            with open(path) as f:
                return f.read()
        except FileNotFoundError:
            return f"Runbook '{name}' not found. Use list_all=True to see available runbooks."
