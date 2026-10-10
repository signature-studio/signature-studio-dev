#!/usr/bin/env python3
"""check_p1_tests.py — CAB-159 の 50 名 (+CreateCaret) が (1) IMPL であり (2) test/selftest_p1.inc に呼出 `NAME(` として登場することを機械検査する。
exit 0 = OK。e2e.sh から呼ぶ。"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); GUI = os.path.dirname(HERE)
names = [l.strip() for l in open(os.path.join(HERE, "p1_batch.txt")) if l.strip() and not l.startswith("#")]
exports = set(l.strip() for l in open(os.path.join(GUI, "exports.txt")) if l.strip() and not l.startswith("#"))
test = open(os.path.join(GUI, "test", "selftest_p1.inc"), encoding="utf-8").read()
bad = []
for n in names:
    calls = len(re.findall(r"(?<![\w.])%s\(" % re.escape(n), test))
    if n not in exports: bad.append("%s: not implemented (exports.txt)" % n)
    elif calls < 1: bad.append("%s: no unit test call in selftest_p1.inc" % n)
print("[check_p1_tests] %d APIs: implemented %d, with unit test %d" % (len(names), sum(n in exports for n in names), sum(len(re.findall(r"(?<![\w.])%s\(" % re.escape(n), test)) > 0 for n in names)))
for b in bad: print("  FAIL", b)
sys.exit(1 if bad else 0)
