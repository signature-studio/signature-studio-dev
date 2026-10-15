#!/usr/bin/env python3
"""PY-124 (#2999): general.saveUndo の PE 事実 (書式・kwlist・既定値・核への受け渡し) を検査する (実機不要)。

  FL_WIN64_DIR=<展開先> python3 analysis/py124_saveundo.py

PE は fl-win64 素材の extracted/block00031_PE.bin (ImageBase 0x400000。文字列・表のポインタは絶対 VA)。
全検査が通れば PASS を出し、いずれかが外れれば AssertionError で止まる (PE 指紋が変わった時の検出)。
"""
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
WRAPPER = 0xD69900   # PyMethodDef entry 0x151ab40 の fn (METH_VARARGS | METH_KEYWORDS)
CORE = 0xD69860      # 核 (job 構造体 rcx を受ける。wrapper が 0xd843d0 に r8 で渡す)
JOB = 0xD843D0       # job 投入 (0xd841e0 で job 確保 → 0x526190 で実行)
FMT_LEA = 0xD69955   # lea r8,[rip+..] → 書式文字列
KWLIST_LEA = 0xD6995C  # lea r9,[rip+..] → kwlist (char* 配列)
KWLIST_VA = 0x151A928


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(PE, "rb").read()

    def read_va(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                off = s.PointerToRawData + (rva - s.VirtualAddress)
                return data[off:off + n]
        raise AssertionError(f"VA {va:#x} は PE の section に無い")

    def cstr(va):
        return read_va(va, 256).split(b"\0", 1)[0].decode()

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def insns(va, n):
        return [(i.address, f"{i.mnemonic} {i.op_str}") for i in md.disasm(read_va(va, n * 16), va)][:n]

    def lea_target(va):
        ins = next(md.disasm(read_va(va, 16), va))
        assert ins.mnemonic == "lea" and "rip" in ins.op_str, ins
        return ins.address + ins.size + int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)

    # 1. 書式文字列: 'si|i' (undoName 必須 str・flags 必須 int・updateHistory 任意 int)
    fmt = cstr(lea_target(FMT_LEA))
    assert fmt == "si|i", fmt

    # 2. kwlist: 3 本 (4 本目は NULL)。PE の文字列 VA は 0xd698d4 / 0xd698dd / 0xd698e3
    ptrs = [int.from_bytes(read_va(KWLIST_VA + 8 * k, 8), "little") for k in range(4)]
    names = [cstr(p) for p in ptrs[:3]]
    assert names == ["undoName", "flags", "updateHistory"], names
    assert ptrs[3] == 0, ptrs[3]
    assert lea_target(KWLIST_LEA) == KWLIST_VA

    # 3. 既定値: updateHistory の出力先 [rbp+0xa8] を 1 で初期化 (0xd69943)
    init = next(md.disasm(read_va(0xD69943, 16), 0xD69943))
    assert init.op_str == "dword ptr [rbp + 0xa8], 1" and init.mnemonic == "mov", init

    # 4. 核への受け渡し: job+0x18=flags (5 番目引数 [rbp+0x80])・job+0x20=updateHistory (6 番目 [rbp+0x88])・
    #    job+0x48=undoName (r9 → 0x4133f0)。wrapper は 0xd843d0 を 11 引数で呼ぶ (rcx=obj, rdx=結果, r8=核, r9=name)
    job = [s for _, s in insns(JOB, 0x60)]
    for src, dst in [("[rbp + 0x80]", "[rbx + 0x18]"), ("[rbp + 0x88]", "[rbx + 0x20]")]:
        pair = [f"mov rax, qword ptr {src}", f"mov qword ptr {dst}, rax"]
        assert any(job[k:k + 2] == pair for k in range(len(job) - 1)), pair
    assert any(s == "mov rdx, r13" for s in job) and any(s.startswith("call 0x4133f0") for s in job)

    # 5. 核: 準備判定 (vtbl+0x98)・成功時 status 0・updateHistory == 1 の判定 (cmp [rbx+0x20],1 / sete r9b)
    core = [s for _, s in insns(CORE, 0x60)]
    assert "mov qword ptr [rbx + 0x60], 0xfffffffffffffffe" in core
    assert "cmp qword ptr [rbx + 0x20], 1" in core and "sete r9b" in core
    assert any(s.startswith("call qword ptr [rax + 0x98]") for s in core)

    print(f"fmt={fmt!r} kwlist={names} default_updateHistory=1 "
          f"core_ready_check=call[vtbl+0x98] update_eq_1=sete_r9b")
    print("PASS: py124 saveUndo PE facts (fmt/kwlist/default/job mapping/core)")


if __name__ == "__main__":
    main()
