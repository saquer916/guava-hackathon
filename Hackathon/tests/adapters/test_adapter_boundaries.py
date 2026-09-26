"""Provider SDKs and wire formats stay inside clinical_triage.adapters."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[2] / "src" / "clinical_triage"
FORBIDDEN_OUTSIDE_ADAPTERS = (
    "guava",
    "httpx",
    "clinical_triage.adapters.openemr",
    "clinical_triage.adapters.guava",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_core_packages_do_not_import_provider_code() -> None:
    violations = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        if relative.parts[0] == "adapters":
            continue
        for name in _imports(path):
            if any(
                name == root or name.startswith(f"{root}.") for root in FORBIDDEN_OUTSIDE_ADAPTERS
            ):
                violations.append(f"{relative}: {name}")
    assert violations == []


def test_openemr_adapter_does_not_import_voice_provider() -> None:
    for path in (PACKAGE / "adapters" / "openemr").rglob("*.py"):
        assert not any(name.split(".")[0] == "guava" for name in _imports(path)), path
