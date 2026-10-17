"""Architecture tests for Phase 3 analytics domain boundaries."""

import ast
from pathlib import Path

ANALYTICS_ROOT = Path(__file__).parents[1] / "app" / "analytics"
DOMAINS = {"overview", "products", "customers"}


def _imports(source: str, package: tuple[str, ...]) -> set[tuple[str, ...]]:
    """Return absolute app.analytics imports, including relative imports."""
    found: set[tuple[str, ...]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for name in node.names:
                parts = tuple(name.name.split("."))
                if parts[:2] == ("app", "analytics"):
                    found.add(parts[2:])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                target = package[: len(package) - node.level]
                if node.module:
                    target += tuple(node.module.split("."))
                found.add(target)
            elif node.module:
                parts = tuple(node.module.split("."))
                if parts[:2] == ("app", "analytics"):
                    found.add(parts[2:])
    return found


def _module_package(path: Path) -> tuple[str, ...]:
    relative = path.relative_to(ANALYTICS_ROOT).with_suffix("")
    return () if relative.name == "__init__" else relative.parts


def test_shared_modules_do_not_import_analytics_domains():
    for path in (ANALYTICS_ROOT / "shared").glob("*.py"):
        imports = _imports(path.read_text(), _module_package(path))
        assert not {item[0] for item in imports if item and item[0] in DOMAINS}, path


def test_domain_modules_do_not_import_another_domain():
    for domain in DOMAINS:
        for path in (ANALYTICS_ROOT / domain).glob("*.py"):
            imports = _imports(path.read_text(), _module_package(path))
            imported_domains = {item[0] for item in imports if item and item[0] in DOMAINS}
            assert imported_domains <= {domain}, path


def test_import_boundary_scanner_detects_absolute_and_relative_violations():
    absolute = _imports("from app.analytics.products import top_products", ("shared", "metrics"))
    relative = _imports("from ..products import top_products", ("overview", "trend"))

    assert absolute == {("products",)}
    assert relative == {("products",)}
