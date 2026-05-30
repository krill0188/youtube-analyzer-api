"""디버그용 — 실제 import 에러 확인"""
import sys
import traceback

try:
    print("Step 1: importing fastapi...", flush=True)
    from fastapi import FastAPI
    print("Step 1: OK", flush=True)

    print("Step 2: importing analyzer...", flush=True)
    from analyzer import analyze_video
    print("Step 2: OK", flush=True)

    print("Step 3: importing main...", flush=True)
    import main
    print("Step 3: OK", flush=True)

    print("ALL IMPORTS OK", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
