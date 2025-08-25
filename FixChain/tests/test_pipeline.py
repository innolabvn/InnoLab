import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from run.run_demo import ExecutionServiceNoMongo
from modules.scan.sonar import SonarQScanner
from modules.scan.bearer import BearerScanner


@pytest.fixture
def sonar_bugs():
    path = Path(__file__).parent / "fixtures" / "sonar_bugs.json"
    return json.loads(path.read_text())


@pytest.fixture
def bearer_bugs():
    path = Path(__file__).parent / "fixtures" / "bearer_bugs.json"
    return json.loads(path.read_text())


def test_pipeline_combines_scanners(monkeypatch, sonar_bugs, bearer_bugs):
    # Mock scanner outputs: first call returns bugs, second call (rescan) returns empty
    sonar_mock = MagicMock(side_effect=[sonar_bugs, []])
    bearer_mock = MagicMock(side_effect=[bearer_bugs, []])
    monkeypatch.setattr(SonarQScanner, "scan", sonar_mock)
    monkeypatch.setattr(BearerScanner, "scan", bearer_mock)

    service = ExecutionServiceNoMongo(scan_mode=["sonarq", "bearer"])
    service.max_iterations = 1  # ensure single iteration

    # Analysis service returns bugs as-is
    monkeypatch.setattr(
        service.analysis_service,
        "analyze_bugs_with_dify",
        lambda bugs, use_rag=False, mode=None: {"list_bugs": bugs, "bugs_to_fix": len(bugs)},
    )

    fixer_mock = MagicMock(return_value={"success": True, "fixed_count": len(sonar_bugs) + len(bearer_bugs)})
    service.fixer.fix_bugs = fixer_mock

    result = service.run_execution()

    # Ensure fixer received combined bugs from both scanners
    fixer_mock.assert_called_once()
    passed_bugs = fixer_mock.call_args[0][0]
    assert passed_bugs == sonar_bugs + bearer_bugs
    assert result["iterations"][0]["bugs_found"] == len(sonar_bugs) + len(bearer_bugs)
