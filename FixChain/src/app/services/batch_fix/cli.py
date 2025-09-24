# src/app/services/batch_fix/cli.py
from __future__ import annotations
from collections import defaultdict
import argparse, json, os
from pathlib import Path
from dotenv import load_dotenv
from src.app.services.log_service import logger
from src.app.services.batch_fix.processor import SecureFixProcessor

def load_issues_group_by_file(path):
    issues_by_file = defaultdict(list)

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    logger.debug(f"Fixer received data: {str(data)[:100]}")
    for d in data:
        fn = d.get("file_name")
        key = os.path.normpath(fn) if fn else "UNKNOWN"
        issues_by_file[key].append(d)

    return issues_by_file

def run():
    parser = argparse.ArgumentParser(description="Secure Batch Fix (AI-powered)")
    parser.add_argument("destination", type=str, nargs="?", help="Directory to scan/fix")
    parser.add_argument("--issues-file", type=str)
    parser.add_argument('--enable-serena', action='store_true')
    parser.add_argument('--serena-mcp', action='store_true')
    args = parser.parse_args()

    root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
    load_dotenv(root_env)

    directory = args.destination
    if not directory or not os.path.isdir(directory):
        logger.error(f"Invalid directory: {directory}"); return

    issues_by_file = {}
    if args.issues_file and os.path.exists(args.issues_file):
        try:
            issues_by_file = load_issues_group_by_file(args.issues_file)
            logger.debug(f"Loaded issues from {args.issues_file}, total files with issues: {issues_by_file}")
        except Exception as e:
            logger.warning("Cannot load issues file: %s", e)

    processor = SecureFixProcessor(directory)
    processor.load_ignore_patterns(directory)

    # collect files
    code_ext = (".py",".js",".ts",".jsx",".java",".cpp",".c",".html",".css",".txt")
    code_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not processor.should_ignore_file(os.path.join(root,d), directory)]
        for f in files:
            p = os.path.join(root, f)
            if processor.should_ignore_file(p, directory): continue
            if f.lower().endswith(code_ext): code_files.append(p)

    if not code_files:
        logger.error(f"No code files found in: {directory}"); return

    logger.debug(f"Directory: {directory}")
    logger.info(f"Found {len(code_files)} code files")
    logger.info("Files to process:")
    for i, p in enumerate(code_files[:10], 1):
        logger.info(f"  {i:2d}. {os.path.relpath(p, directory)}")

    # Determine template type based on Serena availability and flags
    template_type = "fix"  # Default template
    if args.enable_serena or args.serena_mcp:
        template_type = "fix_with_serena"
        logger.info(f"🎯 Using Serena template: {template_type}")
    else:
        logger.info(f"📝 Using standard template: {template_type}")

    results = []
    for i, p in enumerate(code_files, 1):
        rel = os.path.relpath(p, directory)
        logger.info(f"[{i}/{len(code_files)}] {'Fixing'}: {rel}")
        file_issues = issues_by_file.get(rel, [])
        logger.debug(f"File issue to be fixed: {file_issues}")
        r = processor.fix_buggy_file(
            file_path=p, template_type=template_type,
            issues_data=file_issues
        )
        logger.debug("Fixed file %s with result: %s", rel, r)
        results.append(r)
        if r.success:
            logger.info(f"Success: {r.processing_time:.1f}s")
        else:
            logger.info(f"Failed: {r.message}, Validation errors: {r.validation_errors}")

    # summary
    success = sum(1 for r in results if r.success)
    errors = len(results) - success
    total_in = sum(r.input_tokens for r in results if r.success)
    total_out = sum(r.output_tokens for r in results if r.success)
    total_tok = sum(r.total_tokens for r in results if r.success)
    avg_sim = (sum(r.similarity_ratio for r in results if r.success) / max(success,1))
    thr_met = sum(1 for r in results if r.success and r.meets_threshold)
    avg_time = sum(r.processing_time for r in results)/max(len(results),1)

    logger.info("="*50)
    logger.info(f"FIX RESULT: {str(success).upper()}")
    logger.info(f"TOTAL INPUT TOKENS: {total_in}")
    logger.info(f"TOTAL OUTPUT TOKENS: {total_out}")
    logger.info(f"TOTAL TOKENS: {total_tok}")
    logger.info(f"AVERAGE SIMILARITY: {avg_sim:.3f}")
    logger.info(f"THRESHOLD MET COUNT: {thr_met}")
    logger.info(f"AVERAGE PROCESSING TIME: {avg_time:.1f}")

    summary = {
        "success": True,
        "fixed_count": success,
        "failed_count": errors,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tok,
        "average_similarity": avg_sim,
        "threshold_met_count": thr_met,
        "average_processing_time": avg_time,
    }
    logger.info("END_BATCH_RESULT")
    logger.info(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    run()
