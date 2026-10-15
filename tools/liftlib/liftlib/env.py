"""env.py — emsdk (emcc/node) の環境を 1 回だけ取り込み, 以後 subprocess に引き継ぐ。"""
import os
import subprocess
import sys
from typing import Any, MutableMapping, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import ANALYSIS_DIR, PLUGINS_DIR  # noqa: E402

_DONE = False
EMSDK = os.environ.get("EMSDK_DIR", "/opt/emsdk")
OTT_DLL = os.environ.get("OTT_DLL") or os.path.join(PLUGINS_DIR, "ott", "binaries", "OTT_vst2_win64.dll")
# target json のパス欄で `${NAME}` として参照できる環境パス (固定の絶対パスを json に書かない)
PATH_VARS = {"ANALYSIS_DIR": ANALYSIS_DIR, "PLUGINS_DIR": PLUGINS_DIR, "OTT_DLL": OTT_DLL}


def ensure() -> MutableMapping[str, str]:
    global _DONE
    if _DONE:
        return os.environ
    if not (os.path.exists("/usr/bin/emcc") or any(os.access(os.path.join(p, "emcc"), os.X_OK) for p in os.environ.get("PATH", "").split(":"))):
        r = subprocess.run(["bash", "-c", "source %s/emsdk_env.sh >/dev/null 2>&1; env -0" % EMSDK], capture_output=True)
        for kv in r.stdout.split(b"\0"):
            if b"=" in kv:
                kb, vb = kv.split(b"=", 1)
                k, v = kb.decode(), vb.decode()
                if k in ("PATH", "EMSDK", "EM_CONFIG", "EMSDK_NODE", "EMSDK_PYTHON", "EM_CACHE", "EM_FROZEN_CACHE"):
                    os.environ[k] = v
    _DONE = True
    return os.environ


def run(cmd: Sequence[str] | str, **kw: Any) -> subprocess.CompletedProcess[Any]:
    ensure()
    return subprocess.run(cmd, **kw)
