import pytest

from agent_core.tools import build_default_registry, calculator
from agent_core.tools.registry import ToolRegistry


def test_calculator_allows_arithmetic_only():
    assert calculator("2 + 3 * 4") == "2 + 3 * 4 = 14"
    with pytest.raises(ValueError):
        calculator("__import__('os').system('bad')")


def test_registry_isolates_bad_calls():
    assert "Không có tool" in ToolRegistry([]).run("missing", {})


def test_default_tools_do_not_expose_arbitrary_pdf_paths():
    assert "read_pdf" not in [tool.name for tool in build_default_registry().specs()]
