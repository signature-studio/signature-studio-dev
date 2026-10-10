"""env.py — emsdk (emcc/node) の環境を 1 回だけ取り込み, 以後 subprocess に引き継ぐ。"""
import os
import subprocess

_DONE = False
EMSDK = os.environ.get("EMSDK_DIR", "/opt/emsdk")


def ensure():
    global _DONE
    if _DONE:
        return os.environ
    if not (os.path.exists("/usr/bin/emcc") or any(os.access(os.path.join(p, "emcc"), os.X_OK) for p in os.environ.get("PATH", "").split(":"))):
        r = subprocess.run(["bash", "-c", "source %s/emsdk_env.sh >/dev/null 2>&1; env -0" % EMSDK], capture_output=True)
        for kv in r.stdout.split(b"\0"):
            if b"=" in kv:
                k, v = kv.split(b"=", 1)
                k, v = k.decode(), v.decode()
                if k in ("PATH", "EMSDK", "EM_CONFIG", "EMSDK_NODE", "EMSDK_PYTHON", "EM_CACHE", "EM_FROZEN_CACHE"):
                    os.environ[k] = v
    _DONE = True
    return os.environ


def run(cmd, **kw):
    ensure()
    return subprocess.run(cmd, **kw)
