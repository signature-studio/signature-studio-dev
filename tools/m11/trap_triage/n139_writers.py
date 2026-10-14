#!/usr/bin/env python3
# #2118 (M11-N139): unit 1 (function_41ce10) の呼出し木のうち、2 区間 (0xfa5108-0xfa5c64, 0x11e69b0-0x11e6b94)
# を書く (store する) 関数を boot_final.ll から特定する。
#   usage: python3 n139_writers.py <boot_final.ll> <out.json>
# 方式: 関数ごとに inttoptr 絶対定数 (i64 N) を集め、store のアドレス側として使われるものを区間判定する。
# 呼出しは直接 call の辺だけを辿る (indirect call は辿らないので、到達漏れの可能性は out.json の注記に残す)。
import json
import re
import sys

LL, OUT = sys.argv[1], sys.argv[2]
RANGES = [(0xfa5108, 0xfa5c64 + 8), (0x11e69b0, 0x11e6b94 + 4)]
ROOT = "function_41ce10"

fn_re = re.compile(r"^define [^@]*@(function_[0-9a-f]+)\(")
call_re = re.compile(r"call [^@]*@(function_[0-9a-f]+)\(")
const_re = re.compile(r"inttoptr \(i64 (\d+) to ptr\)")
store_re = re.compile(r"^\s*store .*?inttoptr \(i64 (\d+) to ptr\)")

funcs = {}
cur = None
for line in open(LL, encoding="utf-8", errors="replace"):
    m = fn_re.match(line)
    if m:
        cur = m.group(1)
        funcs[cur] = {"calls": set(), "store_consts": [], "ld_consts": [], "store_lines": 0}
        continue
    if cur is None:
        continue
    if line.startswith("}"):
        cur = None
        continue
    for c in call_re.findall(line):
        funcs[cur]["calls"].add(c)
    if " store " in line:
        for a in const_re.findall(line):
            funcs[cur]["store_consts"].append(int(a))
        funcs[cur]["store_lines"] += 1
    else:
        for a in const_re.findall(line):
            funcs[cur]["ld_consts"].append(int(a))


def hit(addr, lo_hi_list):
    return any(lo <= addr < hi for lo, hi in lo_hi_list)


# unit 1 の呼出し木 (直接 call のみ)
reach, stack = set(), [ROOT]
while stack:
    f = stack.pop()
    if f in reach or f not in funcs:
        continue
    reach.add(f)
    stack.extend(funcs[f]["calls"])

writers, readers = {}, {}
for f in sorted(reach):
    st = [a for a in funcs[f]["store_consts"] if hit(a, RANGES)]
    ld = [a for a in funcs[f]["ld_consts"] if hit(a, RANGES)]
    if st:
        writers[f] = sorted(set(st))
    if ld:
        readers[f] = sorted(set(ld))

out = {
    "root": ROOT,
    "reach_functions": len(reach),
    "ranges": [[hex(a), hex(b)] for a, b in RANGES],
    "writers": {k: [hex(x) for x in v] for k, v in writers.items()},
    "readers": {k: [hex(x) for x in v] for k, v in readers.items()},
    "note": "直接 call のみ辿る。indirect call 先は含まない。絶対定数 (inttoptr) のみを見る。base+offset 形式の書込みは別途確認が要る。",
}
json.dump(out, open(OUT, "w"), indent=1)
print("reach", len(reach), "writers", len(writers), "readers", len(readers))
for k, v in writers.items():
    print("W", k, [hex(x) for x in v])
for k, v in readers.items():
    print("R", k, [hex(x) for x in v])
