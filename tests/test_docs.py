"""The documentation keeps its structure (docs/documentation.md): links
resolve, every layer documents itself, a module doc names its files."""
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "fantasy_nhl"
# dependencies, builds, caches and generated output
SKIPPED = {".git", ".venv", "venv", ".idea", ".pytest_cache", "__pycache__",
           "node_modules", "dist", "golden", "plots"}
SOURCES = {".py", ".ts", ".tsx"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _entries(folder: Path) -> list[Path]:
    return [path for path in sorted(folder.iterdir())
            if path.name not in SKIPPED
            and not path.name.endswith(".egg-info")]


def _files(folder: Path) -> Iterator[Path]:
    for path in _entries(folder):
        if path.is_dir():
            yield from _files(path)
        else:
            yield path


def _is_source(path: Path) -> bool:
    return path.suffix in SOURCES and path.name != "__init__.py"


def _module_doc(folder: Path) -> Path:
    return folder / f"{folder.name}.md"


def _name(path: Path) -> str:
    return str(path.relative_to(ROOT))


DOCS = [path for path in _files(ROOT) if path.suffix == ".md"]
MODULE_DOCS = [doc for doc in DOCS if doc == _module_doc(doc.parent)]
LAYERS = [path for path in _entries(PACKAGE)
          if (path / "__init__.py").is_file()] + [ROOT / "web",
                                                  ROOT / "tests"]


def _text_lines(doc: Path) -> list[str]:
    """The lines of a document outside its fenced code blocks."""
    lines, fenced = [], False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            lines.append(line)
    return lines


def _anchors(doc: Path) -> set[str]:
    """The anchors GitHub gives the headings of a document."""
    anchors = set()
    for line in _text_lines(doc):
        heading = re.match(r"#+\s+(.+)", line)
        if heading:
            text = re.sub(r"[`*]", "", heading.group(1).strip().lower())
            anchors.add(re.sub(r"[^\w\- ]", "", text).replace(" ", "-"))
    return anchors


@pytest.mark.parametrize("doc", DOCS, ids=_name)
def test_links_resolve(doc):
    broken = []
    for line in _text_lines(doc):
        # a link shown as inline code is an example, not a link
        for target in LINK.findall(re.sub(r"`[^`]*`", "", line)):
            if re.match(r"[a-z][a-z0-9+.-]*:", target):
                continue  # another site
            path, _, anchor = target.partition("#")
            linked = doc.parent / path if path else doc
            if not linked.exists() or (anchor and linked.suffix == ".md"
                                       and anchor not in _anchors(linked)):
                broken.append(target)
    assert not broken, f"{_name(doc)} links to nothing: {broken}"


@pytest.mark.parametrize("layer", LAYERS, ids=_name)
def test_every_layer_documents_itself(layer):
    """In <folder>/<folder>.md; a package that only groups other packages
    is covered by theirs."""
    if _module_doc(layer).is_file():
        return
    own = [path for path in _entries(layer) if _is_source(path)]
    parts = [path for path in _entries(layer)
             if (path / "__init__.py").is_file()]
    assert not own and parts and all(
        _module_doc(part).is_file() for part in parts), (
        f"{_name(layer)} needs a {layer.name}.md")


def _covered(folder: Path) -> Iterator[Path]:
    """The source files a module doc covers: those of its folder and of
    the subfolders without a doc of their own."""
    for path in _entries(folder):
        if path.is_dir():
            if not _module_doc(path).is_file():
                yield from _covered(path)
        elif _is_source(path):
            yield path


@pytest.mark.parametrize("doc", MODULE_DOCS, ids=_name)
def test_module_doc_names_its_files(doc):
    text = doc.read_text(encoding="utf-8")
    missing = [str(path.relative_to(doc.parent))
               for path in _covered(doc.parent) if path.name not in text]
    assert not missing, f"{_name(doc)} does not mention {missing}"


def test_the_checks_have_something_to_check():
    assert len(MODULE_DOCS) >= 7 and len(DOCS) > len(MODULE_DOCS)
