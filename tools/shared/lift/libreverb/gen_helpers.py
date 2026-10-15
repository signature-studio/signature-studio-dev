#!/usr/bin/env python3
"""gen_helpers.py IN.ll OUT.c [--break OP] — lift IR の `declare @__asm_*` から SSE scalar helper の C 実装を生成する。
規約は tools/m6..m11 の msimd と同じ: i128 = xmm 全体 (lane0 = 下位 32bit)、IEEE round-to-nearest。
RetDec は同名・異シグネチャの declare に `.NNN` を付けるので、C 側は asm label で記号名を一致させる。
未知の op / 想定外のシグネチャは exit 1 (黙って no-op にしない)。
--break OP : ネガティブコントロール用。addss/subss/mulss のどれか 1 種の演算を意図的に誤らせる (add→sub, sub→add, mul→add)。"""
import re, sys

args = sys.argv[1:]
brk = None
if "--break" in args:
    i = args.index("--break"); brk = args[i + 1]; del args[i:i + 2]
assert brk in (None, "addss", "subss", "mulss"), brk
src = open(args[0]).read()
decls = re.findall(r"^declare (\S+) @(__asm_[A-Za-z0-9_.]+)\(([^)]*)\)", src, re.M)
T = {"i128": "u128", "i64": "uint64_t", "i32": "uint32_t", "i8": "uint8_t", "void": "void"}
out = ['#include <stdint.h>', '#include <string.h>', 'typedef unsigned __int128 u128;',
       'static float f0(u128 a){uint32_t u=(uint32_t)a;float f;memcpy(&f,&u,4);return f;}',
       'static float fb(uint32_t u){float f;memcpy(&f,&u,4);return f;}',
       'static u128 setl(u128 a,float f){uint32_t u;memcpy(&u,&f,4);return (a&~(u128)0xffffffffu)|u;}']
ARITH = {"addss": "+", "subss": "-", "mulss": "*"}
BROKEN = {"addss": "-", "subss": "+", "mulss": "+"}
nh = {}
unsup = []
for i, (ret, name, a_) in enumerate(decls):
    op = re.match(r"__asm_([a-z0-9]+)", name).group(1)
    a = [x.strip() for x in a_.split(",") if x.strip()]
    params = ", ".join(f"{T[t]} p{j}" for j, t in enumerate(a))
    head = f"{T[ret]} h{i}({params})"
    if op == "movss" and a == ["i32"] and ret == "i128": body = "return (u128)p0;"
    elif op == "movss" and a == ["i128"] and ret in ("i64", "i32"): body = f"return ({T[ret]})(uint32_t)p0;"
    elif op == "movaps" and a == ["i128"] and ret == "i128": body = "return p0;"
    elif op in ("movaps", "movapd") and a == ["i128"] and ret in ("i64", "i32"): body = f"return ({T[ret]})p0;"
    elif op == "movq" and a == ["i64"] and ret == "i128": body = "return (u128)p0;"
    elif op == "punpcklbw" and a == ["i128", "i128"] and ret == "i128":
        body = "u128 r=0; for(int k=0;k<8;k++){ r|=((p0>>(8*k))&0xff)<<(16*k); r|=((p1>>(8*k))&0xff)<<(16*k+8); } return r;"
    elif op == "int3" and a == [] and ret == "i64": body = "__builtin_trap(); return 0;"
    elif op == "sfence" and a == [] and ret == "i64": body = "return 0;"
    elif op in ARITH and len(a) == 2 and a[0] == "i128" and ret == "i128" and a[1] in ("i128", "i32"):
        y = "f0(p1)" if a[1] == "i128" else "fb(p1)"
        sym = BROKEN[op] if brk == op else ARITH[op]
        body = f"float x=f0(p0),y={y}; return setl(p0,x{sym}y);"
    elif op == "xorps" and a == ["i128", "i128"] and ret == "i128": body = "return p0^p1;"
    elif op == "ucomiss" and a == ["i128", "i128"] and ret == "void": body = ""
    else:
        unsup.append(f"declare {ret} @{name}({a_})")
        continue
    out.append(f'{head} __asm__("{name}");')
    out.append(f"{head} {{ {body} }}")
    nh[op] = nh.get(op, 0) + 1
if unsup:
    print(f"[gen_helpers] {len(unsup)} unsupported helper signatures (全数):", file=sys.stderr)
    for u in unsup: print(f"  {u}", file=sys.stderr)
    sys.exit(1)
open(args[1], "w").write("\n".join(out) + "\n")
print(f"[gen_helpers] {len(decls)} helpers ({', '.join(f'{k}:{v}' for k, v in sorted(nh.items()))})" + (f" BREAK={brk}" if brk else "") + f" -> {args[1]}")
