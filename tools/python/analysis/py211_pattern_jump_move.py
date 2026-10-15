#!/usr/bin/env python3
"""PY-211 (#3539): patterns の jumpToPattern・movePattern・findFirstNextEmptyPat の委譲先本体を PE から検査する (実機不要)。

  python3 analysis/py211_pattern_jump_move.py <PE.bin> [--mutate]

PE は fl-win64 素材の extracted/block00031_PE.bin。各検査を 1 行 (PASS/FAIL) で出し、FAIL が 1 件でもあれば rc 1。
capstone で関数先頭から ret までを逆アセンブルし、rip 相対のメモリ参照は `addr + size + disp` で VA に解決する
(前段 REPORT_PY208 の G・表の番地は disp をそのまま書いていた。本スクリプトは VA で照合する)。

別算法の検算: 最後に `cmp eax, 0x3e7` (機械語 3d e7 03 00 00) を .text のファイル上で直接数え、逆アセンブル結果の番地と一致するかを見る。

--mutate: 検査の感度を見るネガティブコントロール。movePattern の上限 `cmp eax, 0x3e7` の即値を 0x3e8 に書き換えたメモリ上の複製で
検査し直し、`movePattern.upper_bound` が FAIL することを確認する (FAIL が出れば検査は効いている)。
"""
import sys

import capstone
import pefile

TABLE_VA = 0x193FCF8  # 0x12d8b39 の lea の rip 解決先 (disp 0x6671b8)
G_CB = 0x15E4790  # 3 つの callback が読む P の大域 (rip 解決先)
MOVE_BOUND_VA = 0xE33F09  # movePattern の cmp eax, 0x3e7

path = sys.argv[1]
mutate = "--mutate" in sys.argv[2:]
pe = pefile.PE(path, fast_load=True)
data = bytearray(open(path, "rb").read())
base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def foff(va):
    return text.PointerToRawData + (va - base - text.VirtualAddress)


if mutate:
    o = foff(MOVE_BOUND_VA)
    assert data[o:o + 5] == b"\x3d\xe7\x03\x00\x00", "mutate target mismatch"
    data[o + 1] = 0xE8


def decode(va, limit=0x1000):
    out = []
    for ins in md.disasm(bytes(data[foff(va):foff(va) + limit]), va):
        tgt = None
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
        out.append((ins.address, ins.mnemonic, ins.op_str, tgt))
        if ins.mnemonic == "ret":
            break
    return out


def find(fn, mnem, ops_sub, tgt=None):
    for addr, m, o, t in decode(fn):
        if m == mnem and ops_sub in o and (tgt is None or t == tgt):
            return addr
    return None


def nxt(fn, addr, k=1):
    ins = decode(fn)
    idx = [i for i, x in enumerate(ins) if x[0] == addr][0]
    return ins[idx + k]


results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


# jumpToPattern 本体 0x12d8af0
a = find(0x12D8AF0, "call", "qword ptr [rsi + 0x1f0]")
check("jump.vcall_1f0", a is not None, f"call [rsi+0x1f0] at {a and hex(a)}")
a = find(0x12D8AF0, "lea", "[rip", TABLE_VA)
check("jump.table_va", a is not None, f"lea rip->{TABLE_VA:#x} at {a and hex(a)}")
ins = decode(0x12D8AF0)
has_stride = any(m == "lea" and o == "rbx, [rbx + rbx*2]" for _, m, o, _ in ins) and any(
    m == "shl" and o == "rbx, 3" for _, m, o, _ in ins) and any(
    m == "mov" and o == "ecx, dword ptr [rax + rbx*8]" for _, m, o, _ in ins)
check("jump.stride_192", has_stride, "index*8 -> *3 -> [base + idx*24*8] = 192 B/要素 (dword +0 が要素の先頭)")
a = find(0x12D8AF0, "cmp", "dword ptr [rax + rcx*8], 0")
check("jump.elem_neg_skip", a is not None and nxt(0x12D8AF0, a)[1] == "jl",
      "cmp dword [表+idx*192], 0 の直後が jl (負なら呼出し省略)。表要素の符号だけを見る")
jump_ins = decode(0x12D8AF0)
idx_cmp = [(addr, o) for addr, m, o, _ in jump_ins if m == "cmp" and ("ebx" in o or "rbx" in o)]
check("jump.index_cmp_eq_only", len(idx_cmp) == 1 and idx_cmp[0][0] == 0x12D8AF8 and nxt(0x12D8AF0, 0x12D8AF8)[1] == "jne",
      f"index (ebx) を比較する cmp は {len(idx_cmp)} 件 (0x12d8af8: 現在番号 [0x15d51a0] との等号・直後 jne)。大小の比較は無い")
imm999 = [o for _, _, o, _ in jump_ins if "0x3e7" in o or "0x3e8" in o]
check("jump.no_999_imm", not imm999, f"jumpToPattern 本体 (0x12d8af0〜0x12d8bd0) の 999 (0x3e7)・1000 (0x3e8) の即値は {len(imm999)} 件")

# 表の所在: rip 解決先が .bss (ファイル上に初期値なし)
sec = None
for s in pe.sections:
    if s.VirtualAddress + base <= TABLE_VA < s.VirtualAddress + base + s.Misc_VirtualSize:
        sec = s
check("table.in_bss", sec is not None and sec.Name.rstrip(b"\0") == b".bss" and sec.SizeOfRawData == 0,
      f"section {sec.Name.rstrip(b'\\0').decode() if sec else None}, raw size {sec.SizeOfRawData if sec else None}")

# movePattern 本体 0xe33e20: 上限 999・下限 1 の検査 (O が NULL の分岐)
a = find(0xE33E20, "cmp", "eax, 0x3e7")
check("move.upper_bound_999", a is not None and nxt(0xE33E20, a)[1] == "jg",
      f"cmp eax, 0x3e7 at {a and hex(a)} の直後 jg (移動先 > 999 は呼ばない)")
a = find(0xE33E20, "test", "eax, eax")
check("move.lower_bound_1", a is not None and nxt(0xE33E20, a)[1] == "jle",
      f"test eax,eax at {a and hex(a)} の直後 jle (移動先 <= 0 は呼ばない)")
check("move.null_branch_uses_current", find(0xE33E20, "call", "0xe5af90") is not None,
      "O が NULL のとき call 0xe5af90 で現在パターン (min=max) を取る")
ins = decode(0xE5AF90)
rips = [t for _, m, o, t in ins if t is not None]
check("move.getter_min_eq_max", len(rips) == 2 and rips[0] == rips[1],
      f"0xe5af90 は同じ大域 {rips[0]:#x} を 2 回読み、*rdx と *r8 に書く (min == max)" if len(rips) == 2 else "rip 参照が 2 件でない")

# findFirstNextEmptyPat 探索 0x12d8be0: 候補は (start + k - 1) mod 999 + 1 (1..999)
check("find.mod_999", find(0x12D8BE0, "imul", "eax, eax, 0x3e7") is not None,
      "imul eax, eax, 0x3e7 (x mod 999 の逆算)")
check("find.iter_1000", find(0x12D8BE0, "cmp", "r13d, 0x3e8") is not None,
      "cmp r13d, 0x3e8 (1..1000 回の走査)")
bit2 = find(0x12D8BE0, "jne", "0x12d8d18")
check("find.bit2_early_ret", bit2 == 0x12D8C85,
      f"bit2 (4) が立つと jne 0x12d8d18 で jump も後段も省いて cand を返す (jne at {bit2 and hex(bit2)})")
c_ea7 = find(0x12D8BE0, "call", "0xea7ae0")
c_ea6 = find(0x12D8BE0, "call", "0xea6b30")
guard = find(0x12D8BE0, "mov", "rax, qword ptr [rip", 0x15E1748)
check("find.post_calls", c_ea7 is not None and c_ea6 is not None and guard is not None,
      f"後段: call 0xea7ae0 at {c_ea7 and hex(c_ea7)}・ガード [0x15e1748] at {guard and hex(guard)}・call 0xea6b30 at {c_ea6 and hex(c_ea6)} (役割は未同定 → #3558)")
w = 0x12D8D28
check("find.word_zero", data[foff(w):foff(w) + 2] == b"\x00\x00", f"movzx r9 の word [0x12d8d28] はファイル上 {bytes(data[foff(w):foff(w) + 2]).hex()}")

# 3 つの callback の共通 gate: P = [[G]+8]->vtable[+0x98]、初期 status -2
for name, fn in [("jump", 0xD659C0), ("move", 0xD66E70), ("find", 0xD65B30)]:
    g = find(fn, "mov", "rax, qword ptr [rip", G_CB)
    c = find(fn, "call", "qword ptr [rax + 0x98]")
    st = find(fn, "mov", "qword ptr [rbx + 0x60], 0xfffffffffffffffe")
    check(f"cb.{name}.gate", g is not None and c is not None and st is not None,
          f"G={G_CB:#x} load at {g and hex(g)}, call [rax+0x98] at {c and hex(c)}, status=-2 init at {st and hex(st)}")

# selectPattern: Python 値 - 1 (0xd662db の次)
a = find(0xD66230, "sub", "eax, 1")
prev = nxt(0xD66230, a, -1) if a else None
check("select.minus_one", a is not None and prev[1] == "mov" and "[rbp + 0xac]" in prev[2],
      f"mov eax,[rbp+0xac] at {prev and hex(prev[0])} -> sub eax,1 at {a and hex(a)}")

# movePattern の既定値 1
a = find(0xD66EC0, "mov", "dword ptr [rbp + 0x9c], 1")
check("move.default_1", a is not None, f"mov dword [rbp+0x9c], 1 at {a and hex(a)}")

# 0x409c80 = memmove(dst=rdx, src=rcx, n=r8)。n=1 は 1 バイト複写 (flags の下位 8 bit)
a = find(0xD65B30, "call", "0x409c80")
r8 = find(0xD65B30, "mov", "r8d, 1")
check("flags.copy_u8", a is not None and r8 is not None and find(0x409CC8, "movzx", "eax, byte ptr [rcx + r8 - 1]") is not None
      and find(0x409CC8, "mov", "byte ptr [rdx + r8 - 1], al") is not None,
      f"callback の call 0x409c80 at {a and hex(a)} (n=1)。0x409cc8 の 1 バイト経路で複写")

# 別算法の検算: 機械語の並び「cmp eax, 0x3e7 ; jg」(3d e7 03 00 00 と短距離 7f・近距離 0f 8f) を .text のファイル上で正規表現で数える
import re
seg = bytes(data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData])
hits = [base + text.VirtualAddress + m.start() for m in re.finditer(rb"\x3d\xe7\x03\x00\x00(?:\x7f|\x0f\x8f)", seg)]
check("crosscheck.bytes_3e7_jg", MOVE_BOUND_VA in hits,
      f"並び 3d e7 03 00 00 + jg の .text 上の出現 {len(hits)} 件 (同形は他関数にもある) の中に {MOVE_BOUND_VA:#x} がある")

print(f"summary: {sum(results)}/{len(results)} PASS" + (" (mutate)" if mutate else ""))
sys.exit(0 if all(results) else 1)
