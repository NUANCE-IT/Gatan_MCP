"""
conftest.py — shared pytest fixtures for the GMS-MCP test suite.

Sets GMS_SIMULATE=1 before any import so the DMSimulator activates
automatically, and exposes session-scoped fixtures for the simulator
and server module.
"""

import os
import sys
from pathlib import Path

# Force simulation mode before importing any gms_mcp module
os.environ["GMS_SIMULATE"] = "1"

# Ensure src/ is on sys.path when running tests from the repo root
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


@pytest.fixture(scope="session")
def dm():
    """Shared DMSimulator instance for the entire test session."""
    from gms_mcp.simulator import DMSimulator
    return DMSimulator()


@pytest.fixture(scope="session")
def server():
    """
    GMS-MCP server module imported in simulation mode.
    Returns the module so tests can call tool functions directly.
    """
    import gms_mcp.server as srv
    return srv


@pytest.fixture(scope="session")
def ollama_model():
    """Ollama model name, read from environment (default: qwen2.5:7b)."""
    return os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


@pytest.fixture(scope="session")
def ollama_base_url():
    """Ollama server URL."""
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
