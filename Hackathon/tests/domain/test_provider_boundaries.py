import ast
from pathlib import Path


def test_domain_modules_do_not_import_provider_sdks() -> None:
    domain_root = Path(__file__).parents[2] / "src" / "clinical_triage" / "domain"
    forbidden_roots = {"guava", "httpx"}

    violations: list[str] = []
    for path in domain_root.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            if any(name.split(".", maxsplit=1)[0] in forbidden_roots for name in imported):
                violations.append(f"{path.name}:{getattr(node, 'lineno', 0)}")

    assert violations == []
