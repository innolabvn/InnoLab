from __future__ import annotations

import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

for p in (SRC_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import argparse
import json
from typing import List

from dotenv import load_dotenv
from src.app.services.log_service import logger
from src.app.services.execution.service import ExecutionConfig, ExecutionServiceNoMongo


def _parse_list(arg: str, default: List[str]) -> List[str]:
    if not arg:
        return default
    return [x.strip().lower() for x in arg.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="ExecutionService Demo - Bug fixing with Dify AI")
    parser.add_argument("--project", type=str, default="", help="Path to project directory to scan")
    args = parser.parse_args()

    # Load .env từ repo root
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(repo_root, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    dify_key = os.getenv("DIFY_CLOUD_API_KEY")

    cfg = ExecutionConfig(
        max_iterations=int(os.getenv("MAX_ITERATIONS", 5)),
        scan_directory=args.project,
        scan_modes=['bearer'],
        dify_cloud_api_key=dify_key,
    )

    logger.info(f"Project directory: {cfg.scan_directory}")

    try:
        svc = ExecutionServiceNoMongo(cfg)
        result = svc.run()

        logger.info("=" * 16)
        logger.info("EXECUTION RESULT")
        logger.info("=" * 16)
        logger.info(f"Total iterations: {len(result.get('iterations', []))}")
        logger.info(f"Total file fixed: {result.get('total_file_fixed')}")
        logger.info(f"Total duration: {result.get('duration_seconds'):.2f} seconds")

        for i, iteration in enumerate(result.get("iterations", []), 1):
            logger.info(f"Iteration {i}:")
            logger.info(f"Bugs found: {iteration.get('bugs_found')}")

            analysis_result = iteration.get("analysis_result", {})
            logger.info(f"Bugs to fix: {analysis_result.get('bugs_to_fix', 0)}")
            logger.info(f"Bugs after rescan: {iteration.get('rescan_bugs_found', 0)}")
            
            # fix_results from llm.py
            fix_results = iteration.get("fix_results", [])
            fix_result = fix_results[-1] if fix_results else iteration.get("fix_result", {})
            if fix_result.get("total_tokens", 0) > 0:
                logger.info("Token Usage:")
                logger.info(f"Input tokens: {fix_result.get('total_input_tokens', 0):,}")
                logger.info(f"Output tokens: {fix_result.get('total_output_tokens', 0):,}")
                logger.info(f"Total tokens: {fix_result.get('total_tokens', 0):,}")
                logger.info(f"Average similarity: {fix_result.get('average_similarity', 0):.3f}")
                logger.info(f"Threshold met: {fix_result.get('threshold_met_count', 0)}")

            if fix_result.get("message"):
                logger.info(f"Message: {fix_result.get('message')}")

        logger.info(f"Start time: {result.get('start_time')}")
        logger.info(f"End time: {result.get('end_time')}")

        # JSON cuối để machines parse
        logger.info("END_EXECUTION_RESULT_JSON")
        logger.debug(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        logger.info(f"Error during execution: {e}")
        logger.exception("Demo failed")


if __name__ == "__main__":
    main()
