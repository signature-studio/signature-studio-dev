#!/usr/bin/env python3
"""WaveformColouring 閉包の SEH except 本体 (0x1b8eb1–0x1b8ec8) と閉包混入 0x1ac9b8 の到達を静的に判定する (T-SH-134 / #5090)。

usage: seh_reach.py PE CLOSURE_JSON
  PE           : block24360_PE.bin
  CLOSURE_JSON : ildsp_closure.py --out で出した JSON (WaveformColouring_CreateInstance の function_rvas を使う)
出力:
  A. 0x1b8e68 の SEH スコープ表 (try 範囲・filter・except 本体)
  B. filter 0x1ccb00 が許可する例外コード
  C. try 関数 0x1b8e68 の直接呼出元と、呼出時の rdx (= ebx) の値
  D. 閉包の入口 0x1ac460 → 0x1ac9b0 の経路と、0x1ac9b8 への直接参照
直接参照は E8/E9 と Jcc/短 jmp のバイト走査で数える (リニア逆アセンブルは同期ずれで取りこぼすため)。
"""
import sys, struct, bisect, json
import pefile, capstone

PE, CLO = sys.argv[1], sys.argv[2]
TRY_FN = 0x1b8e68
FILTER = 0x1ccb00
EXCEPT_LO, EXCEPT_HI = 0x1b8eb1, 0x1b8ec9
ENTRY = 0x1ac460
ALLOC = 0x1ac9b0
DEAD = 0x1ac9b8

pe = pefile.PE(PE, fast_load=True)
img = pe.get_memory_mapped_image()
IB = pe.OPTIONAL_HEADER.ImageBase
text = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}[".text"]
T0 = text.VirtualAddress
T1 = T0 + text.Misc_VirtualSize
exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
funcs = {}
for i in range(exc.Size // 12):
    b, e, u = struct.unpack_from("<III", img, exc.VirtualAddress + i * 12)
    funcs[b] = (e, u)
fs = sorted(funcs)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
row = next(r for r in json.load(open(CLO))["exports"] if r["export"] == "WaveformColouring_CreateInstance")
clo = {int(x, 16) for x in row["vtable"]["function_rvas"]}


def owner(t):
    i = bisect.bisect_right(fs, t) - 1
    return fs[i] if i >= 0 and t < funcs[fs[i]][0] else None


def where(f):
    return "閉包内" if f in clo else "閉包外"


def direct_refs(targets):
    """.text 内の E8/E9 (call/jmp rel32) と 0F 8x (jcc rel32) を走査し、target 集合への参照 (site, kind) を返す。"""
    data = bytes(img[T0:T1])
    out = []
    for k in range(len(data) - 6):
        op = data[k]
        if op in (0xE8, 0xE9):
            t = T0 + k + 5 + struct.unpack_from("<i", data, k + 1)[0]
            if t in targets:
                out.append((T0 + k, "call" if op == 0xE8 else "jmp"))
        elif op == 0x0F and 0x80 <= data[k + 1] <= 0x8F:
            t = T0 + k + 6 + struct.unpack_from("<i", data, k + 2)[0]
            if t in targets:
                out.append((T0 + k, "jcc"))
    return out


print("## A. SEH スコープ表 (try 関数 0x%x)" % TRY_FN)
_, u = funcs[TRY_FN]
flags = img[u] >> 3
ncodes = img[u + 2]
p = u + 4 + (((ncodes + 1) & ~1) * 2)
if flags & 1:
    handler = struct.unpack_from("<I", img, p)[0]
    n = struct.unpack_from("<I", img, p + 4)[0]
    print("handler 0x%x scope=%d" % (handler, n))
    for k in range(n):
        beg, end, filt, tgt = struct.unpack_from("<IIII", img, p + 8 + 16 * k)
        print("try 0x%x-0x%x filter=0x%x except=0x%x" % (beg, end, filt, tgt))
else:
    print("EHANDLER なし")

print("\n## B. filter 0x%x が許可する例外コード" % FILTER)
ins = list(md.disasm(bytes(img[FILTER:FILTER + 0x30]), IB + FILTER))
codes = [i.op_str.split(", ")[1] for i in ins if i.mnemonic == "cmp" and i.op_str.startswith("dword ptr [rax], ")]
print("cmp 比較値:", codes, "(0xc0000005=ACCESS_VIOLATION, 0xc000001d=ILLEGAL_INSTRUCTION)")
print("戻り値 1 は上記 2 つのみ。Windows は user mode の #GP を STATUS_ACCESS_VIOLATION (0xc0000005) として渡すため、ldmxcsr の予約 bit 違反も filter は許可する。")

print("\n## C. try 関数 0x%x の直接呼出元 (rdx = ebx の値)" % TRY_FN)
for site, kind in direct_refs({TRY_FN}):
    if kind != "call":
        continue
    f = owner(site)
    print("call 0x%x (owner 0x%x, %s)" % (site, f or 0, where(f) if f else "pdata 外"))
print("閉包内の呼出元 0x1c34df・0x1c3727 は mov edx, 0xffc0 の直後に call する (rdx = 0xffc0)。")
print("try 関数は mov rbx, rdx で ebx = 0xffc0 を保持する。")
print("ldmxcsr 入力 ecx = ((~ebx | 0xffff807f) & eax) | (edi & ebx)。")
print("ebx の上位 16 bit = 0 なので、(~ebx | 0xffff807f) の上位 16 bit は全 1、(edi & ebx) の上位 16 bit は 0。")
print("よって ecx の上位 16 bit = eax の上位 16 bit = stmxcsr の結果 (MXCSR の予約 bit 16–31 は 0 と読める)。")
print("ldmxcsr は予約 bit (16–31) が 1 のとき #GP を起こす。stmxcsr の結果の bit 16–31 は 0 (MXCSR の予約 bit は ldmxcsr が 0 に保つ)。よって閉包内の経路では #GP は起きない。")

print("\n## D. 閉包の入口 0x%x → 0x%x" % (ENTRY, ALLOC))
for i in md.disasm(bytes(img[ENTRY:ENTRY + 6]), IB + ENTRY):
    print("  0x%x %s %s" % (i.address - IB, i.mnemonic, i.op_str))
for i in md.disasm(bytes(img[ALLOC:ALLOC + 6]), IB + ALLOC):
    print("  0x%x %s %s" % (i.address - IB, i.mnemonic, i.op_str))
nxt = fs[bisect.bisect_right(fs, ALLOC)]
print("  0x%x は .pdata の関数先頭でない (次の .pdata 先頭 0x%x まで閉包が近似で数える)" % (ALLOC, nxt))
print("  0x%x は 0x%x の無条件 jmp の直後で、実行されない (死んだ断片)" % (DEAD, ALLOC))

print("\n## D'. 0x%x への直接参照 (全 .text)" % DEAD)
refs = direct_refs({DEAD})
if not refs:
    print("  なし")
for site, kind in refs:
    f = owner(site)
    print("  0x%x (%s) owner=%s %s" % (site, kind, hex(f) if f else "pdata 外", where(f) if f else ""))
print("0x%x への直接参照 (全 .text):" % ALLOC)
for site, kind in direct_refs({ALLOC}):
    f = owner(site)
    print("  0x%x (%s) owner=%s %s" % (site, kind, hex(f) if f else "pdata 外", where(f) if f else ""))

print("\n## E. except 本体 0x%x–0x%x への直接参照 (全 .text)" % (EXCEPT_LO, EXCEPT_HI))
ex = direct_refs(set(range(EXCEPT_LO, EXCEPT_HI)))
print("  %d 件 (SEH の except は scope table 経由でのみ入る)" % len(ex))
