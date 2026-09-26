import ast
from pathlib import Path

import pytest

from clinical_triage.domain.voice import TransferResult


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


def test_failed_transfer_requires_a_machine_readable_failure_code() -> None:
    with pytest.raises(ValueError, match="must be opposites"):
        TransferResult(transfer_id="transfer-1", accepted=False)
    with pytest.raises(ValueError, match="must be opposites"):
        TransferResult(transfer_id="transfer-1", accepted=False, failure_code="")
