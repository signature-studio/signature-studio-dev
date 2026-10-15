#!/usr/bin/env python3
# log_cap_check.py — FLE-40 (#5027): FLE_BOOT_LOG_CAP 超過が boot.threw の log_cap として報告されることを、
# 既定経路 (run_boot default) の結果 JSON で確かめる。規則を壊すと落ちる (fle_boot.mjs の分類を戻すと FAIL)。
#   python3 tools/flelift/boot/log_cap_check.py <cap 付き JSON> <cap なし JSON>
import json
import sys


def load(p):
    with open(p) as f:
        return json.load(f)


def main():
    cap, nocap = load(sys.argv[1]), load(sys.argv[2])
    fails = []
    lc = cap.get("log_cap") or {}
    if lc.get("hit") != "bytes":
        fails.append("cap 超過の hit が bytes でない: %r" % lc.get("hit"))
    bc = cap.get("boot") or {}
    threw = (bc.get("threw") or {}).get("cls")
    if threw != "log_cap":
        fails.append("cap 超過で boot.threw.cls が log_cap でない: %r" % threw)
    raw = (bc.get("threw_raw") or {}).get("cls")
    if raw != "exit":
        fails.append("cap 超過の生の停止理由が exit でない: %r" % raw)
    bn = nocap.get("boot") or {}
    if (nocap.get("log_cap") or {}).get("hit") is not None:
        fails.append("cap なしで hit が立っている")
    if (bn.get("threw") or {}).get("cls") != "exit":
        fails.append("cap なしの boot.threw.cls が exit でない: %r" % (bn.get("threw") or {}).get("cls"))
    if bc.get("units_run") != bn.get("units_run"):
        fails.append("units_run が cap の有無で違う: %r vs %r" % (bc.get("units_run"), bn.get("units_run")))
    for m in fails:
        print("FAIL", m)
    print("PASS" if not fails else "FAIL (%d)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
