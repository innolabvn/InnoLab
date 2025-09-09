from __future__ import annotations

import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

for p in (SRC_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import argparse
import json
import os
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
    parser.add_argument("--insert_rag", action="store_true", help="Use RAG (validate default dataset and enable RAG path)")
    parser.add_argument("--project", type=str, default="projects/demo_project", help="Path to project directory to scan")
    parser.add_argument("--scanners", type=str, default="bearer", help="Comma-separated scanners to use (default: bearer)")
    parser.add_argument("--fixers", type=str, default="llm", help="Comma-separated fixers to apply (default: llm)")
    parser.add_argument("--iterations", type=int, default=5, help="Max iterations (default: 5)")
    args = parser.parse_args()

    # Load .env từ repo root
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(repo_root, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    dify_key = os.getenv("DIFY_CLOUD_API_KEY")  # có thể để trống: AnalysisService sẽ báo lỗi mềm

    cfg = ExecutionConfig(
        max_iterations=int(os.getenv("MAX_ITERATIONS", str(args.iterations))),
        project_key=os.getenv("PROJECT_KEY", "my-service"),
        scan_directory=args.project,
        scan_modes=_parse_list(args.scanners, ["bearer"]),
        fix_modes=_parse_list(args.fixers, ["llm"]),
        dify_cloud_api_key=dify_key,
    )

    print(f"Fixers: {','.join(cfg.fix_modes)}")
    print(f"Project directory: {cfg.scan_directory}")
    print("-" * 60)

    use_rag = bool(args.insert_rag)

    try:
        svc = ExecutionServiceNoMongo(cfg)

        if use_rag:
            # Không bắt buộc; chỉ validate file dataset
            svc.insert_rag_default()

        result = svc.run(use_rag=use_rag)

        print("\n" + "=" * 50)
        print("📊 EXECUTION RESULTS")
        print("=" * 50)
        print(f"Project: {result.get('project_key')}")
        print(f"Total bugs fixed: {result.get('total_bugs_fixed')}")
        print(f"Total iterations: {len(result.get('iterations', []))}")
        print(f"Duration: {result.get('duration_seconds'):.2f} seconds")

        for i, iteration in enumerate(result.get("iterations", []), 1):
            print(f"\n  Iteration {i}:")
            print(f"    🐞 Bugs found: {iteration.get('bugs_found')}")
            print(f"        + Type Bug: {iteration.get('bugs_type_bug')}")
            bugs_ignored = iteration.get("bugs_type_code_smell", 0)
            print(f"        + Type Code-smell: {bugs_ignored}")

            ar = iteration.get("analysis_result", {})
            print(f"🔧 Bugs to fix: {ar.get('bugs_to_fix', 0)}")

            rescan_found = iteration.get("rescan_bugs_found", 0)
            rescan_bug_type = iteration.get("rescan_bugs_type_bug", 0)
            rescan_code_smell = iteration.get("rescan_bugs_type_code_smell", 0)
            print(f"🔄 Bugs after rescan: {rescan_found} ({rescan_bug_type} BUG, {rescan_code_smell} CODE_SMELL)")
            print(f"🚫 Bugs Ignored: {bugs_ignored}")

            # in token nếu có (tuỳ fixer)
            fix_results = iteration.get("fix_results", [])
            fix_result = fix_results[-1] if fix_results else iteration.get("fix_result", {})
            if fix_result.get("total_tokens", 0) > 0:
                print("💰 Token Usage:")
                print(f"        + Input tokens: {fix_result.get('total_input_tokens', 0):,}")
                print(f"        + Output tokens: {fix_result.get('total_output_tokens', 0):,}")
                print(f"        + Total tokens: {fix_result.get('total_tokens', 0):,}")
                print(f"        + Average similarity: {fix_result.get('average_similarity', 0):.3f}")
                print(f"        + Threshold met: {fix_result.get('threshold_met_count', 0)}")

            if fix_result.get("message"):
                print(f"    Message: {fix_result.get('message')}")

        print(f"\nStart time: {result.get('start_time')}")
        print(f"End time: {result.get('end_time')}")

        # JSON cuối để machines parse
        print("\nEND_EXECUTION_RESULT_JSON")
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        logger.exception("Demo failed")


if __name__ == "__main__":
    main()
