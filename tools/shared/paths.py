"""外部資産パスの共通定義 (python)。tools/shared/env.sh と同じ変数名・既定値。

使い方: sys.path に tools/shared を足して `from paths import FL_WIN64_DIR` する。
環境変数が設定済みならそれを優先し、未設定時のみ従来 (作業用 VM) の既定値を使う。
変数と docs/REFERENCES.md のエントリ ID の対応は docs/REFERENCES.md §4。
"""
import os
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _repo_root() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_HERE), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return str(_HERE.parent.parent)


REPO_ROOT = os.environ.get("REPO_ROOT") or _repo_root()
ANALYSIS_DIR = os.environ.get("ANALYSIS_DIR") or "/home/ubuntu/work/analysis"
FL_WIN64_DIR = os.environ.get("FL_WIN64_DIR") or f"{ANALYSIS_DIR}/win64"
FL_MAC_DIR = os.environ.get("FL_MAC_DIR") or f"{ANALYSIS_DIR}/mac"
PLUGINS_DIR = os.environ.get("PLUGINS_DIR") or f"{ANALYSIS_DIR}/plugins"

ALL = {
    "REPO_ROOT": REPO_ROOT,
    "ANALYSIS_DIR": ANALYSIS_DIR,
    "FL_WIN64_DIR": FL_WIN64_DIR,
    "FL_MAC_DIR": FL_MAC_DIR,
    "PLUGINS_DIR": PLUGINS_DIR,
}

if __name__ == "__main__":
    for k, v in ALL.items():
        print(f"{k}={v}")
