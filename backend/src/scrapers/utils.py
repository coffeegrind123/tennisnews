import sys


def log_progress(current: int, total: int):
    print(f"\r    visiting {current}/{total}...", end="", flush=True)


def log_done():
    print("", flush=True)
