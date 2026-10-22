import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

from app.analytics.shared.metrics import METRICS
from app.main import app

ROOT = Path(__file__).parents[2]

SYNC_REVISION = "045796b0c7bbdd21520ccce1c7972495aab929f8"
SYNC_DATE = "2026-10-22"
LOCALES = ("tr-TR", "de-DE", "ru-RU", "es-ES", "zh-CN", "ja-JP")
SOURCES = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("deploy/README.md"),
    Path("_docs/architecture.md"),
    Path("_docs/metrics.md"),
)
LINK_PATTERN = re.compile(r"\[[^]]+\]\(([^)]+)\)")
FENCED_BLOCK_PATTERN = re.compile(r"^```[^\n]*\n.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")


def localized_path(source: Path, locale: str) -> Path:
    return source.with_name(f"{source.stem}.{locale}{source.suffix}")


def documentation_matrix() -> list[Path]:
    return [
        path
        for source in SOURCES
        for path in (source, *(localized_path(source, locale) for locale in LOCALES))
    ]


def markdown_anchors(markdown: str) -> set[str]:
    """Return the GitHub-style heading anchors used by these documentation files."""
    anchors: set[str] = set()
    duplicates: Counter[str] = Counter()
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"<[^>]+>", "", match.group(1)).lower()
        heading = re.sub(r"[^\w\- ]", "", heading)
        base = re.sub(r" +", "-", heading).strip("-")
        occurrence = duplicates[base]
        duplicates[base] += 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


def test_metric_catalogue_covers_the_authoritative_registry() -> None:
    catalogue = (ROOT / "_docs" / "metrics.md").read_text(encoding="utf-8")
    for key in METRICS:
        assert f"`{key}`" in catalogue


def test_architecture_endpoint_table_matches_openapi() -> None:
    architecture = (ROOT / "_docs" / "architecture.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`(/api/[^`]+)`", architecture))
    assert documented == set(app.openapi()["paths"])


def test_documentation_relative_links_resolve() -> None:
    for relative_document in documentation_matrix():
        document = ROOT / relative_document
        markdown = document.read_text(encoding="utf-8")
        for target in LINK_PATTERN.findall(markdown):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            relative, _, fragment = target.partition("#")
            linked_document = document.parent / relative if relative else document
            assert linked_document.exists(), f"{relative_document}: {target}"
            if fragment and linked_document.suffix == ".md":
                linked_markdown = linked_document.read_text(encoding="utf-8")
                assert unquote(fragment) in markdown_anchors(linked_markdown), (
                    f"{relative_document}: {target}"
                )


def test_localized_document_matrix_and_language_navigation_are_complete() -> None:
    for source in SOURCES:
        expected_targets = [
            source.name,
            *(localized_path(source, locale).name for locale in LOCALES),
        ]
        for document in (source, *(localized_path(source, locale) for locale in LOCALES)):
            markdown = (ROOT / document).read_text(encoding="utf-8")
            opening = "\n".join(markdown.splitlines()[:8])
            for target in expected_targets:
                assert f"]({target})" in opening, f"{document}: missing {target} navigation"


def test_localized_documents_name_the_english_source_and_sync_revision() -> None:
    for source in SOURCES:
        for locale in LOCALES:
            document = localized_path(source, locale)
            opening = "\n".join((ROOT / document).read_text(encoding="utf-8").splitlines()[:12])
            notice = next((line for line in opening.splitlines() if line.startswith(">")), "")
            assert f"]({source.name})" in notice, f"{document}: English source notice"
            assert SYNC_REVISION in notice, f"{document}: sync revision"
            assert SYNC_DATE in notice, f"{document}: sync date"


def test_localized_documents_preserve_structure_and_technical_literals() -> None:
    for source in SOURCES:
        source_markdown = (ROOT / source).read_text(encoding="utf-8")
        source_headings = [
            len(match.group(1))
            for line in source_markdown.splitlines()
            if (match := re.match(r"^(#{1,6})\s+", line))
        ]
        source_tables = [
            line.count("|") for line in source_markdown.splitlines() if line.startswith("|")
        ]
        source_blocks = FENCED_BLOCK_PATTERN.findall(source_markdown)
        without_blocks = FENCED_BLOCK_PATTERN.sub("", source_markdown)
        source_literals = Counter(INLINE_CODE_PATTERN.findall(without_blocks))

        for locale in LOCALES:
            document = localized_path(source, locale)
            translated = (ROOT / document).read_text(encoding="utf-8")
            translated_headings = [
                len(match.group(1))
                for line in translated.splitlines()
                if (match := re.match(r"^(#{1,6})\s+", line))
            ]
            translated_tables = [
                line.count("|") for line in translated.splitlines() if line.startswith("|")
            ]
            assert translated_headings == source_headings, f"{document}: heading structure"
            assert translated_tables == source_tables, f"{document}: table structure"
            assert FENCED_BLOCK_PATTERN.findall(translated) == source_blocks, (
                f"{document}: fenced code differs from English"
            )

            translated_without_blocks = FENCED_BLOCK_PATTERN.sub("", translated)
            translated_literals = Counter(INLINE_CODE_PATTERN.findall(translated_without_blocks))
            missing_literals = source_literals - translated_literals
            assert not missing_literals, (
                f"{document}: altered technical literals {missing_literals}"
            )
