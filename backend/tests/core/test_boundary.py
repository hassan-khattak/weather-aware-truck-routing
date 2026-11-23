"""The domain core stays pure: no web framework, database or network client (plan.md 12.3)."""

import ast
from pathlib import Path

import pytest

CORE_DIR = Path(__file__).resolve().parents[2] / "core"
FORBIDDEN = {"django", "rest_framework", "httpx", "requests", "psycopg", "urllib3", "aiohttp"}


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


CORE_MODULES = sorted(CORE_DIR.glob("*.py"))


def test_there_are_core_modules_to_check() -> None:
    assert len(CORE_MODULES) >= 9


@pytest.mark.parametrize("module", CORE_MODULES, ids=lambda p: p.name)
def test_core_module_has_no_framework_or_network_imports(module: Path) -> None:
    assert imported_roots(module) & FORBIDDEN == set()
