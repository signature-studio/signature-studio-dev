#!/usr/bin/env python3
"""x86_64 Mach-O slice の __text を llvm-objdump で逆アセンブルして命令数 / SIMD 比率を実測する。
   usage: simd_stats.py <slice> <out.json>   (stream 処理; 33MB でも数分)"""
import sys, subprocess, json, re, collections
sl, out = sys.argv[1], sys.argv[2]
p = subprocess.Popen(["llvm-objdump", "-d", "--macho", "--no-show-raw-insn", "--section=__text", sl],
                     stdout=subprocess.PIPE, text=True, errors="replace", bufsize=1 << 20)
tot = 0; cls = collections.Counter(); mn = collections.Counter(); funcs = 0; calls = 0; indirect = 0
for line in p.stdout:
    if not line.startswith("\t") and ":" not in line[:2] and not line[0].isspace():
        # 関数ラベル行 "_sym:" or "0000... <sym>:" は命令行ではない
        if line.rstrip().endswith(":"): funcs += 1
        continue
    parts = line.split("\t")
    if len(parts) < 2: continue
    ins = " ".join(p.strip() for p in parts[1:])
    if not ins: continue
    m = ins.split()[0]
    tot += 1
    if m.startswith("call"):
        calls += 1
        if "*" in ins: indirect += 1
    if "%zmm" in ins or "{%k" in ins: c = "avx512"
    elif "%ymm" in ins: c = "avx_256"
    elif "%xmm" in ins:
        if m.startswith("v"): c = "avx_128"
        elif m.endswith(("ss", "sd")) and not m.startswith("p"): c = "sse_scalar"
        elif m.endswith(("ps", "pd")) or m.startswith(("p", "unpck", "shuf", "movap", "movup", "movdq", "movlh", "movhl", "cvt", "andn", "xorp", "orp", "andp")): c = "sse_packed"
        else: c = "sse_other"
    elif m.startswith(("fld", "fst", "fadd", "fmul", "fsub", "fdiv", "fxch", "fild", "fist")): c = "x87"
    else: c = "scalar_int"
    cls[c] += 1
    if c not in ("scalar_int",): mn[m] += 1
res = {"slice": sl, "instructions": tot, "labels": funcs, "calls": calls, "indirect_calls": indirect,
       "classes": dict(cls), "simd_ratio": round(sum(v for k, v in cls.items() if k not in ("scalar_int", "x87")) / max(tot, 1), 4),
       "top_simd_mnemonics": mn.most_common(12)}
json.dump(res, open(out, "w"))
print(sl.split("/")[-1], tot, res["simd_ratio"], dict(cls))
