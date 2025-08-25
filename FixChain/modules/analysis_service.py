from __future__ import annotations
import json
from typing import Dict, List

from utils.logger import logger
from lib.dify_lib import DifyMode, run_workflow_with_dify


class AnalysisService:
    """Service for analyzing bugs and interacting with Dify"""

    def __init__(self, dify_cloud_api_key: str | None = None, dify_local_api_key: str | None = None):
        self.dify_cloud_api_key = dify_cloud_api_key
        self.dify_local_api_key = dify_local_api_key

    def count_bug_types(self, bugs: List[Dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {"BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        for bug in bugs:
            bug_type = bug.get("type", "UNKNOWN")
            if bug_type in counts:
                counts[bug_type] += 1
            else:
                counts[bug_type] = counts.get(bug_type, 0) + 1
        counts["TOTAL"] = len(bugs)
        return counts

    def analyze_bugs_with_dify(self, bugs: List[Dict], use_rag: bool = False, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        list_bugs = []
        bugs_to_fix = 0
        try:
            api_key = self.dify_cloud_api_key if mode == DifyMode.CLOUD else self.dify_local_api_key
            if not api_key:
                logger.error(f"No API key found for mode: {mode}")
                return {"success": False, "error": "Missing API key", "list_bugs": list_bugs, "bugs_to_fix": bugs_to_fix}
            inputs = {
                "is_use_rag": str(use_rag),
                "report": json.dumps(bugs, ensure_ascii=False),
            }
            logger.info(f"Need to fix {len(bugs)} bugs using Dify")
            response = run_workflow_with_dify(
                api_key=api_key,
                inputs=inputs,
                user="hieult",
                response_mode="blocking",
                mode=mode,
            )
            outputs = response.get("data", {}).get("outputs", {})
            list_bugs = outputs.get("list_bugs", "")
            logger.info(
                f"DIFY: list_bugs type: {type(list_bugs)}, content: {list_bugs}"
            )
            bugs_to_fix = (
                int(list_bugs.get("bugs_to_fix", "0"))
                if isinstance(list_bugs, dict)
                else 0
            )
            logger.info(
                f"DIFY: Initial bugs_to_fix from response: {bugs_to_fix}"
            )
            if bugs_to_fix == 0 and isinstance(list_bugs, dict) and "bugs" in list_bugs:
                bugs_array = list_bugs.get("bugs", [])
                if isinstance(bugs_array, list):
                    fix_count = sum(
                        1
                        for bug in bugs_array
                        if isinstance(bug, dict)
                        and "action" in bug
                        and "FIX" in str(bug.get("action", "")).upper()
                    )
                    logger.info(
                        f"DIFY: Counted {fix_count} bugs with 'FIX' action from list of {len(bugs_array)} bugs"
                    )
                    bugs_to_fix = fix_count
            elif bugs_to_fix == 0 and isinstance(list_bugs, list):
                fix_count = sum(
                    1
                    for bug in list_bugs
                    if isinstance(bug, dict)
                    and "action" in bug
                    and "FIX" in str(bug.get("action", "")).upper()
                )
                logger.info(
                    f"DIFY: Counted {fix_count} bugs with 'FIX' action from list of {len(list_bugs)} bugs"
                )
                bugs_to_fix = fix_count
            if bugs_to_fix == 0:
                return {
                    "success": True,
                    "bugs_to_fix": bugs_to_fix,
                    "list_bugs": list_bugs,
                    "message": "No bugs to fix",
                }
            return {
                "success": True,
                "list_bugs": list_bugs,
                "bugs_to_fix": bugs_to_fix,
                "message": f"Need to fix {bugs_to_fix} bugs",
            }
        except Exception as e:
            logger.error(f"DIFY:Error in analysis_bugs_with_dify: {str(e)}")
            return {
                "list_bugs": list_bugs,
                "success": False,
                "bugs_to_fix": bugs_to_fix,
                "error": str(e),
            }
