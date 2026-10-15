#!/usr/bin/env python3
"""PY-264 (#3888): 0x11b2ac0 の呼出し経路 (0x1375990 の大域ポインタ格納) と vptr 候補 0xed0c28 の読出し経路を確認する。

  FL_WIN64_DIR=<展開先> python3 analysis/py264_chain_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
出力: 各確認の PASS/FAIL と件数。期待値と異なれば rc 1。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CALLGRAPH = os.path.join(HERE, "flapi", "pe_callgraph.py")
RIPREFS = os.path.join(HERE, "flapi", "pe_rip_refs.py")

CHECKS = [
    ("0x11b2ac0 の RIP 相対 lea は 1 件 (0x1375a18)", [RIPREFS, "0x11b2ac0"], "hits 1", "0x1375a18"),
    ("大域ポインタ 0x15dff78 の RIP 相対参照は 1 件 (0x1375a11)", [RIPREFS, "0x15dff78"], "hits 1", "0x1375a11"),
    ("0x1375990 の直接 call 元は 0 件", [CALLGRAPH, "callers", "0x1375990"], "direct call sites 0", None),
    ("セル 0xed0b60 の RIP 相対読出しは 1 件 (0x11b2af9)", [RIPREFS, "0xed0b60"], "hits 1", "0x11b2af9"),
    ("vptr 候補 0xed0c28 の RIP 相対参照は 0 件", [RIPREFS, "0xed0c28"], "hits 0", None),
    ("0x410320 の直接 call 元は 0 件以上 (vtable 間接 call のみ)", [CALLGRAPH, "around", "0x410320", "0x410330"], "call qword ptr", None),
]


def run(args):
    env = dict(os.environ)
    if "FL_WIN64_DIR" not in env:
        sys.exit("FL_WIN64_DIR が未設定")
    out = subprocess.run([sys.executable] + args, env=env, capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def main():
    rc = 0
    for label, args, expect, must in CHECKS:
        text = run(args)
        ok = expect in text and (must is None or must in text)
        print("%s %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            rc = 1
    print("chain.check %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
