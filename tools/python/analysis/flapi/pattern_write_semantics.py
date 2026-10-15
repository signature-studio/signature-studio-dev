#!/usr/bin/env python3
"""PY-4871 (#5130): patterns 書き込み系の副作用読解 (burnLoop・clearPattern・ensureValidNoteRecord・setLoopStarterRootNote) を PE 上で判定する (実機不要)。

  python3 analysis/flapi/pattern_write_semantics.py <PE.bin>

各 VA の命令列 (ret / int3 まで) に対し、REPORT_PY4871.md §2・§6 の事実を「命令の順序一致」で判定する。
1 つでも不一致なら終了コード 1。文字列の読みは .rdata から取る。
"""
import sys

import capstone
import pefile

CHECKS = [
    (0x12D8AF0, "0x12d8af0: vt+0x1f0 呼び出し (値は返さない)",
     ["call qword ptr [rsi + 0x1f0]", "ret"]),
    (0xD66CB0, "clearPattern コア: 0..999 で 0x12d8af0 → vt+0x100",
     ["call 0x12d8af0", "call qword ptr [rbx + 0x100]"]),
    (0xD66CB0, "clearPattern コア: index > 999 は -4 (0xfffffffffffffffc)",
     ["cmp rax, 0x3e7", "mov qword ptr [rbx + 0x60], 0xfffffffffffffffc"]),
    (0x1063C40, "burnLoop コア: 入口で [obj+0x54] が 0 なら後始末へ",
     ["cmp byte ptr [rax + 0x54], 0", "je 0x1064077"]),
    (0x1063C40, "burnLoop コア: [obj+0x58] list を stride 20 で走査し key == index かつ flag != 0 を探す",
     ["mov rcx, qword ptr [rcx + 0x58]", "lea r9, [r9 + r9*4]", "cmp dword ptr [rdx + r9*4], r10d",
      "cmp dword ptr [rdx + rcx*4 + 4], 0"]),
    (0x1064077, "burnLoop 後始末: 0x412d60 → 0x418190 で戻る",
     ["call 0x412d60", "call 0x418190", "ret"]),
    (0x1063A20, "record 生成 (0x1063a20): [obj+0x54] = 0・[obj+0x50] = 1",
     ["mov byte ptr [rax + 0x54], 0", "mov dword ptr [rax + 0x50], 1"]),
    (0x11E7430, "0x11e7430 前半: 1000 件 (stride 0xc0) に +0x6c = 0x80000001・+0x70 = 0x7fffffff",
     ["mov edx, 0x3e8", "mov dword ptr [rax + 0x6c], 0x80000001", "mov dword ptr [rax + 0x70], 0x7fffffff",
      "add rcx, 0xc0"]),
    (0x11E7430, "0x11e7430 後段: 0x11e7652 以降の record 走査 (stride 12) で 0x663bf0・0x1046a30 を呼ぶ",
     ["call 0x663bf0", "call 0x1046a30"]),
    (0xDC0700, "0xdc0700: table[cur].+0xa4 != 0 のとき +0xa8 - 1 から文字列を作る (0x661dc0)",
     ["cmp byte ptr [rcx + rdx*8 + 0xa4], 0", "sub edx, 1", "call 0x661dc0"]),
    (0xDC0700, "0xdc0700: 即値 0xc3bfb9 (Python コード片の文字列) を 0x6682f0 へ渡す",
     ["mov edx, 0xc3bfb9", "call 0x6682f0"]),
]
STRING_VA = 0xC3BFB9


def main():
    path = sys.argv[1]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def body(va, n=0x2000):
        out = []
        for ins in md.disasm(data[off(va):off(va) + n], va):
            out.append(f"{ins.mnemonic} {ins.op_str}".strip())
            if ins.mnemonic in ("ret", "int3"):
                break
        return out

    def ordered(seq, needles):
        i = 0
        for s in seq:
            if i < len(needles) and needles[i] in s:
                i += 1
        return i == len(needles)

    fails = 0
    for va, desc, needles in CHECKS:
        ok = ordered(body(va), needles)
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'} {va:#x} {desc}")

    raw = data[off(STRING_VA) - 1:off(STRING_VA) - 1 + 0x200]
    end = next(i for i in range(0, len(raw) - 1, 2) if raw[i:i + 2] == b"\0\0")
    text_w = raw[:end].decode("utf-16le", errors="replace")
    print(f"INFO {STRING_VA:#x} の 1 バイト前から UTF-16LE: {text_w[:40]!r} (即値の意味は未確定)")
    print(f"RESULT {'OK' if fails == 0 else 'NG'} fail={fails} total={len(CHECKS)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
