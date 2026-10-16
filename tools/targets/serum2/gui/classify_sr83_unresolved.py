#!/usr/bin/env python3
"""SR-83 #5005: 閉包の未解決間接 call 6 箇所 (REPORT_APPENDIX_5005.md §5.6) を分類する。

分類の規則 (機械的に確かめられるものだけ):
- `call qword ptr [rip+d]` で、スロットの中身が `jmp rax` (CFG 検査用ディスパッチ) のとき:
  宛先は rax で、rax は別オブジェクトの vtable 等から読んだ値。静的には宛先を確定できない (vtable 型追跡が要る)。
- `call reg` で、reg が `mov reg, [rip+d]` (グローバル関数ポインタ) から来るとき:
  スロット (.data の bss) の書き込み元を調べる。直接の `mov [rip+d], r` と、
  アドレスを取る `lea r, [rip+d]` の両方を走査し、書き込みが 0 件なら「静的に書き込みが無い (実行時に設定)」。
入力: PE (sha256 501e7bb3… を確認すること)・出力: 標準出力に 1 行 1 サイト。
usage: classify_sr83_unresolved.py <pe>
"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path = sys.argv[1]
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
tbase = IMG + text.VirtualAddress
raw = text.get_data()
cs = Cs(CS_ARCH_X86, CS_MODE_64)
RIP = re.compile(r"rip \+ (0x[0-9a-f]+)")


def off_of(va):
    rva = va - IMG
    for s in pe.sections:
        span = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if s.VirtualAddress <= rva < s.VirtualAddress + span and rva - s.VirtualAddress < s.SizeOfRawData:
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def qword_at(va):
    o = off_of(va)
    return struct.unpack_from("<Q", data, o)[0] if o is not None else None


def insns_at(va, n):
    return cs.disasm(raw[va - tbase: va - tbase + n], va)


def functions():
    pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
    pdd = data[pd.PointerToRawData:pd.PointerToRawData + pd.SizeOfRawData]
    for i in range(0, len(pdd) - 11, 12):
        b, e, _ = struct.unpack_from("<III", pdd, i)
        if b:
            yield IMG + b, IMG + e


def rip_target(ins):
    m = RIP.search(ins.op_str)
    return ins.address + ins.size + int(m.group(1), 16) if m else None


def writers_and_takers(slot):
    """slot を直接 store する命令と、アドレスを取る lea の位置を返す (全 .pdata 関数を走査)。"""
    stores, takes = [], []
    for b, e in functions():
        for ins in cs.disasm(raw[b - tbase: e - tbase], b):
            if "rip" not in ins.op_str or rip_target(ins) != slot:
                continue
            if ins.mnemonic == "lea":
                takes.append(hex(ins.address))
            elif ins.mnemonic == "mov" and ins.op_str.startswith("qword ptr [rip"):
                stores.append(hex(ins.address))
    return stores, takes


CALLS = [
    (0x180136CA7, "call r10", "global"),
    (0x180136CE8, "call r10", "global"),
    (0x180136D1D, "call rax", "global"),
    (0x1801381D8, "call rax", "global"),
    (0x1801425E3, "call rax", "global"),
    (0x1809CA7B2, "call [rip] (CFG候補: slot 中身を確認)", "cfg"),
    (0x1809CA88D, "call [rip] (CFG候補: slot 中身を確認)", "cfg"),
]

for va, label, kind in CALLS:
    fn = [f for f in functions() if f[0] <= va < f[1]]
    if not fn:
        print(f"{hex(va)}\t{label}\tno-pdata-owner")
        continue
    b = fn[0][0]
    ins_list = list(insns_at(b, va - b + 16))
    call = [i for i in ins_list if i.address == va]
    if not call:
        print(f"{hex(va)}\t{label}\tcall-not-found")
        continue
    call = call[0]
    if call.mnemonic == "call" and "rip" in call.op_str:
        slot = rip_target(call)
        content = qword_at(slot)
        disp = insns_at(content, 8) if content else []
        first = next(iter(disp), None)
        tag = f"{first.mnemonic} {first.op_str}" if first else "unreadable"
        print(f"{hex(va)}\t{label}\tslot={hex(slot)}\tcontent={hex(content or 0)}\tat-content={tag}\tCFG-dispatch={'yes' if tag == 'jmp rax' else 'no'}")
    else:
        # call reg: 直前に mov reg, [rip+d] で読んだグローバルを探す
        reg = call.op_str
        src = None
        for i in ins_list:
            if i.address >= va:
                break
            if i.mnemonic == "mov" and i.op_str.startswith(reg + ", qword ptr [rip"):
                src = rip_target(i)
        if src is None:
            print(f"{hex(va)}\t{label}\tsource-not-found")
            continue
        stores, takes = writers_and_takers(src)
        print(f"{hex(va)}\t{label}\tglobal={hex(src)}\tdirect-stores={len(stores)}\tlea-takes={len(takes)}\tbss={'yes' if off_of(src) is None else 'no'}")
