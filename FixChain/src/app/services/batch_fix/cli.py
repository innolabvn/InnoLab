# src/app/services/batch_fix/cli.py
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from dotenv import load_dotenv
from src.app.services.log_service import logger
from app.services.batch_fix.processor import SecureFixProcessor

def run():
    parser = argparse.ArgumentParser(description="Secure Batch Fix (AI-powered)")
    parser.add_argument("destination", nargs="?", help="Directory to scan/fix")
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--prompt", type=str)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--issues-file", type=str)
    parser.add_argument("--enable-rag", action="store_true")
    args = parser.parse_args()

    # .env (for GOOGLE_API_KEY used by adapters.llm.google_genai)
    root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
    load_dotenv(root_env)

    directory = args.destination or input("Enter directory path: ").strip()
    if not directory or not os.path.isdir(directory):
        print(f"Invalid directory: {directory}"); return

    fix_mode = args.fix and not args.scan_only
    print("\nFIXING Mode" if fix_mode else "\nSCANNING Mode")

    issues_by_file = {}
    if args.issues_file and os.path.exists(args.issues_file):
        try:
            data = json.loads(Path(args.issues_file).read_text(encoding="utf-8"))
            for it in data.get("issues", []):
                fp = os.path.normpath(it.get("file_path",""))
                if fp: issues_by_file.setdefault(fp, []).append(it)
        except Exception as e:
            logger.warning("Cannot load issues file: %s", e)

    processor = SecureFixProcessor(directory, None)
    processor.load_ignore_patterns(directory)

    # collect files
    code_ext = (".py",".js",".ts",".jsx",".tsx",".java",".cpp",".c",".html",".css",".txt")
    code_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not processor.should_ignore_file(os.path.join(root,d), directory)]
        for f in files:
            p = os.path.join(root, f)
            if processor.should_ignore_file(p, directory): continue
            if f.lower().endswith(code_ext): code_files.append(p)

    if not code_files:
        print(f"No code files found in: {directory}"); return

    print(f"\nDirectory: {directory}")
    print(f"Found {len(code_files)} code files")
    print("\nFiles to process:")
    for i, p in enumerate(code_files[:10], 1):
        print(f"  {i:2d}. {os.path.relpath(p, directory)}")
    if len(code_files) > 10:
        print(f"  ... and {len(code_files)-10} more files")

    if not args.auto:
        act = "fix" if fix_mode else "scan"
        confirm = input(f"\n{act.title()} {len(code_files)} files? (y/N): ").strip().lower()
        if confirm not in ("y","yes"): print("Cancelled"); return
    else:
        print("\nAuto mode: proceeding without confirmation")

    results = []
    for i, p in enumerate(code_files, 1):
        rel = os.path.relpath(p, directory)
        print(f"\n[{i}/{len(code_files)}] {'Fixing' if fix_mode else 'Scanning'}: {rel}")
        if fix_mode:
            file_issues = issues_by_file.get(rel, [])
            r = processor.fix_file_with_validation(
                p, template_type="fix", custom_prompt=args.prompt,
                issues_data=file_issues, enable_rag=args.enable_rag
            )
        else:
            r = processor.scan_file_only(p)
        results.append(r)
        if r.success:
            print(f"  {'Success' if fix_mode else 'Scanned'} ({r.processing_time:.1f}s)")
        else:
            print(f"  Failed: {'; '.join(r.issues_found)}")

    # summary
    success = sum(1 for r in results if r.success)
    errors = len(results) - success
    total_in = sum(r.input_tokens for r in results if r.success)
    total_out = sum(r.output_tokens for r in results if r.success)
    total_tok = sum(r.total_tokens for r in results if r.success)
    avg_sim = (sum(r.similarity_ratio for r in results if r.success) / max(success,1)) if fix_mode else 0.0
    thr_met = sum(1 for r in results if r.success and r.meets_threshold)
    avg_time = sum(r.processing_time for r in results)/max(len(results),1)

    print("\n" + "="*70)
    if fix_mode:
        print("BATCH_FIX_RESULT: SUCCESS")
        print(f"FIXED_FILES: {success}")
        print(f"FAILED_FILES: {errors}")
        print(f"TOTAL_INPUT_TOKENS: {total_in}")
        print(f"TOTAL_OUTPUT_TOKENS: {total_out}")
        print(f"TOTAL_TOKENS: {total_tok}")
        print(f"AVERAGE_SIMILARITY: {avg_sim:.3f}")
        print(f"THRESHOLD_MET_COUNT: {thr_met}")
        print(f"SIMILARITY_THRESHOLD: {processor.similarity_threshold}")
    else:
        print("BATCH_SCAN_RESULT: SUCCESS")
        print(f"SCANNED_FILES: {success}")
        print(f"FAILED_FILES: {errors}")
        files_with_issues = sum(1 for r in results if r.success and r.issues_found != ["No issues found"])
        print(f"FILES_WITH_ISSUES: {files_with_issues}")
        print(f"CLEAN_FILES: {success - files_with_issues}")
    print(f"AVERAGE_PROCESSING_TIME: {avg_time:.1f}")

    summary = {
        "success": True,
        "fixed_count": success if fix_mode else 0,
        "failed_count": errors,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tok,
        "average_similarity": avg_sim,
        "threshold_met_count": thr_met,
        "similarity_threshold": processor.similarity_threshold,
        "average_processing_time": avg_time,
    }
    print("\nEND_BATCH_RESULT")
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    run()
