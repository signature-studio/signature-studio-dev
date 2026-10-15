#!/usr/bin/env python3
"""reach_order_check.py — 到達ログ (GUI-REACH / GUI-MSG 行) の順序検査 (#3510: W 版 Win32 ゲストの GUI 通し)。

入力: ログファイル (native_w_run.log など)。行の出現順が到達順 (gui_reach_dump は初回到達の順に出す)。
検査:
  - 次の名前がそれぞれ 1 回以上ある: RegisterClassW CreateWindowExW PeekMessageW DispatchMessageW
    DefWindowProcW BeginPaint BitBlt (GUI-REACH 行) と WM_PAINT (GUI-MSG 行 = window proc への配送)
  - 初回の出現順が RegisterClassW < CreateWindowExW < WM_PAINT < BitBlt
usage: reach_order_check.py <log>      (exit 0 = PASS / 1 = FAIL)
       reach_order_check.py --selftest (合成ログで検査の判定自体を確かめる)
"""
import re, sys

REACH = re.compile(r"GUI-REACH (\d+) (\S+) (\d+) (?:IMPL|STUB) P\S+")
MSG = re.compile(r"GUI-MSG (\S+) (\d+)")
NEED = ["RegisterClassW", "CreateWindowExW", "PeekMessageW", "DispatchMessageW", "DefWindowProcW", "BeginPaint", "BitBlt", "WM_PAINT"]
ORDER = ["RegisterClassW", "CreateWindowExW", "WM_PAINT", "BitBlt"]

def trace(text):
    seq = []
    for line in text.splitlines():
        m = REACH.search(line)
        if m: seq.append(m.group(2)); continue
        m = MSG.search(line)
        if m: seq.append(m.group(1))
    return seq

def check(seq):
    fails = [n + " が無い" for n in NEED if n not in seq]
    if not fails:
        first = [seq.index(n) for n in ORDER]
        if any(a >= b for a, b in zip(first, first[1:])):
            fails.append("初回の順序が不正: " + " < ".join("%s@%d" % (n, i) for n, i in zip(ORDER, first)))
    return fails

GOOD = ["GUI-REACH 1 RegisterClassW 2 IMPL P0", "GUI-REACH 2 CreateWindowExW 2 IMPL P0",
        "GUI-REACH 3 PeekMessageW 3 IMPL P0", "GUI-REACH 4 DispatchMessageW 1 IMPL P0",
        "GUI-REACH 5 DefWindowProcW 2 IMPL P0", "GUI-MSG WM_PAINT 2", "GUI-REACH 6 BeginPaint 1 IMPL P0",
        "GUI-REACH 7 BitBlt 1 IMPL P0", "GUI-REACH-SUMMARY reached=7 impl=7 stub=0"]

def selftest():
    cases = [
        ("正例", GOOD, 0),
        ("WM_PAINT 行が無い (旧 shim)", [l for l in GOOD if not l.startswith("GUI-MSG")], 1),
        ("BitBlt が WM_PAINT より前", GOOD[:5] + [GOOD[7], GOOD[5], GOOD[6], GOOD[8]], 1),
        ("CreateWindowExW が RegisterClassW より前", [GOOD[1], GOOD[0]] + GOOD[2:], 1),
    ]
    bad = 0
    for name, lines, want in cases:
        rc = 1 if check(trace("\n".join(lines))) else 0
        ok = rc == want
        bad += 0 if ok else 1
        print("[reach_order_check] selftest %s: %s (want %s)" % (name, "ok" if ok else "NG", "FAIL" if want else "PASS"))
    print("[reach_order_check] selftest %s" % ("PASS" if not bad else "FAIL (%d)" % bad))
    return 1 if bad else 0

def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) != 2:
        print(__doc__, file=sys.stderr); return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        seq = trace(f.read())
    fails = check(seq)
    if fails:
        for m in fails: print("[reach_order_check] FAIL: " + m)
        return 1
    print("[reach_order_check] PASS (%d 件の到達行; 順序 %s)" % (len(seq), " < ".join(ORDER)))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
