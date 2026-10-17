"""Architecture tests for Phase 3 analytics domain boundaries."""

import ast
from pathlib import Path

import pytest

ANALYTICS_ROOT = Path(__file__).parents[1] / "app" / "analytics"
DOMAINS = {"overview", "products", "customers"}


def _imports(source: str, package: tuple[str, ...]) -> set[tuple[str, ...]]:
    """Return absolute analytics imports, resolving both absolute and relative forms."""
    found: set[tuple[str, ...]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for name in node.names:
                parts = tuple(name.name.split("."))
                if parts[:2] == ("app", "analytics"):
                    found.add(parts[2:])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                target = package[: len(package) - (node.level - 1)]
                if node.module:
                    target += tuple(node.module.split("."))
                if node.module:
                    found.add(target)
                else:
                    found.update(target + (name.name,) for name in node.names if name.name != "*")
            elif node.module:
                parts = tuple(node.module.split("."))
                if parts[:2] == ("app", "analytics"):
                    target = parts[2:]
                    if target:
                        found.add(target)
                    else:
                        found.update((name.name,) for name in node.names if name.name != "*")
    return found


def _package(path: Path) -> tuple[str, ...]:
    relative = path.relative_to(ANALYTICS_ROOT).with_suffix("")
    return relative.parts[:-1] if relative.name != "__init__" else relative.parts


def _boundary_violations(source: str, package: tuple[str, ...]) -> set[str]:
    source_domain = package[0] if package else None
    violations: set[str] = set()
    for imported in _imports(source, package):
        target_domain = imported[0] if imported else None
        if source_domain == "shared" and target_domain in DOMAINS:
            violations.add(f"shared imports domain {target_domain}")
        elif source_domain in DOMAINS and target_domain in DOMAINS - {source_domain}:
            violations.add(f"{source_domain} imports domain {target_domain}")
    return violations


def test_every_analytics_python_file_obeys_the_dependency_direction():
    for path in ANALYTICS_ROOT.rglob("*.py"):
        assert not _boundary_violations(path.read_text(), _package(path)), path


@pytest.mark.parametrize(
    ("source", "package", "message"),
    [
        (
            "from app.analytics.products import top_products",
            ("overview",),
            "overview imports domain products",
        ),
        ("from ..products import top_products", ("overview",), "overview imports domain products"),
        ("from ..overview import kpis", ("shared",), "shared imports domain overview"),
    ],
)
def test_boundary_scanner_rejects_hand_written_violations(source, package, message):
    assert _boundary_violations(source, package) == {message}


def test_boundary_scanner_allows_domain_importing_shared_with_absolute_and_relative_imports():
    assert not _boundary_violations("from app.analytics.shared import periods", ("overview",))
    assert not _boundary_violations("from ..shared import periods", ("overview",))
