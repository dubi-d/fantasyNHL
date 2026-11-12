"""Import rules between the layers: analysis <- sources, views <- cli."""
import ast
from pathlib import Path

import pytest

import fantasy_nhl

ROOT = Path(fantasy_nhl.__file__).parent
SOURCES = {"espn_data", "sources"}
TERMINAL = {"rich", "questionary", "prompt_toolkit"}
# layer -> what its modules must not import (package parts or libraries)
FORBIDDEN = {
    "analysis": SOURCES | TERMINAL | {"views", "cli", "plots", "espn_api",
                                      "matplotlib"},
    "espn_data": TERMINAL | {"views", "cli", "plots", "matplotlib"},
    "sources": TERMINAL | {"views", "cli", "plots", "matplotlib"},
    "views": SOURCES | TERMINAL | {"cli", "plots", "espn_api", "matplotlib"},
    "plots": SOURCES | TERMINAL | {"views", "cli", "espn_api"},
}


def _is_type_checking(node: ast.AST) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING")


def _runtime_imports(path: Path) -> set[str]:
    """What a module imports when it runs: the first part of every library
    and, for imports within the package, the part after the package."""
    package = path.relative_to(ROOT).parts[:-1]
    found = set()
    pending = [ast.parse(path.read_text())]
    while pending:
        node = pending.pop()
        if _is_type_checking(node):
            continue
        pending.extend(ast.iter_child_nodes(node))
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = ["fantasy_nhl", *package[:len(package) - node.level + 1]
                    ] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            names = ([module] if node.module or not node.level
                     else [f"{module}.{alias.name}" for alias in node.names])
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] != "fantasy_nhl":
                found.add(parts[0])
            elif len(parts) > 1:
                found.add(parts[1])
    return found


def _layer(path: Path) -> str:
    return path.relative_to(ROOT).parts[0].removesuffix(".py")


@pytest.mark.parametrize(
    "path", [p for p in sorted(ROOT.rglob("*.py")) if _layer(p) in FORBIDDEN],
    ids=lambda p: str(p.relative_to(ROOT)))
def test_layer_imports(path):
    crossed = _runtime_imports(path) & FORBIDDEN[_layer(path)]
    assert not crossed, f"{path.name} must not import {sorted(crossed)}"
