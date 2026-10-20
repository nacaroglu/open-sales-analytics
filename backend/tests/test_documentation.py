import re
from pathlib import Path

from app.analytics.shared.metrics import METRICS
from app.main import app

ROOT = Path(__file__).parents[2]


def test_metric_catalogue_covers_the_authoritative_registry() -> None:
    catalogue = (ROOT / "_docs" / "metrics.md").read_text(encoding="utf-8")
    for key in METRICS:
        assert f"`{key}`" in catalogue


def test_architecture_endpoint_table_matches_openapi() -> None:
    architecture = (ROOT / "_docs" / "architecture.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`(/api/[^`]+)`", architecture))
    assert documented == set(app.openapi()["paths"])


def test_documentation_relative_links_resolve() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "_docs" / "architecture.md",
        ROOT / "_docs" / "metrics.md",
    ]
    pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for document in documents:
        for target in pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if relative:
                assert (document.parent / relative).exists(), f"{document}: {target}"
