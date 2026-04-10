import os
import sys


IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def log_progress(current: int, total: int):
    if IS_CI:
        if current == 1 or current == total or current % 5 == 0:
            print(f"    visiting {current}/{total}...", flush=True)
    else:
        print(f"\r    visiting {current}/{total}...", end="", flush=True)


def log_done():
    if not IS_CI:
        print("", flush=True)
